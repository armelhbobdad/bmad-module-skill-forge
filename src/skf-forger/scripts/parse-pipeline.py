#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Deterministic parse + validation of a forger pipeline invocation.

Pipeline Mode (references/pipeline-mode.md §1-2) turns a raw code sequence
(`BS CS[cocoindex] TS[min:80] EX`, `AN -> CS -> TS -> EX`, or an alias such as
`forge-quick cognee`) into a normalized run plan and a list of sequence
anti-patterns.
Splitting the tokens, expanding aliases against a fixed table, classifying each
bracket argument, and detecting anti-patterns (duplicates, ordering, missing
prerequisites) is set/order plumbing with exactly one correct answer per input —
so it runs here, not in the prompt. The prompt keeps only the judgment the
script cannot make: interpreting the user's freeform request into a code
sequence, and deciding whether to proceed past a warned anti-pattern.

The forger passes the user's whole invocation, so an alias may carry its
arguments after it (`forge-auto <repo-or-doc-url>`, `forge <repo-url-or-path>
<skill-name>`, `forge-quick <package-or-url>`, `maintain <skill>`) and
`--pin <version>` may appear anywhere. The alias expands, and its arguments
bind, in order, to the inputs of the alias's first workflow (ALIAS_INPUTS);
`--pin` joins them, as the Pipeline Arguments rule says. An input left
unbound is reported, because that workflow requires it and a pipeline runs
headless. A quoted argument (a path with a space) stays one token. Codes and
the bracket keywords `min` and `auto` match in any case; a bracket that starts
like `min` but is not `min:<number>` is reported as malformed instead of
passing on as a target.

The alias-expansion and anti-pattern tables mirror
`src/shared/references/pipeline-contracts.md` (the human-readable contract);
this script is the executable form the forger consumes.

CLI usage:
  uv run scripts/parse-pipeline.py 'BS CS TS EX'      # positional
  uv run scripts/parse-pipeline.py 'forge-quick cognee'
  uv run scripts/parse-pipeline.py 'forge-quick'      # exit 3: missing_args [target]
  uv run scripts/parse-pipeline.py 'forge-auto https://github.com/o/r --pin 0.2.1'
  echo 'AN -> CS -> TS -> EX' | uv run scripts/parse-pipeline.py --stdin

Output (stdout, one object):
  {
    "raw": "<input>",
    "alias": "forge" | null,          # set when the input starts with an alias
    "deprecated_alias": "deepwiki" | null,
    "removed_alias": "onboard" | null,
    "expanded": ["BS", "CS", "TS", "EX"],   # normalized tokens (post-expansion)
    "plan": [{"code","min","mode","target"}, ...],
    "codes": ["BS", "CS", "TS", "EX"],
    "args": {"<input>": "<value>", "pin": "<version>"},  # for the first workflow
    "unknown_codes": [],
    "unexpected_args": [],            # extra alias arguments, unknown flags
    "missing_args": [],               # alias inputs left unbound, e.g. "target"
    "malformed_brackets": [],         # e.g. "TS[min:80%]"
    "anti_patterns": [{"pattern","message","suggestion"}, ...],
    "valid": <bool>                   # runnable: real codes, nothing unknown,
  }                                   # unexpected, missing or malformed, not
                                      # removed

`args` holds only what the invocation gave: `project_path` (forge-auto),
`target_repo` and `skill_name` (forge), `target` (forge-quick), `skill_name`
(maintain), and `pin`. `--headless`/`-H` is Ferris's own flag, read at
activation, so it is accepted and not returned.

Exit codes:
  0  parsed, runnable (anti-patterns and a deprecated alias are warnings)
  1  no input provided (usage error)
  2  removed alias (e.g. `onboard`): the forger HALTs
  3  nothing runnable (empty, or an unknown code, an unexpected or missing
     argument or a malformed bracket): the forger names the problem and asks,
     or halts headless, before any workflow runs
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys

# Workflow codes that can appear in a pipeline. KI/WS are inline actions, not
# pipeline steps; `campaign` is a standalone workflow, not a pipeline code.
KNOWN_CODES = frozenset(
    {"SF", "AN", "BS", "CS", "QS", "SS", "US", "AS", "VS", "RA", "TS", "EX", "RS", "DS"}
)

