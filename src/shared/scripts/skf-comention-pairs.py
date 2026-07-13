#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Co-mention Pairs — compute compose-mode co-mention pairs from an
architecture document with the same precision guards the prompt used to run
by hand.

`detect-integrations.md` §2 (compose branch) asks the LLM to scan an
architecture markdown document for skill-name co-mentions using three
deterministic guards:

  1. Word-boundary matching (`\\b{skill_name}\\b`, case-insensitive) — no
     substring false positives (`react` must not match inside `reactive`).
  2. Section filtering — paragraphs governed by an H1/H2 header that
     normalises to one of {introduction, overview, glossary, table of
     contents, references, appendix, index} are excluded, and heading text
     itself is never a co-mention source.
  3. Two-paragraph minimum — a pair (A, B) qualifies only when at least two
     distinct body paragraphs each contain word-boundary matches for both A
     and B.

Given a fixed architecture doc and skill-name set the qualifying-pair set is
fully determined, so this belongs in a deterministic helper rather than
in-prompt regex/counting. It mirrors the co-import subprocess the code-mode
branch already delegates and the `skf-pair-intersect.py` pre-pass. The LLM
still does the semantic composition (integration-section authoring, tier
inheritance, VS-verdict parsing) — the script only emits the qualifying pairs
and their evidence paragraphs.

Subcommand:
  comention --doc <md-file-or-'-'> --skills <json-file-or-'-'>
      --doc     path to the architecture markdown document, or '-' for stdin.
      --skills  path to a JSON array of loaded skill names
                (e.g. `["react", "express"]`), or '-' for stdin.
                (--doc and --skills cannot both read from stdin.)

      Emit JSON:
        {
          "pairs": [
            {
              "a": "<skill>", "b": "<skill>",
              "paragraph_count": N,
              "evidence": [{"header": "<governing-header-or-null>",
                            "excerpt": "<collapsed paragraph text>"}, ...]
            },
            ...
          ],
          "excluded_section_count": M
        }

      Only unordered pairs (a < b lexicographically) with paragraph_count >= 2
      are emitted. `pairs[]` is sorted by paragraph_count DESC, then (a, b)
      ASC — stable, mirroring skf-pair-intersect.py. `evidence[]` is in
      document order. `excluded_section_count` is the number of DISTINCT
      excluded H1/H2 sections (by normalised header) that governed at least
      one body paragraph — a diagnostic for the caller, not a gate.

CLI examples:
  uv run skf-comention-pairs.py comention --doc arch.md --skills skills.json
  echo '["react","express"]' | uv run skf-comention-pairs.py comention \\
      --doc arch.md --skills -

Exit codes:
  0  — operation succeeded (including: no qualifying pairs → empty list)
  1  — user error (bad JSON, missing/unreadable file, both inputs on stdin,
       malformed skills array)
  2  — unexpected internal error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


# Closed exclusion set — governing H1/H2 headers that normalise to one of
# these drop their paragraphs from co-mention analysis (they typically
# enumerate all libraries without describing an integration).
EXCLUDED_HEADERS = frozenset({
    "introduction",
    "overview",
    "glossary",
    "table of contents",
    "references",
    "appendix",
    "index",
})

# ATX header line: 1-6 leading hashes followed by at least one space/tab.
# A line like `#foo` (no space) is NOT a header per CommonMark and is treated
# as body text. Capture group 1 = hashes (level), group 2 = header text.
_HEADER_RE = re.compile(r"^(#{1,6})[ \t]+(.*)$")

_EXCERPT_LIMIT = 240


class UserError(Exception):
    """A caller-facing input error → exit code 1."""


# --------------------------------------------------------------------------
# Markdown parsing
# --------------------------------------------------------------------------


def _strip_closing_hashes(text: str) -> str:
    """Remove a closed-ATX trailing run of hashes (e.g. `Overview ##`)."""
    return re.sub(r"[ \t]*#+[ \t]*$", "", text)


def normalize_header(text: str) -> str:
    """Normalise a header for exclusion-set comparison: lowercase, collapse
    internal whitespace, strip trailing punctuation."""
    t = text.strip().lower()
    t = re.sub(r"\s+", " ", t).strip()
    t = t.rstrip(".,:;!?").strip()
    return t


def parse_body_paragraphs(doc_text: str) -> list[tuple[str | None, str]]:
    """Split the document into body paragraphs, each tagged with the raw text
    of its governing (nearest-preceding) H1/H2 header (or None).

    Paragraphs are maximal runs of consecutive non-blank, non-header lines,
    separated by blank lines. Header lines of ANY level are never emitted as
    paragraphs (headings are not a co-mention source). Only H1/H2 headers
    update the governing header; H3-H6 leave it unchanged.
    """
    paragraphs: list[tuple[str | None, str]] = []
    governing: str | None = None
    buf: list[str] = []

    def _flush() -> None:
        if buf:
            text = "\n".join(buf).strip()
            if text:
                paragraphs.append((governing, text))
            buf.clear()

    for raw_line in doc_text.splitlines():
        m = _HEADER_RE.match(raw_line)
        if m is not None:
            # A header terminates the current paragraph; the header line
            # itself is not body content.
            _flush()
            level = len(m.group(1))
            header_text = _strip_closing_hashes(m.group(2)).strip()
            if level <= 2:
                governing = header_text if header_text else None
            continue
        if raw_line.strip() == "":
            _flush()
            continue
        buf.append(raw_line)
    _flush()
    return paragraphs


