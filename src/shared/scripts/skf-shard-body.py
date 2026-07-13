#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Shard Body — deterministic auto-shard of an oversized SKILL.md body.

Replaces the in-prompt line-counting / boundary-detection / size-sort /
file-write / blockquote-replacement surgery that `skf-create-skill`'s
`references/step-auto-shard.md` §1–§5 and `references/validate.md` §4
otherwise perform by hand (LLM line-counting is the least reliable
deterministic op — it silently ships an over-budget body or wrongly HALTs).

What it does (single positional invocation):

  1. Split frontmatter (leading `---` … `---`) from body. Frontmatter is
     NEVER modified.
  2. Count body lines between the frontmatter close and EOF, excluding
     trailing blank lines  → `body_lines_before`.
  3. If `body_lines_before` <= `--budget` (default 400): emit
     `action: "skip"`, write nothing.
  4. Otherwise enumerate Tier-2 sections — level-2 headings whose text
     starts with `Full` (`## Full API Reference`, `## Full Type
     Definitions`, …). Each section spans its heading through the line
     before the next level-1/level-2 heading (or EOF).
  5. Sort candidates by line count descending (largest first, stable) and
     greedily extract the largest, re-counting after each, stopping the
     moment the body fits under budget. If selective extraction of every
     Tier-2 section still cannot fit, extract them all and report
     `under_budget: false` (the caller then trims Tier-1 by editing
     judgment — that fallback stays in the prompt).
  6. Each extracted section is written to `references/{kebab(heading)}.md`
     (heading preserved) via `skf-atomic-write.py`, and the section in
     SKILL.md is replaced by a `> See [Title](references/…md)` blockquote.
     The rewritten SKILL.md is itself written via `skf-atomic-write.py`.
  7. Verify every Tier-1 heading that was inline before extraction is still
     inline (`tier1_preserved`, with `tier1_missing[]`), and every emitted
     blockquote resolves to a written reference file (`xref_ok`).

Deterministic: same input + budget → same JSON and same on-disk result.

Output JSON (stdout, or `-o`):
  {
    "action": "skip" | "shard",
    "body_lines_before": <int>,
    "body_lines_after": <int>,
    "sections_extracted": [
      {"heading": "Full API Reference",
       "file": "references/full-api-reference.md",
       "lines": <int>}
    ],
    "tier1_preserved": <bool>,
    "tier1_missing": ["Overview", ...],
    "xref_ok": <bool>,
    "under_budget": <bool>,
    "dry_run": <bool>,
    "budget": <int>
  }

Heading parsing reuses `skf-scan-skill-md-structure.py`'s `_HEADING_RE`
(single source of truth for what counts as a heading), imported from the
adjacent script; a local copy of the same pattern is the fallback if the
sibling is unavailable.

Exit codes:
  0 — analysis succeeded (skip, shard, or a tier1-violation report the
      caller HALTs on). Emitting a valid report is success; the caller
      gates on `tier1_preserved` / `xref_ok`.
  1 — user error (file not found, unreadable, bad frontmatter).
  2 — operation failure (a reference/SKILL.md write could not complete).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path


# --------------------------------------------------------------------------
# Heading regex — reuse the sibling scanner's single source of truth
# --------------------------------------------------------------------------


def _load_heading_re() -> "re.Pattern[str]":
    """Import `_HEADING_RE` from the adjacent structure-scanner script.

    Both scripts install into the same directory (dev `src/shared/scripts/`
    and installed `_bmad/skf/shared/scripts/`), so the sibling is always
    adjacent. Fall back to an identical literal if the import fails, so the
    script still runs standalone (graceful degradation).
    """
    sibling = Path(__file__).resolve().parent / "skf-scan-skill-md-structure.py"
    try:
        spec = importlib.util.spec_from_file_location(
            "skf_scan_skill_md_structure", sibling
        )
        if spec is None or spec.loader is None:
            raise ImportError("no import spec")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod._HEADING_RE  # type: ignore[attr-defined]
    except Exception:
        return re.compile(r"^\s*(#+)\s+(.*?)\s*$")


_HEADING_RE = _load_heading_re()


# --------------------------------------------------------------------------
# Canonical Tier-1 headings (mirror step-auto-shard.md §3). Any that were
# inline before extraction must remain inline after.
# --------------------------------------------------------------------------


