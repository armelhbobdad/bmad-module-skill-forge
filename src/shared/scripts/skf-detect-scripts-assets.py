# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Detect Scripts & Assets — file-level artifact detection for skill compilation.

Scans a source tree and identifies script and asset files per the detection
heuristics documented in
`src/skf-create-skill/references/extraction-patterns-tracing.md` (Script/Asset
Extraction Patterns section). The output feeds `scripts_inventory[]` and
`assets_inventory[]` in the create-skill workflow's extraction inventory
(see step 3 §4c).

This script replaces ~13 lines of prose plus implicit "compute SHA-256, read
shebang, find header comments" operations that would otherwise be re-derived
by the LLM on every run.

Subcommand: a single `detect` subcommand keeps room for future extensions
(e.g., `detect-entry-points` that only parses package.json/Cargo.toml).

CLI:
  uv run skf-detect-scripts-assets.py detect <source-root> \\
      [--scripts-intent detect|none] \\
      [--assets-intent detect|none] \\
      [--scope-include "pattern1,pattern2,..."] \\
      [--max-lines 500]

Detection rules — scripts:
  Directory convention: scripts/, bin/, tools/, cli/
  Shebang signals: #!/bin/bash, #!/usr/bin/env python|node|bash|sh, etc.
  Entry point declarations: package.json `bin`, pyproject.toml [project.scripts]
  CLI argument-parser imports are detected for the LLM-judgment tier only —
  this script flags the directory/shebang/entry-point cases that are fully
  deterministic.

Detection rules — assets:
  Directory convention: assets/, templates/, schemas/, configs/, examples/
  Pattern matches: *.schema.json (contains "$schema"), *.example,
    *.template.*, *.sample, openapi.json, *.graphql, swagger.yaml

Exclusions:
  Binary extensions: .so, .dll, .jar, .wasm, .exe, .dylib, .a, .o, .pyc,
    .class, .png, .jpg, .jpeg, .gif, .ico, .pdf, .zip, .tar, .gz, .tgz
  Generated paths: dist/, build/, .webpack/, node_modules/, __pycache__/,
    target/ (Rust), .next/, .nuxt/, out/, coverage/

Size flag:
  Files >max-lines (default 500) get size_flag="oversized" but are still
  included — the caller decides whether to bundle them.

Output JSON (stdout):
  {
    "scripts_inventory": [ {name, source_file, purpose, language,
                            content_hash, confidence, lines, size_flag}, ... ],
    "assets_inventory":  [ {name, source_file, purpose, type, content_hash,
                            confidence, lines, size_flag}, ... ],
    "scripts_skipped": false,
    "assets_skipped":  false,
    "stats": { "scripts_found": N, "assets_found": M, "files_scanned": K }
  }

Confidence is always "T1-low" — file existence verified, content not
AST-analyzed. Matches the spec at extraction-patterns-tracing.md §Provenance.

Exit codes:
  0  — detection succeeded (including --scripts-intent=none --assets-intent=none)
  1  — user error (bad source root, malformed args)
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Iterable


# --------------------------------------------------------------------------
# Constants — detection rules (single source of truth)
# --------------------------------------------------------------------------


SCRIPT_DIRS = {"scripts", "bin", "tools", "cli"}
ASSET_DIRS = {"assets", "templates", "schemas", "configs", "examples"}

SHEBANG_LANGS = {
    "bash": "bash",
    "sh": "shell",
    "zsh": "zsh",
    "python": "python",
    "python2": "python",
    "python3": "python",
    "node": "javascript",
    "deno": "typescript",
    "ruby": "ruby",
    "perl": "perl",
}

EXTENSION_LANGS = {
    ".sh": "shell",
    ".bash": "bash",
    ".zsh": "zsh",
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".rb": "ruby",
    ".pl": "perl",
    ".go": "go",
    ".rs": "rust",
}

BINARY_EXTS = {
    ".so", ".dll", ".jar", ".wasm", ".exe", ".dylib", ".a", ".o",
    ".pyc", ".class", ".png", ".jpg", ".jpeg", ".gif", ".ico",
    ".pdf", ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
}

# Path-segment names that mark generated/vendored output trees.
EXCLUDED_DIR_NAMES = {
    "node_modules", "__pycache__", "dist", "build", ".webpack",
    "target", ".next", ".nuxt", "out", "coverage", ".git",
    ".venv", "venv", ".tox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".gradle", ".idea", ".vscode",
}

ASSET_TYPE_SCHEMA = "schema"
ASSET_TYPE_TEMPLATE = "template"
ASSET_TYPE_CONFIG = "config"
ASSET_TYPE_EXAMPLE = "example"

