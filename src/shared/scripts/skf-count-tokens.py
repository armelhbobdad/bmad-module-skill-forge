#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
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

The managed_section object also gives `skills`, the number of skill rows (each
`[name v...]` row header) in the measured block, and `target_files`, every --target-file
that holds a block, in the order passed and each once. A target file that cannot be read
as UTF-8 text is skipped.

package_total sums context-snippet.md + SKILL.md + metadata.json + references_total and
DELIBERATELY EXCLUDES the managed-section row — the managed section is a shared all-skills
cost reported separately, and including it would double-count this skill's own snippet
(see references/token-report.md §1).

context_budget gives the token report's Context Budget Impact values, in tokens:
  - always_on:       the managed section (loaded in every session); null when no
                     target file holds a block
  - on_trigger:      SKILL.md (loaded when the skill triggers)
  - full_disclosure: SKILL.md + references_total (loaded when every reference is read too);
                     neither the snippet nor metadata.json, so it is not package_total
  - snippet:         context-snippet.md (this skill's share of the managed section)

What a run has staged but not written, the token report of an export dry run measures
with these flags (without them the output is unchanged):
  - --snippet PATH:      PATH is the context-snippet row: its `path` is PATH, and it is
                         reported with exists false and zero metrics when PATH is absent.
  - --no-snippet:        no context-snippet row (a run with passive context off writes
                         none): package_total leaves it out and context_budget.snippet is
                         null. It cannot be combined with --snippet (exit 2).
  - --section-file PATH: PATH holds a managed-section body as `assemble --out` stages it;
                         the managed section is measured as the block `insert` and
                         `replace` would write around it, `<!-- SKF:BEGIN updated:{today} -->`,
                         the body and `<!-- SKF:END -->` on lines of their own, today being
                         the UTC date, so its numbers equal the written block's. Then
                         `present` is true, `source_file` is PATH and `target_files` lists
                         each --target-file once, in order, without reading it. A PATH that
                         is missing, a folder or not UTF-8 text exits 2.

CLI:
  python3 skf-count-tokens.py <skill-package-dir>
  python3 skf-count-tokens.py <skill-package-dir> --target-file CLAUDE.md
  python3 skf-count-tokens.py <skill-package-dir> --target-file CLAUDE.md --target-file AGENTS.md
  python3 skf-count-tokens.py <skill-package-dir> -o report.json
  python3 skf-count-tokens.py <skill-package-dir> --snippet <draft> --section-file <body> --target-file CLAUDE.md
  python3 skf-count-tokens.py <skill-package-dir> --no-snippet

Exit codes: 0 = metrics emitted, 2 = error (skill package dir missing / not a directory,
--snippet with --no-snippet, or a --section-file it cannot read).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Mirrors skf-rebuild-managed-sections.py: a BEGIN marker may carry attributes
# (e.g. `updated:2026-07-13`) before its closing `-->`; the END marker is fixed.
MANAGED_SECTION_RE = re.compile(
    r"<!-- SKF:BEGIN[^>]*-->.*?<!-- SKF:END -->",
    re.DOTALL,
)

# A skill row header of the managed section: `[name v<version>]` at the start of a line,
# optionally after the format's leading `|`, with or without a `root:` field. The
# ` v<version>` keeps the section's own `[SKF Skills]|{n} skills|{m} stack` header out.
# This is skf-rebuild-managed-sections.py's ROW_HEADER_PATTERN, so both scripts count the
# rows parse_managed_rows returns (test-skf-count-tokens.py keeps them in step).
MANAGED_ROW_RE = re.compile(r"^\|?\[(?P<name>[^\]]+?) v(?P<version>[^\]\s]+)\]", re.MULTILINE)

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


def wrap_section(body: str, today: str | None = None) -> str:
    """The block skf-rebuild-managed-sections.py's insert and replace write around a staged body."""
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"<!-- SKF:BEGIN updated:{today} -->\n{body}\n<!-- SKF:END -->"


def count_managed_skills(section: str) -> int:
    """The number of skill rows (`[name v...]` row headers) in a managed section."""
    return len(MANAGED_ROW_RE.findall(section))


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


def count_package(
    skill_dir: Path,
    target_files: list[Path] | None = None,
    *,
    snippet: Path | None = None,
    no_snippet: bool = False,
    section: str | None = None,
    section_source: Path | None = None,
) -> dict:
    """Measure a skill package's artifacts and the shared managed section.

    Returns the metrics dict (see module docstring for the shape). Missing core
    artifacts are reported with exists=False and zero metrics so package_total is
    always well-defined and callers can render 'N/A' rows without guessing.
    `snippet` measures that file as the context-snippet row, `no_snippet` leaves
    the row out, and `section` (a block wrap_section built, read from
    `section_source`) is measured in place of the target files' blocks.
    """
    skill_dir = Path(skill_dir)
    target_files = target_files or []

    files: list[dict] = []

    # Core per-skill artifacts.
    for name, role in CORE_ARTIFACTS:
        path, shown = skill_dir / name, name
        if role == "context-snippet":
            if no_snippet:
                continue
            if snippet is not None:
                path = Path(snippet)
                shown = path.as_posix()
        if path.is_file():
            metrics = measure(_read_text(path))
            files.append({"path": shown, "role": role, "exists": True, **metrics})
        else:
            files.append({"path": shown, "role": role, "exists": False, "words": 0, "tokens": 0})

    # references/ — per-file rows + summed total.
    ref_rows, references_total = measure_reference_files(skill_dir / "references")
    files.extend(ref_rows)

    # package_total = snippet + SKILL.md + metadata + references_total; EXCLUDES managed section.
    core_by_role = {row["role"]: row for row in files if row["role"] in {"context-snippet", "skill-md", "metadata"}}
    package_total = {
        "words": sum(core_by_role[r]["words"] for r in core_by_role) + references_total["words"],
        "tokens": sum(core_by_role[r]["tokens"] for r in core_by_role) + references_total["tokens"],
    }

    # Managed section: the first --target-file that actually contains a block is measured;
    # target_files lists every one that holds a block.
    managed_section = {"present": False, "source_file": None, "target_files": [], "skills": 0,
                       "words": 0, "tokens": 0}
    seen: set[Path] = set()
    if section is not None:
        # The staged section is measured; the target files are only listed, unread.
        for tf in target_files:
            tf = Path(tf)
            if tf.resolve() not in seen:
                seen.add(tf.resolve())
                managed_section["target_files"].append(tf.as_posix())
        managed_section.update(
            present=True,
            source_file=Path(section_source).as_posix() if section_source is not None else None,
            skills=count_managed_skills(section),
            **measure(section),
        )
        target_files = []
    for tf in target_files:
        tf = Path(tf)
        if tf.resolve() in seen or not tf.is_file():
            continue
        seen.add(tf.resolve())
        try:
            section = extract_managed_section(_read_text(tf))
        except (OSError, UnicodeDecodeError):
            continue  # unreadable or not UTF-8: it holds no block this helper can measure
        if section is None:
            continue
        managed_section["target_files"].append(tf.as_posix())
        if not managed_section["present"]:
            managed_section.update(
                present=True,
                source_file=tf.as_posix(),
                skills=count_managed_skills(section),
                **measure(section),
            )

    # The Context Budget Impact values token-report.md §2 renders.
    context_budget = {
        "always_on": managed_section["tokens"] if managed_section["present"] else None,
        "on_trigger": core_by_role["skill-md"]["tokens"],
        "full_disclosure": core_by_role["skill-md"]["tokens"] + references_total["tokens"],
        "snippet": core_by_role["context-snippet"]["tokens"] if "context-snippet" in core_by_role else None,
    }

    return {
        "status": "ok",
        "skill_package": skill_dir.as_posix(),
        "files": files,
        "references_total": references_total,
        "managed_section": managed_section,
        "package_total": package_total,
        "context_budget": context_budget,
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
    snippet_group = parser.add_mutually_exclusive_group()
    snippet_group.add_argument(
        "--snippet",
        metavar="PATH",
        help="Measure this file as the context-snippet row (a staged draft) instead of the package's.",
    )
    snippet_group.add_argument(
        "--no-snippet",
        action="store_true",
        help="Leave the context-snippet row out (a run with passive context off writes none).",
    )
    parser.add_argument(
        "--section-file",
        metavar="PATH",
        help="A managed-section body as `assemble --out` stages it: measure the block insert or "
        "replace would write around it; --target-file is then listed, not read.",
    )
    parser.add_argument("-o", "--output", metavar="PATH", help="Write JSON here (default: stdout)")
    parser.add_argument("--verbose", action="store_true", help="Emit diagnostics to stderr")
    args = parser.parse_args(argv)

    skill_dir = Path(args.skill_package)
    if not skill_dir.is_dir():
        print(f"error: skill package directory not found: {skill_dir}", file=sys.stderr)
        return 2

    section = None
    if args.section_file is not None:
        section_path = Path(args.section_file)
        if not section_path.is_file():
            what = "a folder" if section_path.is_dir() else "missing"
            print(f"error: --section-file {section_path.as_posix()} is {what}", file=sys.stderr)
            return 2
        try:
            # Read as the written context file is read back to measure it (newlines
            # translated), so even a CRLF body measures as the block written from it.
            section = wrap_section(section_path.read_text(encoding="utf-8"))
        except UnicodeDecodeError as e:
            print(f"error: --section-file {section_path.as_posix()} is not UTF-8 text ({e})", file=sys.stderr)
            return 2
        except OSError as e:
            print(f"error: cannot read --section-file {section_path.as_posix()}: {e}", file=sys.stderr)
            return 2

    if args.verbose:
        print(f"measuring skill package: {skill_dir}", file=sys.stderr)
        if args.target_file:
            print(f"managed-section candidates: {args.target_file}", file=sys.stderr)

    result = count_package(
        skill_dir,
        [Path(p) for p in args.target_file],
        snippet=Path(args.snippet) if args.snippet is not None else None,
        no_snippet=args.no_snippet,
        section=section,
        section_source=Path(args.section_file) if section is not None else None,
    )

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
