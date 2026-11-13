#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Shard Body — deterministic auto-shard of an oversized SKILL.md body.

Owns the line counting, the section boundaries, the size sort, the file
writes and the blockquote replacements of `skf-create-skill`'s
`references/step-auto-shard.md` §0 (which runs it on every pass and keeps no
by-hand fallback) and `references/validate.md` §4, and of
`skf-update-skill`'s `references/body-split.md`, which
`references/verify-publish.md` §7 loads when skill-check reports
`body.max_lines` or `body.max_tokens`: counted by eye, an over-budget body
ships silently or the step halts for nothing.

What it does (single positional invocation):

  1. Split frontmatter (leading `---` … `---`) from body. Frontmatter is
     NEVER modified.
  2. Count body lines between the frontmatter close and EOF, excluding
     trailing blank lines  → `body_lines_before`, and body words: the
     parts left after splitting the body on JavaScript's `\\s` whitespace
     (`/\\s+/`), empty parts dropped → `body_words_before`: the same split
     skill-check's `body.max_tokens` estimate makes
     (`text.split(/\\s+/).filter(Boolean)`), which update-skill's write.md
     §7 holds under a budget below skill-check's limit.
  3. If `body_lines_before` <= `--budget` (default 400) and, when
     `--word-budget` is set (default 0, off), `body_words_before` <=
     `--word-budget`: emit `action: "skip"`, write nothing.
  4. Otherwise enumerate Tier-2 sections — level-2 headings whose text
     starts with `Full` (`## Full API Reference`, `## Full Type
     Definitions`, …). Each section spans its heading through the line
     before the next level-1/level-2 heading (or EOF). With
     `--skip-manual`, a section that intersects a [MANUAL] block is never
     a candidate: a block is an open marker paired with the earliest
     following close marker of the same name, read over the whole body
     (so a block opened before a section and closed after it counts, and
     a marker split across lines is found, as skf-hash-content.py reads
     them), and a marker left unpaired protects its own lines. update-skill
     inventories [MANUAL] blocks in SKILL.md only, so a moved block would
     leave its next inventory.
  5. Greedily extract one candidate at a time, re-counting after each,
     stopping the moment the body fits: lines <= `--budget` and, when set,
     words <= `--word-budget`. While the lines exceed the budget the next
     candidate is the largest by lines; once they fit, the largest by
     words (ties keep document order). If extracting every candidate
     still cannot fit, extract them all and report `under_budget: false`
     or `under_word_budget: false`. create-skill then trims Tier-1 by
     editing judgment (that fallback stays in the prompt); update-skill
     records a warning and trims nothing. With no candidate, nothing is
     written.
  6. Each extracted section is written to `references/{kebab(heading)}.md`
     (heading preserved) via `skf-atomic-write.py`, and the section in
     SKILL.md is replaced by a `> See [Title](references/…md)` blockquote.
     A file is never overwritten: when `references/{kebab}.md` already
     holds other content, or an earlier extracted section of this run took
     the name, the next free `{kebab}-2.md`, `{kebab}-3.md`, … is used (as
     skill-check's split-body names them), in document order, and the
     blockquote points at it. The rewritten SKILL.md is itself written via
     `skf-atomic-write.py`.
  7. Verify every Tier-1 heading that was inline before extraction is still
     inline (`tier1_preserved`, with `tier1_missing[]`), and every emitted
     blockquote resolves to a written reference file (`xref_ok`).

Deterministic: same input + budgets + flags → same JSON and same on-disk
result.

Output JSON (stdout, or `-o`):
  {
    "action": "skip" | "shard",
    "body_lines_before": <int>,
    "body_lines_after": <int>,
    "body_words_before": <int>,
    "body_words_after": <int>,
    "sections_extracted": [
      {"heading": "Full API Reference",
       "file": "references/full-api-reference.md",
       "lines": <int>}
    ],
    "tier1_preserved": <bool>,
    "tier1_missing": ["Overview", ...],
    "xref_ok": <bool>,
    "under_budget": <bool>,
    "under_word_budget": <bool>,   (true when --word-budget is 0)
    "dry_run": <bool>,
    "budget": <int>,
    "word_budget": <int>           (0 when off)
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
      The stderr line names the file that failed and each reference file
      already written (`already written: none` when there is none).
"""

from __future__ import annotations

import argparse
import bisect
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
# The canonical Tier-1 headings: this list is the one source, which
# step-auto-shard.md §0 relies on. Any that were inline before extraction
# must remain inline after.
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

    __slots__ = ("start", "end", "heading", "kebab", "name")

    def __init__(self, start: int, end: int, heading: str) -> None:
        self.start = start
        self.end = end
        self.heading = heading
        self.kebab = kebab_case(heading)
        # The reference file's stem: the kebab name, or a `-2`, `-3` …
        # variant `assign_names` picks so no file is overwritten.
        self.name = self.kebab

    @property
    def lines(self) -> int:
        return self.end - self.start

    @property
    def blockquote(self) -> str:
        return f"> See [{self.heading}](references/{self.name}.md)"

    @property
    def ref_rel(self) -> str:
        return f"references/{self.name}.md"


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


# JavaScript's `\s`, what skill-check's `/\s+/` splits on: tab, LF, VT, FF,
# CR, space, U+00A0, U+1680, U+2000-U+200A, U+2028, U+2029, U+202F, U+205F,
# U+3000 and U+FEFF. Python's `str.split()` differs: it also splits on
# U+001C-U+001F and U+0085, and never on U+FEFF.
_JS_WHITESPACE_RE = re.compile(
    "[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+"
)


def count_words(text: str) -> int:
    """Words in `text`: the parts a JavaScript `/\\s+/` split leaves, empty parts dropped."""
    return sum(1 for part in _JS_WHITESPACE_RE.split(text) if part)


def count_body_words(body: list[str]) -> int:
    """Number of body words (see `count_words`)."""
    return count_words("\n".join(body))


# [MANUAL] markers as skf-hash-content.py reads them for the inventory:
# whitespace-tolerant, so a marker may run across lines. `_MANUAL_LOOSE_RE`
# also catches a marker too malformed for the inventory to read.
_MANUAL_OPEN_RE = re.compile(r"<!--\s*\[MANUAL:([^\]]+)\]\s*-->")
_MANUAL_CLOSE_RE = re.compile(r"<!--\s*\[/MANUAL:([^\]]+)\]\s*-->")
_MANUAL_LOOSE_RE = re.compile(r"<!--\s*\[/?MANUAL:")


def manual_ranges(body: list[str]) -> list[tuple[int, int]]:
    """Half-open body line ranges [first, last + 1) the [MANUAL] blocks cover.

    Read over the whole body, joined, so a block opened before a section and
    closed after it, and a marker split across lines, are both found. A block
    is an open marker paired with the earliest following close marker of the
    same name, as skf-hash-content.py pairs them; an unpaired marker, or a
    marker too malformed to pair, covers its own lines.
    """
    text = "\n".join(body)
    starts: list[int] = []
    offset = 0
    for line in body:
        starts.append(offset)
        offset += len(line) + 1

    def line_of(pos: int) -> int:
        return bisect.bisect_right(starts, pos) - 1

    def span(begin: int, finish: int) -> tuple[int, int]:
        return line_of(begin), line_of(max(begin, finish - 1)) + 1

    closes = [(m.start(), m.end(), m.group(1).strip()) for m in _MANUAL_CLOSE_RE.finditer(text)]
    ranges: list[tuple[int, int]] = []
    paired: set[int] = set()
    for om in _MANUAL_OPEN_RE.finditer(text):
        name = om.group(1).strip()
        close = next((c for c in closes if c[0] >= om.end() and c[2] == name), None)
        if close is None:
            ranges.append(span(om.start(), om.end()))
        else:
            paired.add(close[0])
            ranges.append(span(om.start(), close[1]))
    for c_start, c_end, _ in closes:
        if c_start not in paired:
            ranges.append(span(c_start, c_end))
    for m in _MANUAL_LOOSE_RE.finditer(text):
        ranges.append(span(m.start(), m.end()))
    return ranges


def holds_manual(
    body: list[str], sec: "Section", ranges: list[tuple[int, int]] | None = None
) -> bool:
    """True when the section intersects a [MANUAL] block (see `manual_ranges`)."""
    if ranges is None:
        ranges = manual_ranges(body)
    return any(sec.start < last and first < sec.end for first, last in ranges)


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


def fits(lines: int, words: int, budget: int, word_budget: int) -> bool:
    """True when the body is within the line budget and, when set, the word budget."""
    return lines <= budget and (word_budget <= 0 or words <= word_budget)


def select_sections(
    body: list[str], sections: list[Section], budget: int, word_budget: int = 0
) -> tuple[list[Section], list[str], int, int]:
    """Greedily extract one section at a time until the body fits, or all are taken.

    The body fits when its lines are <= `budget` and, when `word_budget` is
    above 0, its words are <= `word_budget`. Whichever budget the body still
    exceeds picks the next section: the largest by lines while the lines
    exceed `budget`, then the largest by words. `max` keeps the first of equal
    sections, so ties go in document order: deterministic. Returns (selected,
    new_body, body_lines_after, body_words_after).
    """
    words = {sec.start: count_words("\n".join(body[sec.start : sec.end])) for sec in sections}
    remaining = list(sections)
    selected: list[Section] = []
    new_body = body
    after = count_body_lines(body)
    words_after = count_body_words(body)
    while remaining and not fits(after, words_after, budget, word_budget):
        if after > budget:
            pick = max(remaining, key=lambda s: s.lines)
        else:
            pick = max(remaining, key=lambda s: words[s.start])
        remaining.remove(pick)
        selected.append(pick)
        new_body = rebuild_body(body, selected)
        after = count_body_lines(new_body)
        words_after = count_body_words(new_body)
    return selected, new_body, after, words_after


def _same_content(path: Path, content: str) -> bool:
    try:
        return path.is_file() and path.read_text(encoding="utf-8") == content
    except (OSError, UnicodeDecodeError):
        return False


def assign_names(body: list[str], selected: list[Section], references_dir: Path) -> None:
    """Give each selected section a reference file name that overwrites nothing.

    In document order, each takes `{kebab}.md`, or the first free
    `{kebab}-2.md`, `{kebab}-3.md`, ... when that file already holds other
    content or an earlier section of this run took the name. A file that
    already holds exactly the section's content is reused.
    """
    taken: set[str] = set()
    for sec in sorted(selected, key=lambda s: s.start):
        content = _section_content(body, sec)
        n = 1
        while True:
            name = sec.kebab if n == 1 else f"{sec.kebab}-{n}"
            path = references_dir / f"{name}.md"
            if name not in taken and (not path.exists() or _same_content(path, content)):
                break
            n += 1
        sec.name = name
        taken.add(name)


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
    word_budget: int = args.word_budget
    dry_run: bool = args.dry_run

    frontmatter, body = split_frontmatter(text)
    body_lines_before = count_body_lines(body)
    body_words_before = count_body_words(body)
    tier1_before = present_tier1(body)

    if args.verbose:
        print(
            f"skf-shard-body: body_lines_before={body_lines_before} budget={budget} "
            f"body_words_before={body_words_before} word_budget={word_budget}",
            file=sys.stderr,
        )

    # --- Skip path: already within budget -----------------------------------
    if fits(body_lines_before, body_words_before, budget, word_budget):
        _emit(
            {
                "action": "skip",
                "body_lines_before": body_lines_before,
                "body_lines_after": body_lines_before,
                "body_words_before": body_words_before,
                "body_words_after": body_words_before,
                "sections_extracted": [],
                "tier1_preserved": True,
                "tier1_missing": [],
                "xref_ok": True,
                "under_budget": True,
                "under_word_budget": True,
                "dry_run": dry_run,
                "budget": budget,
                "word_budget": word_budget,
            },
            args.output,
        )
        return 0

    # --- Shard path ---------------------------------------------------------
    references_dir = skill_md.parent / "references"
    sections = find_full_sections(body)
    if args.skip_manual:
        ranges = manual_ranges(body)
        sections = [sec for sec in sections if not holds_manual(body, sec, ranges)]
    selected, new_body, body_lines_after, body_words_after = select_sections(
        body, sections, budget, word_budget
    )
    # A reference file's name never changes a count (no whitespace in it), so
    # the names are picked once the selection is final.
    assign_names(body, selected, references_dir)
    new_body = rebuild_body(body, selected)

    tier1_after = present_tier1(new_body)
    tier1_missing = [
        h for h in TIER1_HEADINGS if h in tier1_before and h not in tier1_after
    ]
    tier1_preserved = not tier1_missing
    under_budget = body_lines_after <= budget
    under_word_budget = word_budget <= 0 or body_words_after <= word_budget

    # Compute the plan fully before touching disk. Only write when we have a
    # real extraction AND Tier-1 survived — never leave a half-mutated tree.
    should_write = (not dry_run) and bool(selected) and tier1_preserved
    if should_write:
        written: list[str] = []
        try:
            for sec in selected:
                _atomic_write(
                    references_dir / f"{sec.name}.md", _section_content(body, sec)
                )
                written.append(sec.ref_rel)
            new_text = "\n".join(frontmatter + new_body) + "\n"
            _atomic_write(skill_md, new_text)
        except OSError as exc:
            print(
                f"error: {exc}; already written: {', '.join(written) or 'none'}",
                file=sys.stderr,
            )
            return 2

    blockquotes_ok = all(sec.blockquote in new_body for sec in selected)
    if should_write:
        xref_ok = blockquotes_ok and all(
            (references_dir / f"{sec.name}.md").is_file() for sec in selected
        )
    else:
        # dry-run, nothing-to-extract, or aborted tier1 violation
        xref_ok = blockquotes_ok and tier1_preserved

    _emit(
        {
            "action": "shard",
            "body_lines_before": body_lines_before,
            "body_lines_after": body_lines_after,
            "body_words_before": body_words_before,
            "body_words_after": body_words_after,
            "sections_extracted": [
                {"heading": sec.heading, "file": sec.ref_rel, "lines": sec.lines}
                for sec in selected
            ],
            "tier1_preserved": tier1_preserved,
            "tier1_missing": tier1_missing,
            "xref_ok": xref_ok,
            "under_budget": under_budget,
            "under_word_budget": under_word_budget,
            "dry_run": dry_run,
            "budget": budget,
            "word_budget": word_budget,
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
            "fits under --budget (and --word-budget, when set), replacing each "
            "with a cross-reference blockquote, and emit a JSON report the "
            "auto-shard / validate / update write steps consume instead of "
            "counting and splitting by hand."
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
        "--word-budget",
        type=int,
        default=0,
        help=(
            "body word budget (words split as JavaScript's /\\s+/ splits them, "
            "as skill-check's body.max_tokens estimate does); 0 turns it off "
            "(default 0)"
        ),
    )
    parser.add_argument(
        "--skip-manual",
        action="store_true",
        help="never move a `## Full` section that intersects a [MANUAL] block",
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