CONFIDENCE = "T1-low"


# --------------------------------------------------------------------------
# Walk + filter
# --------------------------------------------------------------------------


def iter_files(source_root: Path) -> Iterable[Path]:
    """Yield every file under source_root, skipping excluded directory trees.

    Done as a manual walk so we can prune EXCLUDED_DIR_NAMES at any depth
    without scanning their contents (Path.rglob can't prune efficiently).
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
                yield entry


def is_binary_path(path: Path) -> bool:
    return path.suffix.lower() in BINARY_EXTS


def relative_segments(path: Path, root: Path) -> tuple[str, ...]:
    """Return path parts relative to root, dropping the filename."""
    rel = path.relative_to(root)
    return rel.parts[:-1]


def in_directory(path: Path, root: Path, dir_names: set[str]) -> bool:
    """True if any segment of path's relative dir is in dir_names."""
    return any(seg in dir_names for seg in relative_segments(path, root))


def matches_scope(path: Path, root: Path, scope_patterns: list[str]) -> bool:
    """Match `path` against scope-include glob patterns relative to root."""
    if not scope_patterns:
        return True
    rel = str(path.relative_to(root))
    return any(fnmatch.fnmatch(rel, pattern) for pattern in scope_patterns)


# --------------------------------------------------------------------------
# Read helpers
# --------------------------------------------------------------------------


def read_text_safe(path: Path, *, max_bytes: int | None = None) -> str | None:
    """Read text from `path` as UTF-8, returning None on decode failure
    (treated as binary). Caller can pass max_bytes to bound reads of large
    files."""
    try:
        if max_bytes is None:
            return path.read_text(encoding="utf-8")
        with path.open("rb") as fh:
            blob = fh.read(max_bytes)
        return blob.decode("utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def sha256_of_file(path: Path) -> str:
    """Compute SHA-256 of file content; emits with `sha256:` prefix."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def count_lines(path: Path) -> int:
    """Count newlines in the file; returns 0 if file is unreadable."""
    n = 0
    try:
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                n += chunk.count(b"\n")
    except OSError:
        return 0
    return n


# --------------------------------------------------------------------------
# Script detection
# --------------------------------------------------------------------------


_SHEBANG_RE = re.compile(rb"^#!.*?(\b(?:" + "|".join(SHEBANG_LANGS).encode() + rb")\b)")


def detect_shebang_language(path: Path) -> str | None:
    """Return language name if the file starts with a recognized shebang."""
    try:
        with path.open("rb") as fh:
            first = fh.readline(256)
    except OSError:
        return None
    if not first.startswith(b"#!"):
        return None
    match = _SHEBANG_RE.match(first)
    if not match:
        return None
    interp = match.group(1).decode()
    return SHEBANG_LANGS.get(interp)


def detect_language(path: Path, *, shebang_lang: str | None) -> str:
    """Determine the script's language for the inventory record."""
    if shebang_lang:
        return shebang_lang
    ext_lang = EXTENSION_LANGS.get(path.suffix.lower())
    if ext_lang:
        return ext_lang
    return "unknown"


def entry_point_script_paths(source_root: Path) -> set[Path]:
    """Parse package.json `bin` and pyproject.toml [project.scripts] to find
    explicit entry-point scripts. Returns absolute paths that exist on disk.

    Other manifest formats (Cargo.toml [[bin]]) are handled by directory
    convention (`src/bin/` etc.) rather than parsing — adding a Cargo parser
    is future work and not in this script's scope per the deterministic-only
    extraction rule.
    """
    found: set[Path] = set()
    found.update(_parse_package_json_bin(source_root))
    found.update(_parse_pyproject_scripts(source_root))
    return found


def _parse_package_json_bin(source_root: Path) -> Iterable[Path]:
    pkg = source_root / "package.json"
    if not pkg.is_file():
        return ()
    text = read_text_safe(pkg, max_bytes=512 * 1024)
    if text is None:
        return ()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return ()
    bin_field = data.get("bin")
    if isinstance(bin_field, str):
        candidates = [bin_field]
    elif isinstance(bin_field, dict):
        candidates = [v for v in bin_field.values() if isinstance(v, str)]
    else:
        return ()
    out: list[Path] = []
    for cand in candidates:
        # bin paths are relative to package.json
        p = (source_root / cand).resolve()
        if p.is_file():
            out.append(p)
    return out


def _parse_pyproject_scripts(source_root: Path) -> Iterable[Path]:
    """Pyproject [project.scripts] points at a dotted module path, not a file
    path — we can't deterministically map `mypkg.cli:main` to a script file
    without invoking the package's installer. We instead surface the existence
    of any [project.scripts] entry as a hint by treating any file under
    `<source_root>/<top-level>/__main__.py` or files matching the cli module
    in standard layouts. To avoid speculative mapping, this function returns
    an empty set today; the directory-convention path picks up most cases
    (script-like files in scripts/ or bin/). Future work: parse setuptools
    package layout to resolve.
    """
    _ = source_root
    return ()


def is_script(path: Path, source_root: Path, *, entry_points: set[Path]) -> tuple[bool, str | None]:
    """Decide whether `path` is a script. Returns (is_script, shebang_lang)."""
    if path.resolve() in entry_points:
        return True, detect_shebang_language(path)
    if in_directory(path, source_root, SCRIPT_DIRS):
        return True, detect_shebang_language(path)
    shebang_lang = detect_shebang_language(path)
    if shebang_lang is not None:
        return True, shebang_lang
    return False, None


# --------------------------------------------------------------------------
# Asset detection
# --------------------------------------------------------------------------


_ASSET_FILENAME_TYPE: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r".*\.schema\.json$", re.IGNORECASE), ASSET_TYPE_SCHEMA),
    (re.compile(r"^openapi\.(json|ya?ml)$", re.IGNORECASE), ASSET_TYPE_SCHEMA),
    (re.compile(r"^swagger\.(json|ya?ml)$", re.IGNORECASE), ASSET_TYPE_SCHEMA),
    (re.compile(r".*\.graphql$", re.IGNORECASE), ASSET_TYPE_SCHEMA),
    (re.compile(r".*\.template\..+$", re.IGNORECASE), ASSET_TYPE_TEMPLATE),
    (re.compile(r".*\.(example|sample)(\..+)?$", re.IGNORECASE), ASSET_TYPE_EXAMPLE),
]


