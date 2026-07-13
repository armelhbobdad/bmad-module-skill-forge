#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Deterministic schema validation of the §1 subagent inventory JSON.

Structural validator for the SKF test-skill coverage step (coverage-check.md
§1a "Schema validation" block). test-skill is a quality gate, so it must not
trust subagent output blindly: before any downstream step consumes the
documented inventory, the shape is validated. That validation is pure
structural checking — strip wrapping fences, parse JSON, assert required keys
and types, assert each export entry is a dict with a non-empty `name` and a
`kind` drawn from a fixed enum, and assert each cross-check mismatch carries its
five fields — with exactly one correct pass/fail per input and no
interpretation of meaning. It is therefore script work, not prompt work; the
prompt reads this verdict and owns the HALT decision plus the separate
grep ground-truth spot-check.

Distinct from reconcile-coverage.py (coverage numerator arithmetic) and
compute-score.py (weight tables): this script only validates the *shape* of the
subagent inventory and, on success, echoes the fence-stripped parsed inventory
back so the prompt consumes it directly instead of re-parsing the raw response.

CLI usage (mirrors reconcile-coverage.py):
  uv run validate-inventory.py '<raw response>'                 # positional
  uv run validate-inventory.py --json-input '<raw response>'    # explicit flag
  echo '<raw response>' | uv run validate-inventory.py --stdin  # piped input

Input: the subagent's RAW response text (JSON, optionally wrapped in a markdown
code fence — a leading line of three backticks with an optional language tag and
a trailing line of three backticks are stripped before parsing).

Output (stdout, one object):
  {
    "valid": <bool>,             # true only when parse + every schema check pass
    "violations": [<str>, ...],  # human-readable failures; empty when valid
    "rejectedCount": <int>,      # count of malformed exports[] entries
    "exportsCount": <int>,       # len(exports) when parsed; 0 otherwise
    "inventory": {...} | null    # fence-stripped parsed inventory when valid; null otherwise
  }

Exit codes:
  0  — inventory valid
  1  — no input provided (usage error)
  2  — inventory invalid (parse failure or schema violation; result JSON emitted)
"""

from __future__ import annotations

import argparse
import json
import re
import sys

# Fixed enum for exports[].kind — the constructs SKF documents across languages
# and skill types: JS/TS (function/class/type/constant/hook/interface/method),
# Rust public-API items (struct/enum/trait/macro, alongside the shared
# type/constant/function), and stack-composition scaffolds (adapter). Mirrors the
# enum documented in coverage-check.md §1a.
VALID_KINDS = (
    "function",
    "class",
    "type",
    "constant",
    "hook",
    "interface",
    "method",
    "struct",
    "enum",
    "trait",
    "macro",
    "adapter",
)

REQUIRED_MISMATCH_FIELDS = (
    "export",
    "skill_md_line",
    "reference_file",
    "reference_line",
    "issue",
)

_FENCE_OPEN = re.compile(r"^```[A-Za-z0-9_-]*$")
_FENCE_CLOSE = re.compile(r"^```$")


def strip_fences(text):
    """Remove a wrapping markdown code fence, matching coverage-check.md §1a step 1.

    When the first non-empty line is three backticks (optionally with a language
    tag) and the last non-empty line is three backticks, drop those two lines.
    Otherwise return the text unchanged.
    """
    lines = text.split("\n")
    non_empty_idx = [i for i, ln in enumerate(lines) if ln.strip()]
    if len(non_empty_idx) < 2:
        return text
    first, last = non_empty_idx[0], non_empty_idx[-1]
    if _FENCE_OPEN.match(lines[first].strip()) and _FENCE_CLOSE.match(lines[last].strip()):
        kept = [ln for i, ln in enumerate(lines) if i != first and i != last]
        return "\n".join(kept)
    return text


def validate_inventory(raw):
    """Pure structural validation of the subagent inventory response.

    `raw` is the raw response text. Returns the result dict documented in the
    module docstring. Deterministic: identical input yields an identical verdict.
    """
    violations = []
    inner = strip_fences(raw)
    try:
        data = json.loads(inner)
    except json.JSONDecodeError as exc:
        return {
            "valid": False,
            "violations": [f"subagent response not valid JSON: {exc.msg}"],
            "rejectedCount": 0,
            "exportsCount": 0,
            "inventory": None,
        }

    if not isinstance(data, dict):
        return {
            "valid": False,
            "violations": ["subagent response is not a JSON object"],
            "rejectedCount": 0,
            "exportsCount": 0,
            "inventory": None,
        }

    exports = data.get("exports")
    if not isinstance(exports, list):
        violations.append(
            "missing/typo: `exports` must be present and a list"
        )
        exports = []

    cross = data.get("cross_check_mismatches")
    if not isinstance(cross, list):
        violations.append(
            "missing/typo: `cross_check_mismatches` must be present and a list (may be empty)"
        )
        cross = []

    # Per-entry export validation — count rejections.
    rejected = 0
    for idx, entry in enumerate(exports):
        if not isinstance(entry, dict):
            rejected += 1
            continue
        name = entry.get("name")
        kind = entry.get("kind")
        if not (isinstance(name, str) and name):
            rejected += 1
            continue
        if kind not in VALID_KINDS:
            rejected += 1
            continue
    if rejected > 0:
        subject = "entry does" if rejected == 1 else "entries do"
        violations.append(
            f"{rejected} exports[] {subject} not match schema "
            f"(each needs a non-empty string `name` and a `kind` in "
            f"{{{', '.join(VALID_KINDS)}}})"
        )

    # Non-empty cross-check mismatch entries must carry all five fields.
    for idx, entry in enumerate(cross):
        if not isinstance(entry, dict):
            violations.append(f"cross_check_mismatches[{idx}] is not an object")
            continue
        missing = [f for f in REQUIRED_MISMATCH_FIELDS if f not in entry]
        if missing:
            violations.append(
                f"cross_check_mismatches[{idx}] missing field(s): {', '.join(missing)}"
            )

    valid = not violations
    return {
        "valid": valid,
        "violations": violations,
        "rejectedCount": rejected,
        "exportsCount": len(exports),
        "inventory": data if valid else None,
    }


# --- CLI --------------------------------------------------------------------


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="validate-inventory",
        description=(
            "Deterministic schema validation of the §1 subagent inventory JSON "
            "(coverage-check.md §1a). Strips wrapping fences, parses, and asserts "
            "the required-keys/types/enum/mismatch-field contract, returning "
            "{valid, violations, rejectedCount, exportsCount, inventory}."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument(
        "raw_input",
        nargs="?",
        help="Raw subagent response as a positional argument.",
    )
    src.add_argument(
        "--json-input",
        dest="raw_input_flag",
        help="Raw subagent response passed via flag (overrides positional).",
    )
    src.add_argument(
        "--stdin",
        action="store_true",
        help="Read the raw subagent response from stdin.",
    )
    return parser


def _resolve_input(args):
    if args.stdin:
        return sys.stdin.read()
    if args.raw_input_flag is not None:
        return args.raw_input_flag
    if args.raw_input is not None:
        return args.raw_input
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

    result = validate_inventory(raw)
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
