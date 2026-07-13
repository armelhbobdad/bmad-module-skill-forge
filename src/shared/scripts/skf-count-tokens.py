#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""SKF Count Tokens — Deterministic per-artifact token/word metrics for a skill package.

Pre-pass that measures the exported artifacts of a single skill package and the
shared managed section, so the export skill's token report (references/token-report.md)
and snippet token check (references/generate-snippet.md §4) render exact numbers from
JSON instead of re-reading every reference file to word-count it in-prompt.

Metrics:
  - words:  whitespace-split word count (`len(text.split())`) — the report's "Words" column
  - tokens: char-over-four estimate (`len(text) // 4`) — the SKF-wide convention already
            used by skf-validate-output.py, so every SKF token number agrees

Measured artifacts (all relative to the positional skill-package dir):
  - context-snippet.md   — the compressed passive-context snippet (if present)
  - SKILL.md             — the active skill document
  - metadata.json        — machine-readable metadata
  - references/*         — every file under references/ (recursively), summed as references_total
  - managed section      — the complete <!-- SKF:BEGIN ... --> ... <!-- SKF:END --> block,
                           extracted from the first --target-file that contains one
                           (shared across the batch; measured once)

package_total sums context-snippet.md + SKILL.md + metadata.json + references_total and
DELIBERATELY EXCLUDES the managed-section row — the managed section is a shared all-skills
cost reported separately, and including it would double-count this skill's own snippet
(see references/token-report.md §1).

CLI:
  python3 skf-count-tokens.py <skill-package-dir>
  python3 skf-count-tokens.py <skill-package-dir> --target-file CLAUDE.md
  python3 skf-count-tokens.py <skill-package-dir> --target-file CLAUDE.md --target-file AGENTS.md
  python3 skf-count-tokens.py <skill-package-dir> -o report.json

Exit codes: 0 = metrics emitted, 2 = error (skill package dir missing / not a directory).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Mirrors skf-rebuild-managed-sections.py: a BEGIN marker may carry attributes
# (e.g. `updated:2026-07-13`) before its closing `-->`; the END marker is fixed.
MANAGED_SECTION_RE = re.compile(
    r"<!-- SKF:BEGIN[^>]*-->.*?<!-- SKF:END -->",
    re.DOTALL,
)

# Core per-skill artifacts, in report order. (references/ is handled separately.)
CORE_ARTIFACTS = [
    ("context-snippet.md", "context-snippet"),
    ("SKILL.md", "skill-md"),
    ("metadata.json", "metadata"),
]


def estimate_tokens(text: str) -> int:
    """Char-over-four token estimate — the SKF-wide convention (see skf-validate-output.py)."""
    return len(text) // 4


def count_words(text: str) -> int:
    """Whitespace-split word count — the token report's 'Words' column."""
    return len(text.split())


def measure(text: str) -> dict:
    """Return the {words, tokens} metrics for a piece of text."""
    return {"words": count_words(text), "tokens": estimate_tokens(text)}


def _read_text(path: Path) -> str:
    # encoding is pinned to utf-8 so non-ASCII content is not mojibaked on
    # Windows (cp1252 default).
    return path.read_text(encoding="utf-8")


def extract_managed_section(text: str) -> str | None:
    """Return the complete BEGIN..END managed-section span (markers included), or None."""
    m = MANAGED_SECTION_RE.search(text)
    return m.group(0) if m else None


def measure_reference_files(references_dir: Path) -> tuple[list[dict], dict]:
    """Measure every file under references/ (recursively, sorted). Returns (per-file rows, total)."""
    rows: list[dict] = []
    total_words = 0
    total_tokens = 0
    if references_dir.is_dir():
        for path in sorted(references_dir.rglob("*"), key=lambda p: p.as_posix()):
            if not path.is_file():
                continue
            text = _read_text(path)
            metrics = measure(text)
            rows.append(
                {
                    "path": path.relative_to(references_dir.parent).as_posix(),
                    "role": "reference",
                    "exists": True,
                    **metrics,
                }
            )
            total_words += metrics["words"]
            total_tokens += metrics["tokens"]
    total = {"count": len(rows), "words": total_words, "tokens": total_tokens}
    return rows, total


def count_package(skill_dir: Path, target_files: list[Path] | None = None) -> dict:
    """Measure a skill package's artifacts and the shared managed section.

    Returns the metrics dict (see module docstring for the shape). Missing core
    artifacts are reported with exists=False and zero metrics so package_total is
    always well-defined and callers can render 'N/A' rows without guessing.
    """
    skill_dir = Path(skill_dir)
    target_files = target_files or []

    files: list[dict] = []

    # Core per-skill artifacts.
    for name, role in CORE_ARTIFACTS:
        path = skill_dir / name
        if path.is_file():
            metrics = measure(_read_text(path))
            files.append({"path": name, "role": role, "exists": True, **metrics})
        else:
            files.append({"path": name, "role": role, "exists": False, "words": 0, "tokens": 0})

    # references/ — per-file rows + summed total.
    ref_rows, references_total = measure_reference_files(skill_dir / "references")
    files.extend(ref_rows)

    # package_total = snippet + SKILL.md + metadata + references_total; EXCLUDES managed section.
    core_by_role = {row["role"]: row for row in files if row["role"] in {"context-snippet", "skill-md", "metadata"}}
    package_total = {
        "words": sum(core_by_role[r]["words"] for r in core_by_role) + references_total["words"],
        "tokens": sum(core_by_role[r]["tokens"] for r in core_by_role) + references_total["tokens"],
    }

    # Managed section — first --target-file that actually contains a block wins.
    managed_section = {"present": False, "source_file": None, "words": 0, "tokens": 0}
    for tf in target_files:
        tf = Path(tf)
        if not tf.is_file():
            continue
        section = extract_managed_section(_read_text(tf))
        if section is not None:
            managed_section = {
                "present": True,
                "source_file": tf.as_posix(),
                **measure(section),
            }
            break

    return {
        "status": "ok",
        "skill_package": skill_dir.as_posix(),
        "files": files,
        "references_total": references_total,
        "managed_section": managed_section,
        "package_total": package_total,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skf-count-tokens.py",
        description=(
            "Deterministic per-artifact word/token metrics for a skill package. Emits JSON "
            "with per-file rows, references_total, the shared managed-section block, and a "
            "package_total that excludes the managed section (see references/token-report.md §1). "
            "tokens = len(text)//4 (SKF-wide convention); words = whitespace-split count."
        ),
    )
    parser.add_argument(
        "skill_package",
        help="Resolved skill-package directory (holds context-snippet.md, SKILL.md, metadata.json, references/)",
    )
    parser.add_argument(
        "--target-file",
        action="append",
        default=[],
        metavar="PATH",
        help="Context file (CLAUDE.md / AGENTS.md / .cursorrules) to extract the managed "
        "section from; repeatable — the first file with a BEGIN..END block is measured.",
    )
    parser.add_argument("-o", "--output", metavar="PATH", help="Write JSON here (default: stdout)")
    parser.add_argument("--verbose", action="store_true", help="Emit diagnostics to stderr")
    args = parser.parse_args(argv)

    skill_dir = Path(args.skill_package)
    if not skill_dir.is_dir():
        print(f"error: skill package directory not found: {skill_dir}", file=sys.stderr)
        return 2

    if args.verbose:
        print(f"measuring skill package: {skill_dir}", file=sys.stderr)
        if args.target_file:
            print(f"managed-section candidates: {args.target_file}", file=sys.stderr)

    result = count_package(skill_dir, [Path(p) for p in args.target_file])

    payload = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
        if args.verbose:
            print(f"wrote {args.output}", file=sys.stderr)
    else:
        print(payload)

    return 0


if __name__ == "__main__":
    sys.exit(main())