def asset_type(path: Path, source_root: Path) -> str | None:
    """Return the asset type for `path` or None if it doesn't match asset rules."""
    # Pattern-based detection (works regardless of containing directory)
    for pattern, atype in _ASSET_FILENAME_TYPE:
        if pattern.match(path.name):
            return atype

    if in_directory(path, source_root, ASSET_DIRS):
        segments = set(relative_segments(path, source_root))
        if "templates" in segments:
            return ASSET_TYPE_TEMPLATE
        if "schemas" in segments:
            # JSON schema content check
            if path.suffix.lower() == ".json":
                text = read_text_safe(path, max_bytes=64 * 1024)
                if text and '"$schema"' in text:
                    return ASSET_TYPE_SCHEMA
            return ASSET_TYPE_SCHEMA
        if "configs" in segments:
            return ASSET_TYPE_CONFIG
        if "examples" in segments:
            return ASSET_TYPE_EXAMPLE
        # assets/ — type unknown, default to config (safer than template)
        return ASSET_TYPE_CONFIG
    return None


# --------------------------------------------------------------------------
# Purpose extraction
# --------------------------------------------------------------------------


_HEADER_COMMENT_RE = re.compile(
    r"^\s*(?:#|//|/\*|\*)\s*(.{3,})$"
)


def extract_purpose(path: Path, *, asset_type_hint: str | None) -> str:
    """Pull a one-line purpose summary from the file's leading content.

    Heuristics (first match wins):
      - JSON schema: read top-level `title` or `description` field
      - Files with header comments: first comment line after any shebang
      - Otherwise: fall back to the filename (per spec)
    """
    if asset_type_hint == ASSET_TYPE_SCHEMA and path.suffix.lower() == ".json":
        text = read_text_safe(path, max_bytes=64 * 1024)
        if text:
            try:
                data = json.loads(text)
                for key in ("title", "description"):
                    val = data.get(key) if isinstance(data, dict) else None
                    if isinstance(val, str) and val.strip():
                        return val.strip()
            except json.JSONDecodeError:
                pass

    text = read_text_safe(path, max_bytes=4 * 1024)
    if text:
        for i, line in enumerate(text.splitlines()[:10]):
            if i == 0 and line.startswith("#!"):
                continue
            if not line.strip():
                continue
            match = _HEADER_COMMENT_RE.match(line)
            if match:
                purpose = match.group(1).strip().rstrip("*/").strip()
                if purpose:
                    return purpose

    return path.name


# --------------------------------------------------------------------------
# Build records
# --------------------------------------------------------------------------