# --------------------------------------------------------------------------
# Co-mention analysis
# --------------------------------------------------------------------------


def _make_excerpt(text: str, limit: int = _EXCERPT_LIMIT) -> str:
    """Collapse whitespace and truncate for a stable, compact evidence quote."""
    collapsed = re.sub(r"\s+", " ", text).strip()
    if len(collapsed) > limit:
        return collapsed[: limit - 3].rstrip() + "..."
    return collapsed


def analyze(doc_text: str, skill_names: list[str]) -> dict:
    """Compute qualifying co-mention pairs and their evidence.

    Deterministic: same (doc_text, skill_names) → identical output.
    """
    names = sorted(set(skill_names))
    patterns = {
        n: re.compile(r"\b" + re.escape(n) + r"\b", re.IGNORECASE)
        for n in names
    }
    paragraphs = parse_body_paragraphs(doc_text)

    excluded_sections: set[str] = set()
    # (a, b) -> list of evidence dicts, one per qualifying paragraph
    pair_evidence: dict[tuple[str, str], list[dict]] = {}

    for governing, text in paragraphs:
        if governing is not None:
            norm = normalize_header(governing)
            if norm in EXCLUDED_HEADERS:
                excluded_sections.add(norm)
                continue
        # names is sorted, so `present` is sorted → pairs are (a < b)
        present = [n for n in names if patterns[n].search(text)]
        if len(present) < 2:
            continue
        excerpt = _make_excerpt(text)
        evidence_entry = {"header": governing, "excerpt": excerpt}
        for i in range(len(present)):
            for j in range(i + 1, len(present)):
                key = (present[i], present[j])
                pair_evidence.setdefault(key, []).append(evidence_entry)

    pairs: list[dict] = []
    for (a, b), evidence in pair_evidence.items():
        if len(evidence) >= 2:
            pairs.append({
                "a": a,
                "b": b,
                "paragraph_count": len(evidence),
                "evidence": evidence,
            })
    pairs.sort(key=lambda p: (-p["paragraph_count"], p["a"], p["b"]))

    return {
        "pairs": pairs,
        "excluded_section_count": len(excluded_sections),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _read_source(source: str, label: str) -> str:
    """Read text from a file path or stdin (if source == '-')."""
    if source == "-":
        try:
            return sys.stdin.read()
        except OSError as exc:
            raise UserError(f"failed to read {label} from stdin: {exc}") from exc
    path = Path(source)
    if not path.is_file():
        raise UserError(f"{label} file not found: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise UserError(f"failed to read {label} file {path}: {exc}") from exc


def parse_skills(raw_text: str) -> list[str]:
    """Parse and validate the --skills JSON array of non-empty strings."""
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise UserError(f"malformed JSON in --skills input: {exc}") from exc
    if not isinstance(data, list):
        raise UserError(
            "--skills input must be a JSON array of strings; "
            f"got {type(data).__name__}"
        )
    names: list[str] = []
    for idx, item in enumerate(data):
        if not isinstance(item, str) or not item:
            raise UserError(
                f"--skills[{idx}] must be a non-empty string; got {item!r}"
            )
        names.append(item)
    return names


def _cmd_comention(args: argparse.Namespace) -> int:
    if args.doc == "-" and args.skills == "-":
        raise UserError(
            "--doc and --skills cannot both read from stdin ('-')"
        )
    # Read the file-backed input first so a single stdin source stays intact.
    if args.doc == "-":
        skills_text = _read_source(args.skills, "--skills")
        doc_text = _read_source(args.doc, "--doc")
    else:
        doc_text = _read_source(args.doc, "--doc")
        skills_text = _read_source(args.skills, "--skills")
    skill_names = parse_skills(skills_text)

    result = analyze(doc_text, skill_names)
    if args.verbose:
        print(
            f"analyzed {len(set(skill_names))} distinct skill names; "
            f"{len(result['pairs'])} qualifying pairs; "
            f"{result['excluded_section_count']} excluded sections",
            file=sys.stderr,
        )
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-comention-pairs",
        description=(
            "Compute compose-mode co-mention pairs from an architecture "
            "document (detect-integrations.md §2 compose branch)."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_cm = sub.add_parser(
        "comention",
        help=(
            "emit qualifying co-mention pairs (>=2 body paragraphs, "
            "word-boundary, section-filtered) as JSON"
        ),
    )
    p_cm.add_argument(
        "--doc",
        required=True,
        help="path to the architecture markdown document, or '-' for stdin",
    )
    p_cm.add_argument(
        "--skills",
        required=True,
        help=(
            "path to a JSON array of loaded skill names, or '-' for stdin. "
            "Shape: [\"<skill>\", ...]"
        ),
    )
    p_cm.add_argument(
        "--verbose",
        action="store_true",
        help="print a one-line summary to stderr",
    )
    p_cm.set_defaults(func=_cmd_comention)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — last-resort guard → exit 2
        print(f"internal error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