TIER1_HEADINGS: list[str] = [
    "Overview",
    "Quick Start",
    "Common Workflows",
    "Key API Summary",
    "Component Catalog",
    "Migration & Deprecation Warnings",
    "Key Types",
    "Architecture at a Glance",
    "CLI",
    "Scripts & Assets",
    "Manual Sections",
]


# --------------------------------------------------------------------------
# Parsing helpers
# --------------------------------------------------------------------------


class Section:
    """A Tier-2 (`## Full …`) section as a half-open line range [start, end)."""

    __slots__ = ("start", "end", "heading", "kebab")

    def __init__(self, start: int, end: int, heading: str) -> None:
        self.start = start
        self.end = end
        self.heading = heading
        self.kebab = kebab_case(heading)

    @property
    def lines(self) -> int:
        return self.end - self.start

    @property
    def blockquote(self) -> str:
        return f"> See [{self.heading}](references/{self.kebab}.md)"

    @property
    def ref_rel(self) -> str:
        return f"references/{self.kebab}.md"


def kebab_case(text: str) -> str:
    """Lowercase, collapse non-alphanumeric runs to single hyphens, trim."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def split_frontmatter(text: str) -> tuple[list[str], list[str]]:
    """Return (frontmatter_lines, body_lines).

    Frontmatter is a leading `---` … `---` block. `frontmatter_lines`
    includes both fences. When no frontmatter is present, it is empty and
    the whole file is the body.
    """
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return lines[: i + 1], lines[i + 1 :]
    return [], lines


def count_body_lines(body: list[str]) -> int:
    """Number of body lines excluding trailing blank lines."""
    end = len(body)
    while end > 0 and body[end - 1].strip() == "":
        end -= 1
    return end


def _headings(body: list[str]) -> list[tuple[int, int, str]]:
    """Return [(line_index, level, heading_text)] for every heading line."""
    out: list[tuple[int, int, str]] = []
    for idx, line in enumerate(body):
        m = _HEADING_RE.match(line)
        if m:
            out.append((idx, len(m.group(1)), m.group(2).strip()))
    return out


def find_full_sections(body: list[str]) -> list[Section]:
    """Enumerate Tier-2 `## Full …` sections in document order.

    A section spans its `## Full …` heading through the line before the next
    level-1 or level-2 heading (or EOF), so nested `###` sub-headings stay
    with their section.
    """
    heads = _headings(body)
    sections: list[Section] = []
    for hi, (idx, level, htext) in enumerate(heads):
        if level != 2:
            continue
        if not (htext == "Full" or htext.startswith("Full ")):
            continue
        end = len(body)
        for nidx, nlevel, _ in heads[hi + 1 :]:
            if nlevel <= 2:
                end = nidx
                break
        sections.append(Section(idx, end, htext))
    return sections


def present_tier1(body: list[str]) -> set[str]:
    """Set of canonical Tier-1 headings present as level-2 headings."""
    canonical = set(TIER1_HEADINGS)
    found: set[str] = set()
    for _, level, htext in _headings(body):
        if level == 2 and htext in canonical:
            found.add(htext)
    return found


def rebuild_body(body: list[str], selected: list[Section]) -> list[str]:
    """Replace each selected section's line range with its blockquote."""
    by_start = {s.start: s for s in selected}
    out: list[str] = []
    i = 0
    n = len(body)
    while i < n:
        sec = by_start.get(i)
        if sec is not None:
            out.append(sec.blockquote)
            i = sec.end
        else:
            out.append(body[i])
            i += 1
    return out


def select_sections(
    body: list[str], sections: list[Section], budget: int
) -> tuple[list[Section], list[str], int]:
    """Greedily extract largest-first until the body fits, or all are taken.

    Returns (selected, new_body, body_lines_after). `sorted(reverse=True)` is
    stable, so equal-size sections keep document order — deterministic.
    """
    candidates = sorted(sections, key=lambda s: s.lines, reverse=True)
    selected: list[Section] = []
    new_body = body
    after = count_body_lines(body)
    for sec in candidates:
        selected.append(sec)
        new_body = rebuild_body(body, selected)
        after = count_body_lines(new_body)
        if after <= budget:
            break
    return selected, new_body, after


# --------------------------------------------------------------------------
# Writing (routed through skf-atomic-write.py)
# --------------------------------------------------------------------------