def build_script_record(
    path: Path, source_root: Path, *, shebang_lang: str | None, max_lines: int
) -> dict:
    rel = str(path.relative_to(source_root))
    lines = count_lines(path)
    return {
        "name": path.name,
        "source_file": rel,
        "purpose": extract_purpose(path, asset_type_hint=None),
        "language": detect_language(path, shebang_lang=shebang_lang),
        "content_hash": sha256_of_file(path),
        "confidence": CONFIDENCE,
        "lines": lines,
        "size_flag": "oversized" if lines > max_lines else None,
    }


def build_asset_record(
    path: Path, source_root: Path, *, atype: str, max_lines: int
) -> dict:
    rel = str(path.relative_to(source_root))
    lines = count_lines(path)
    return {
        "name": path.name,
        "source_file": rel,
        "purpose": extract_purpose(path, asset_type_hint=atype),
        "type": atype,
        "content_hash": sha256_of_file(path),
        "confidence": CONFIDENCE,
        "lines": lines,
        "size_flag": "oversized" if lines > max_lines else None,
    }


# --------------------------------------------------------------------------
# Main detection
# --------------------------------------------------------------------------


def detect(
    source_root: Path,
    *,
    scripts_intent: str = "detect",
    assets_intent: str = "detect",
    scope_patterns: list[str] | None = None,
    max_lines: int = 500,
) -> dict:
    scope_patterns = scope_patterns or []
    scripts_skipped = scripts_intent == "none"
    assets_skipped = assets_intent == "none"

    scripts_inventory: list[dict] = []
    assets_inventory: list[dict] = []
    files_scanned = 0

    entry_points = (
        entry_point_script_paths(source_root) if not scripts_skipped else set()
    )

    if not scripts_skipped or not assets_skipped:
        for path in iter_files(source_root):
            files_scanned += 1
            if is_binary_path(path):
                continue
            if not matches_scope(path, source_root, scope_patterns):
                continue

            if not scripts_skipped:
                is_scr, shebang_lang = is_script(
                    path, source_root, entry_points=entry_points
                )
                if is_scr:
                    scripts_inventory.append(
                        build_script_record(
                            path, source_root,
                            shebang_lang=shebang_lang, max_lines=max_lines,
                        )
                    )
                    continue  # a script can't also be an asset

            if not assets_skipped:
                atype = asset_type(path, source_root)
                if atype is not None:
                    assets_inventory.append(
                        build_asset_record(
                            path, source_root, atype=atype, max_lines=max_lines,
                        )
                    )

    # Deterministic ordering for stable diffs / cacheability
    scripts_inventory.sort(key=lambda r: r["source_file"])
    assets_inventory.sort(key=lambda r: r["source_file"])

    return {
        "scripts_inventory": scripts_inventory,
        "assets_inventory": assets_inventory,
        "scripts_skipped": scripts_skipped,
        "assets_skipped": assets_skipped,
        "stats": {
            "scripts_found": len(scripts_inventory),
            "assets_found": len(assets_inventory),
            "files_scanned": files_scanned,
        },
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_detect(args: argparse.Namespace) -> int:
    source_root = Path(args.source_root).resolve()
    if not source_root.is_dir():
        print(f"error: source root not a directory: {source_root}", file=sys.stderr)
        return 1
    scope_patterns = (
        [s.strip() for s in args.scope_include.split(",") if s.strip()]
        if args.scope_include
        else []
    )
    if args.scripts_intent not in ("detect", "none"):
        print(f"error: --scripts-intent must be detect|none", file=sys.stderr)
        return 1
    if args.assets_intent not in ("detect", "none"):
        print(f"error: --assets-intent must be detect|none", file=sys.stderr)
        return 1

    result = detect(
        source_root,
        scripts_intent=args.scripts_intent,
        assets_intent=args.assets_intent,
        scope_patterns=scope_patterns,
        max_lines=args.max_lines,
    )
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-detect-scripts-assets",
        description="Detect script and asset files in a source tree per SKF extraction rules.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("detect", help="scan a source tree and emit inventory JSON")
    p.add_argument("source_root", help="path to the source tree root")
    p.add_argument(
        "--scripts-intent",
        default="detect",
        help="detect|none (default: detect)",
    )
    p.add_argument(
        "--assets-intent",
        default="detect",
        help="detect|none (default: detect)",
    )
    p.add_argument(
        "--scope-include",
        default=None,
        help="comma-separated glob patterns to limit detection (relative to source-root)",
    )
    p.add_argument(
        "--max-lines",
        type=int,
        default=500,
        help="files above this line count get size_flag='oversized' (default: 500)",
    )
    p.set_defaults(func=_cmd_detect)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
