#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Deterministic parse + validation of a forger pipeline invocation.

Pipeline Mode (references/pipeline-mode.md §1-2) turns a raw code sequence
(`BS CS[cocoindex] TS[min:80] EX`, `AN -> CS -> TS -> EX`, or a bare alias like
`forge-auto`) into a normalized run plan and a list of sequence anti-patterns.
Splitting the tokens, expanding aliases against a fixed table, classifying each
bracket argument, and detecting anti-patterns (duplicates, ordering, missing
prerequisites) is set/order plumbing with exactly one correct answer per input —
so it runs here, not in the prompt. The prompt keeps only the judgment the
script cannot make: interpreting the user's freeform request into a code
sequence, and deciding whether to proceed past a warned anti-pattern.

The alias-expansion and anti-pattern tables mirror
`src/shared/references/pipeline-contracts.md` (the human-readable contract);
this script is the executable form the forger consumes.

CLI usage:
  uv run scripts/parse-pipeline.py 'BS CS TS EX'      # positional
  uv run scripts/parse-pipeline.py 'forge-auto'       # bare alias
  echo 'AN -> CS -> TS -> EX' | uv run scripts/parse-pipeline.py --stdin

Output (stdout, one object):
  {
    "raw": "<input>",
    "alias": "forge" | null,          # set when the input was a lone alias
    "deprecated_alias": "deepwiki" | null,
    "removed_alias": "onboard" | null,
    "expanded": ["BS", "CS", "TS", "EX"],   # normalized tokens (post-expansion)
    "plan": [{"code","min","mode","target"}, ...],
    "codes": ["BS", "CS", "TS", "EX"],
    "unknown_codes": [],
    "anti_patterns": [{"pattern","message","suggestion"}, ...],
    "valid": <bool>                   # runnable: real codes, no unknowns, not removed
  }

Exit codes:
  0  — parsed, runnable (anti-patterns and a deprecated alias are warnings)
  1  — no input provided (usage error)
  2  — removed alias (e.g. `onboard`) — the forger HALTs
  3  — nothing runnable (empty, or unknown codes) — the forger corrects course