# Only these take a `min:N`: AN as the fewest units it must confirm (the
# pipeline gate's --min) and TS as its test threshold (--threshold). CS, AS and
# VS have circuit breakers with no number to set, so on them, as on any other
# code, a `min:N` bracket is ignored (recorded as `min: null`, with a warning).
THRESHOLD_CODES = frozenset({"AN", "TS"})

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

# The arguments each alias takes after it, in order. Each names the input of
# the alias's first workflow that receives it: analyze-source's project_path,
# brief-skill's target_repo and skill_name, quick-skill's target and
# audit-skill's skill_name. Mirrors the alias forms in SKILL.md's Pipelines
# paragraph.
ALIAS_INPUTS = {
    "forge-auto": ("project_path",),
    "forge": ("target_repo", "skill_name"),
    "forge-quick": ("target",),
    "maintain": ("skill_name",),
}

# Pipeline-level flags (pipeline-contracts.md Pipeline Arguments): each takes a
# value and reaches the first workflow as the named input.
VALUE_FLAGS = {"--pin": "pin"}
# Ferris's own flag: On Activation already read it from the invocation.
IGNORED_FLAGS = frozenset({"--headless", "-H"})

_TOKEN_RE = re.compile(r"^([A-Za-z]+)(?:\[([^\]]*)\])?$")
_ARROWS = re.compile(r"->|→|—>|»")
_MIN_RE = re.compile(r"min:(\d+)", re.IGNORECASE)
# `min`, `min:`, `min=80`, `MIN:80%`: a threshold written wrong. A target such
# as `minimatch` does not match, because no `:` or `=` follows `min`.
_MIN_LIKE_RE = re.compile(r"min\s*(?:[:=]|$)", re.IGNORECASE)


def _unquote(token):
    """Drop one pair of matching quotes around a token."""
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "'\"":
        return token[1:-1]
    return token


def _tokenize(raw):
    """Split a raw invocation on whitespace and arrow separators.

    A quoted argument stays one token, without its quotes. Backslashes are
    kept as they are, so a Windows path survives; an unbalanced quote falls
    back to a plain whitespace split.
    """
    normalized = _ARROWS.sub(" ", raw)
    lexer = shlex.shlex(normalized, posix=False)
    lexer.whitespace_split = True
    lexer.commenters = ""  # a URL fragment (`#readme`) is not a comment
    try:
        tokens = list(lexer)
    except ValueError:
        return normalized.split()
    return [t for t in map(_unquote, tokens) if t]


def _split_flags(tokens):
    """Return (other tokens, args from flags, unexpected flag tokens).

    `--pin <version>` and `--pin=<version>` give `pin`. A flag with no value,
    one given twice or one the pipeline does not take is unexpected: which
    value was meant has no single answer, so the parse reports it.
    """
    rest, args, unexpected = [], {}, []
    tokens = list(tokens)
    while tokens:
        tok = tokens.pop(0)
        if not tok.startswith("-") or tok == "-":
            rest.append(tok)
            continue
        if tok in IGNORED_FLAGS:
            continue
        name, eq, value = tok.partition("=")
        if name not in VALUE_FLAGS:
            unexpected.append(tok)
            continue
        if not eq and tokens and not tokens[0].startswith("-"):
            value = tokens.pop(0)
            tok = f"{name} {value}"
        key = VALUE_FLAGS[name]
        if not value or key in args:
            unexpected.append(tok)
        else:
            args[key] = value
    return rest, args, unexpected


def _classify_bracket(code, value):
    """Return (min, mode, target, malformed) for a bracket value on a code.

    Keywords match in any case (`TS[MIN:80]`, `AN[Auto]`). `min:N` counts only
    on AN and TS; elsewhere it is recorded as `min: null`.
    """
    if value is None or value == "":
        return None, None, None, False
    m = _MIN_RE.fullmatch(value)
    if m:
        # min:N only applies to AN and TS; ignored elsewhere.
        return (int(m.group(1)) if code in THRESHOLD_CODES else None), None, None, False
    if _MIN_LIKE_RE.match(value):
        return None, None, None, True
    if value.lower() == "auto":
        return None, "auto", None, False
    return None, None, value, False