def _atomic_write(target: Path, content: str) -> None:
    """Write `content` to `target` atomically via the shared atomic-write helper."""
    helper = Path(__file__).resolve().parent / "skf-atomic-write.py"
    proc = subprocess.run(
        [sys.executable, str(helper), "write", "--target", str(target)],
        input=content.encode("utf-8"),
        capture_output=True,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip() or proc.stdout.decode(
            "utf-8", "replace"
        ).strip()
        raise OSError(f"atomic write failed for {target}: {detail}")


def _section_content(body: list[str], sec: Section) -> str:
    """Section text (heading preserved), trailing blanks trimmed, one newline."""
    chunk = body[sec.start : sec.end]
    end = len(chunk)
    while end > 0 and chunk[end - 1].strip() == "":
        end -= 1
    return "\n".join(chunk[:end]) + "\n"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _emit(payload: dict, out_path: str | None) -> None:
    text = json.dumps(payload, indent=2) + "\n"
    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def _cmd_shard(args: argparse.Namespace) -> int:
    skill_md = Path(args.skill_md)
    if not skill_md.is_file():
        print(f"error: file not found: {skill_md}", file=sys.stderr)
        return 1
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot read {skill_md}: {exc}", file=sys.stderr)
        return 1

    budget: int = args.budget
    dry_run: bool = args.dry_run

    frontmatter, body = split_frontmatter(text)
    body_lines_before = count_body_lines(body)
    tier1_before = present_tier1(body)

    if args.verbose:
        print(
            f"skf-shard-body: body_lines_before={body_lines_before} budget={budget}",
            file=sys.stderr,
        )

    # --- Skip path: already within budget -----------------------------------
    if body_lines_before <= budget:
        _emit(
            {
                "action": "skip",
                "body_lines_before": body_lines_before,
                "body_lines_after": body_lines_before,
                "sections_extracted": [],
                "tier1_preserved": True,
                "tier1_missing": [],
                "xref_ok": True,
                "under_budget": True,
                "dry_run": dry_run,
                "budget": budget,
            },
            args.output,
        )
        return 0

    # --- Shard path ---------------------------------------------------------
    sections = find_full_sections(body)
    selected, new_body, body_lines_after = select_sections(body, sections, budget)

    tier1_after = present_tier1(new_body)
    tier1_missing = [
        h for h in TIER1_HEADINGS if h in tier1_before and h not in tier1_after
    ]
    tier1_preserved = not tier1_missing
    under_budget = body_lines_after <= budget

    references_dir = skill_md.parent / "references"

    # Compute the plan fully before touching disk. Only write when we have a
    # real extraction AND Tier-1 survived — never leave a half-mutated tree.
    should_write = (not dry_run) and bool(selected) and tier1_preserved
    if should_write:
        try:
            for sec in selected:
                _atomic_write(
                    references_dir / f"{sec.kebab}.md", _section_content(body, sec)
                )
            new_text = "\n".join(frontmatter + new_body) + "\n"
            _atomic_write(skill_md, new_text)
        except OSError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    blockquotes_ok = all(sec.blockquote in new_body for sec in selected)
    if should_write:
        xref_ok = blockquotes_ok and all(
            (references_dir / f"{sec.kebab}.md").is_file() for sec in selected
        )
    else:
        # dry-run, nothing-to-extract, or aborted tier1 violation
        xref_ok = blockquotes_ok and tier1_preserved

    _emit(
        {
            "action": "shard",
            "body_lines_before": body_lines_before,
            "body_lines_after": body_lines_after,
            "sections_extracted": [
                {"heading": sec.heading, "file": sec.ref_rel, "lines": sec.lines}
                for sec in selected
            ],
            "tier1_preserved": tier1_preserved,
            "tier1_missing": tier1_missing,
            "xref_ok": xref_ok,
            "under_budget": under_budget,
            "dry_run": dry_run,
            "budget": budget,
        },
        args.output,
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-shard-body",
        description=(
            "Deterministically shard an oversized SKILL.md body: extract the "
            "largest `## Full …` Tier-2 sections to references/ until the body "
            "fits under --budget, replacing each with a cross-reference "
            "blockquote, and emit a JSON report the auto-shard / validate "
            "steps consume instead of counting and splitting by hand."
        ),
    )
    parser.add_argument("skill_md", help="path to the staging SKILL.md file")
    parser.add_argument(
        "--budget",
        type=int,
        default=400,
        help="body line budget below which no shard occurs (default 400)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="compute and report the plan without writing any files",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="write JSON report to this path (default stdout)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="emit progress diagnostics to stderr",
    )
    parser.set_defaults(func=_cmd_shard)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