"""

from __future__ import annotations

import argparse
import json
import re
import sys

# Workflow codes that can appear in a pipeline. KI/WS are inline actions, not
# pipeline steps; `campaign` is a standalone workflow, not a pipeline code.
KNOWN_CODES = frozenset(
    {"SF", "AN", "BS", "CS", "QS", "SS", "US", "AS", "VS", "RA", "TS", "EX", "RS", "DS"}
)

# Only these accept a `min:N` circuit-breaker override; on other codes a
# `min:N` bracket is ignored (recorded as `min: null`).
CIRCUIT_BREAKER_CODES = frozenset({"AN", "CS", "TS", "AS", "VS"})

# Alias table — mirrors pipeline-contracts.md. `forge-auto`'s TS[min:90] gate is
# non-default and is kept in lockstep with init.md §1b's forge-auto → 90 lookup.
ALIASES = {
    "forge-auto": ["AN[auto]", "BS[auto]", "CS", "TS[min:90]", "EX"],
    "forge": ["BS", "CS", "TS", "EX"],
    "forge-quick": ["QS", "TS", "EX"],
    "maintain": ["AS", "US", "TS", "EX"],
}
DEPRECATED_ALIASES = {"deepwiki": "forge-auto"}  # renamed; still expands
REMOVED_ALIASES = {"onboard"}  # no expansion — the forger HALTs

_TOKEN_RE = re.compile(r"^([A-Za-z]+)(?:\[([^\]]*)\])?$")
_ARROWS = re.compile(r"->|→|—>|»")


def _tokenize(raw):
    """Split a raw sequence on whitespace and arrow separators."""
    normalized = _ARROWS.sub(" ", raw)
    return [t for t in normalized.split() if t]


def _classify_bracket(code, value):
    """Return (min, mode, target) for a bracket value on a given code."""
    if value is None or value == "":
        return None, None, None
    m = re.fullmatch(r"min:(\d+)", value)
    if m:
        # min:N only applies to circuit-breaker codes; ignored elsewhere.
        return (int(m.group(1)) if code in CIRCUIT_BREAKER_CODES else None), None, None
    if value == "auto":
        return None, "auto", None
    return None, None, value


def _detect_anti_patterns(codes):
    """Deterministic sequence checks — mirrors pipeline-contracts.md."""
    found = []

    # Duplicate codes.
    seen = set()
    dupes = []
    for c in codes:
        if c in seen and c not in dupes:
            dupes.append(c)
        seen.add(c)
    if dupes:
        found.append(
            {
                "pattern": "duplicate-codes",
                "codes": dupes,
                "message": f"same workflow appears more than once: {', '.join(dupes)}",
                "suggestion": "remove the duplicate",
            }
        )

    # EX before TS (equivalently, TS after EX).
    ex_idxs = [i for i, c in enumerate(codes) if c == "EX"]
    ts_idxs = [i for i, c in enumerate(codes) if c == "TS"]
    if ex_idxs and ts_idxs and min(ex_idxs) < max(ts_idxs):
        found.append(
            {
                "pattern": "ex-before-ts",
                "codes": ["EX", "TS"],
                "message": "EX (export) runs before TS (test) — exporting an untested skill",
                "suggestion": "move TS before EX",
            }
        )

    # CS without BS or AN.
    if "CS" in codes and "BS" not in codes and "AN" not in codes:
        found.append(
            {
                "pattern": "cs-without-brief",
                "codes": ["CS"],
                "message": "CS (compile) has no preceding BS or AN — compiling without a brief",
                "suggestion": "use QS for the quick path, or add AN/BS to produce a brief",
            }
        )

    # US without AS.
    if "US" in codes and "AS" not in codes:
        found.append(
            {
                "pattern": "us-without-audit",
                "codes": ["US"],
                "message": "US (update) has no preceding AS — updating without an audit",
                "suggestion": "run AS first to detect what changed",
            }
        )

    return found


def parse_pipeline(raw):
    """Parse and validate a raw pipeline sequence. Deterministic."""
    tokens = _tokenize(raw)
    result = {
        "raw": raw,
        "alias": None,
        "deprecated_alias": None,
        "removed_alias": None,
        "expanded": [],
        "plan": [],
        "codes": [],
        "unknown_codes": [],
        "anti_patterns": [],
        "valid": False,
    }
    if not tokens:
        return result

    # Alias handling — only when the sequence is a lone alias token.
    if len(tokens) == 1:
        lone = tokens[0].lower()
        if lone in REMOVED_ALIASES:
            result["removed_alias"] = lone
            return result
        if lone in DEPRECATED_ALIASES:
            result["deprecated_alias"] = lone
            target = DEPRECATED_ALIASES[lone]
            result["alias"] = target
            tokens = list(ALIASES[target])
        elif lone in ALIASES:
            result["alias"] = lone
            tokens = list(ALIASES[lone])

    result["expanded"] = []
    for tok in tokens:
        m = _TOKEN_RE.match(tok)
        if not m:
            result["unknown_codes"].append(tok)
            continue
        code = m.group(1).upper()
        value = m.group(2)
        result["expanded"].append(
            f"{code}[{value}]" if value not in (None, "") else code
        )
        if code not in KNOWN_CODES:
            result["unknown_codes"].append(tok)
            continue
        min_n, mode, target = _classify_bracket(code, value)
        result["codes"].append(code)
        result["plan"].append(
            {"code": code, "min": min_n, "mode": mode, "target": target}
        )

    result["anti_patterns"] = _detect_anti_patterns(result["codes"])
    result["valid"] = bool(result["codes"]) and not result["unknown_codes"]
    return result


# --- CLI --------------------------------------------------------------------


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="parse-pipeline",
        description=(
            "Deterministic parse + validation of a forger pipeline invocation "
            "(pipeline-mode.md §1-2): tokenize, expand aliases, classify bracket "
            "arguments, and detect sequence anti-patterns, returning a normalized "
            "run plan as JSON."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument(
        "sequence",
        nargs="?",
        help="Raw pipeline sequence as a positional argument.",
    )
    src.add_argument(
        "--stdin",
        action="store_true",
        help="Read the raw sequence from stdin.",
    )
    return parser


def _resolve_input(args):
    if args.stdin:
        return sys.stdin.read()
    if args.sequence is not None:
        return args.sequence
    return ""


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    raw = _resolve_input(args)
    if not raw.strip():
        parser.print_usage(file=sys.stderr)
        print("error: no input provided (positional arg or --stdin)", file=sys.stderr)
        return 1

    result = parse_pipeline(raw)
    print(json.dumps(result, indent=2))
    if result["removed_alias"]:
        return 2
    if not result["valid"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