def _normalized_token(code, value):
    """The token as `expanded` lists it: keywords lower case, `min:N` as a number."""
    if value in (None, ""):
        return code
    m = _MIN_RE.fullmatch(value)
    if m:
        return f"{code}[min:{int(m.group(1))}]"
    if value.lower() == "auto":
        return f"{code}[auto]"
    return f"{code}[{value}]"


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


def _min_ignored(tokens):
    """The warning for `min:N` brackets on codes other than AN and TS."""
    return {
        "pattern": "min-ignored",
        "codes": [t.split("[", 1)[0] for t in tokens],
        "message": f"{', '.join(tokens)} is ignored: only AN (a unit count) and TS (a test threshold) take min:N",
        "suggestion": "remove it, or put the threshold on TS (TS[min:N])",
    }


def parse_pipeline(raw):
    """Parse and validate a raw pipeline invocation. Deterministic."""
    result = {
        "raw": raw,
        "alias": None,
        "deprecated_alias": None,
        "removed_alias": None,
        "expanded": [],
        "plan": [],
        "codes": [],
        "args": {},
        "unknown_codes": [],
        "unexpected_args": [],
        "missing_args": [],
        "malformed_brackets": [],
        "anti_patterns": [],
        "valid": False,
    }
    tokens, args, unexpected = _split_flags(_tokenize(raw))
    result["args"] = args
    result["unexpected_args"] = unexpected
    if not tokens:
        return result

    # A leading alias expands; the tokens after it are its arguments.
    lead = tokens[0].lower()
    if lead in REMOVED_ALIASES:
        result["removed_alias"] = lead
        return result
    alias = None
    if lead in DEPRECATED_ALIASES:
        result["deprecated_alias"] = lead
        alias = DEPRECATED_ALIASES[lead]
    elif lead in ALIASES:
        alias = lead
    if alias:
        result["alias"] = alias
        positionals = tokens[1:]
        names = ALIAS_INPUTS[alias]
        result["args"] = {**dict(zip(names, positionals)), **args}
        result["unexpected_args"] = positionals[len(names):] + unexpected
        result["missing_args"] = list(names[len(positionals):])
        tokens = list(ALIASES[alias])

    ignored_min = []
    for tok in tokens:
        m = _TOKEN_RE.match(tok)
        if not m:
            result["unknown_codes"].append(tok)
            continue
        code = m.group(1).upper()
        value = m.group(2)
        result["expanded"].append(_normalized_token(code, value))
        if code not in KNOWN_CODES:
            result["unknown_codes"].append(tok)
            continue
        min_n, mode, target, malformed = _classify_bracket(code, value)
        if malformed:
            result["malformed_brackets"].append(tok)
        elif value and _MIN_RE.fullmatch(value) and code not in THRESHOLD_CODES:
            ignored_min.append(_normalized_token(code, value))
        result["codes"].append(code)
        result["plan"].append(
            {"code": code, "min": min_n, "mode": mode, "target": target}
        )

    result["anti_patterns"] = _detect_anti_patterns(result["codes"])
    if ignored_min:
        result["anti_patterns"].append(_min_ignored(ignored_min))
    result["valid"] = (
        bool(result["codes"])
        and not result["unknown_codes"]
        and not result["unexpected_args"]
        and not result["missing_args"]
        and not result["malformed_brackets"]
    )
    return result


# --- CLI --------------------------------------------------------------------


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="parse-pipeline",
        description=(
            "Deterministic parse + validation of a forger pipeline invocation "
            "(pipeline-mode.md §1-2): tokenize, expand aliases, bind an alias's "
            "arguments to its first workflow, classify bracket arguments, and "
            "detect sequence anti-patterns, returning a normalized run plan as JSON."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument(
        "sequence",
        nargs="?",
        help="The whole pipeline invocation as a positional argument.",
    )
    src.add_argument(
        "--stdin",
        action="store_true",
        help="Read the whole pipeline invocation from stdin.",
    )
    return parser


def _resolve_input(args):
    if args.stdin:
        # A Windows console reads cp1252: the arrows and paths need UTF-8.
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8")
        return sys.stdin.read().strip()
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
    sys.exit(main())
