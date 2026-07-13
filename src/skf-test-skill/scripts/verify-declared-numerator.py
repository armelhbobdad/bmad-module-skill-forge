#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Deterministic numerator ground-truth verifier.

Grep-and-count helper for the SKF test-skill workflow (coverage-check.md §4b
"Numerator ground-truth"). It fires only on the inflation signature
(`stats.exports_documented == effective_denominator` exactly): the numerator
equals the denominator, the tell of a documented count padded to force 100%
coverage. On that signature the declared count is not trusted — every declared
export name is greped against the skill's documentation surface and only the
names that actually appear count toward coverage.

Distinct from reconcile-coverage.py (whose scalar/stack branches grep the §1
inventory names and return only a residual missing *count*): this script greps
the full declared metadata/provenance set and enumerates the *absent* names so
§4b can list them in a High-severity gap. Both scripts share the same grep
semantics (SKILL.md ∪ sorted references/*.md, UTF-8, case-sensitive substring
containment — mirroring `grep "{name}"`) so their numerators agree.

Input schema (one JSON object):
  {
    "declaredNames": ["foo", "Bar::baz", ...],  # metadata.exports[] / provenance declared set
    "skillPackagePath": "/path/to/skill"        # SKILL.md ∪ references/*.md
  }

Output (stdout, one object):
  {
    "declared":  <int>,           # de-duplicated declared name count
    "verified":  <int>,           # declared names present in the doc surface
    "present":   [names],         # sorted
    "absent":    [names],         # sorted (declared − verified) — the gap list
    "inflated":  <bool>           # verified < declared (numerator was padded)
  }
  or {"error": ..., "code": "INVALID_INPUT"} on a schema violation.

`verified` is the numerator §4b uses for Export Coverage (it overrides the
declared count when `inflated` is true).

CLI usage (mirrors reconcile-coverage.py):
  uv run verify-declared-numerator.py '<JSON>'                  # positional
  uv run verify-declared-numerator.py --json-input '<JSON>'     # explicit flag
  cat input.json | uv run verify-declared-numerator.py --stdin  # piped input

Exit codes:
  0  — verification emitted successfully
  1  — no input / input could not be parsed as JSON
  2  — input parsed but schema/semantics invalid (error object emitted as JSON)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def make_error(message):
    return {"error": message, "code": "INVALID_INPUT"}


def load_doc_text(skill_package_path):
    """Concatenate SKILL.md ∪ references/*.md text for name-presence grepping.

    Deterministic: references are read in sorted order. Reads as UTF-8 so
    non-ASCII exports do not mojibake on Windows (cp1252 default). Mirrors
    reconcile-coverage.py.load_doc_text so the two numerators agree.
    """
    root = Path(skill_package_path)
    parts = []
    skill_md = root / "SKILL.md"
    if skill_md.is_file():
        parts.append(skill_md.read_text(encoding="utf-8"))
    refs_dir = root / "references"
    if refs_dir.is_dir():
        for ref in sorted(refs_dir.glob("*.md")):
            parts.append(ref.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _validate(inp):
    if inp is None or not isinstance(inp, dict):
        return "Input must be a JSON object"
    names = inp.get("declaredNames")
    if not isinstance(names, list) or not names:
        return "declaredNames must be a non-empty list of strings"
    if not inp.get("skillPackagePath"):
        return "skillPackagePath is required to grep SKILL.md ∪ references"
    return None


def verify(inp, doc_text=None):
    """Pure verification. `doc_text` may be injected (tests); else loaded from disk."""
    err = _validate(inp)
    if err:
        return make_error(err)

    declared_set = sorted({n for n in inp["declaredNames"] if isinstance(n, str) and n})
    if doc_text is None:
        doc_text = load_doc_text(inp["skillPackagePath"])

    present = sorted(n for n in declared_set if n in doc_text)
    absent = sorted(n for n in declared_set if n not in doc_text)

    return {
        "declared": len(declared_set),
        "verified": len(present),
        "present": present,
        "absent": absent,
        "inflated": len(present) < len(declared_set),
    }


# --- CLI --------------------------------------------------------------------


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="verify-declared-numerator",
        description=(
            "Deterministic numerator ground-truth verifier (coverage-check.md "
            "§4b). Greps the full declared export set against SKILL.md ∪ "
            "references/*.md and enumerates the present/absent names so a padded "
            "numerator is caught and the verified count replaces it."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  uv run verify-declared-numerator.py "
            "'{\"declaredNames\":[\"foo\",\"bar\"],"
            "\"skillPackagePath\":\"/path/to/skill\"}'"
        ),
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument(
        "json_input",
        nargs="?",
        help="JSON object as a positional argument (single-quote it on the shell).",
    )
    src.add_argument(
        "--json-input",
        dest="json_input_flag",
        help="JSON object passed via flag (overrides positional).",
    )
    src.add_argument(
        "--stdin",
        action="store_true",
        help="Read the JSON object from stdin.",
    )
    return parser


def _resolve_input(args):
    if args.stdin:
        return sys.stdin.read()
    if args.json_input_flag is not None:
        return args.json_input_flag
    if args.json_input is not None:
        return args.json_input
    return ""


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    raw = _resolve_input(args)
    if not raw.strip():
        parser.print_usage(file=sys.stderr)
        print(
            "error: no input provided (positional arg, --json-input, or --stdin)",
            file=sys.stderr,
        )
        return 1

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps(make_error(f"Invalid JSON: {exc.msg}"), indent=2))
        return 1

    result = verify(data)
    print(json.dumps(result, indent=2))
    if isinstance(result, dict) and result.get("code") == "INVALID_INPUT":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
