#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Deterministic numerator ground-truth verifier.

Lookup-and-count helper for the SKF test-skill workflow (coverage-check.md §4b
"Numerator ground-truth"). It fires only on the inflation signature
(`stats.exports_documented == effective_denominator` exactly): the numerator
equals the denominator, the tell of a documented count padded to force 100%
coverage. On that signature the declared count is not trusted: every declared
export name is looked up in the skill's documentation surface and only the
names that actually appear count toward coverage.

Distinct from reconcile-coverage.py (whose scalar/stack branches look up the §1
inventory names and return only a residual missing *count*): this script looks
up the full declared metadata/provenance set and enumerates the *absent* names so
§4b can list them in a High-severity gap. Both scripts read the same text and
match names the same way, through validate-inventory.py beside them (SKILL.md ∪
sorted references/*.md, UTF-8; the name as a fixed string, case-sensitive, never
inside a longer identifier, so `get` is not found in `target` or `getAll`), so
their numerators agree.

Input schema (one JSON object):
  {
    "declaredNames": ["foo", "Bar::baz", ...],  # metadata.exports[] / provenance declared set
    "skillPackagePath": "/path/to/skill"        # SKILL.md ∪ references/*.md
  }

or the files: --inputs <coverage-inputs.json> --skill-dir <skill package>.
--inputs reads load-coverage-inputs.py metadata's output: its `declaredNames`
and `inflationSignature`. Without the signature there is nothing to verify,
so the result is `skipped` and `inflated` is false; a caller can run the
command on every skill.

Output (stdout, one object):
  {
    "skipped":   <bool>,          # --inputs only: true when there is no inflation signature
    "declared":  <int>,           # de-duplicated declared name count
    "verified":  <int>,           # declared names present in the doc surface
    "present":   [names],         # sorted
    "absent":    [names],         # sorted (declared − verified): the gap list
    "inflated":  <bool>           # verified < declared (numerator was padded)
  }
  or {"error": ..., "code": "INVALID_INPUT"} on a schema violation.

`verified` is the numerator §4b uses for Export Coverage (it overrides the
declared count when `inflated` is true): reconcile-coverage.py --verified
reads this result. --output also writes it to a file.

CLI usage (mirrors reconcile-coverage.py):
  uv run verify-declared-numerator.py --inputs <file> --skill-dir <dir> [--output <file>]
  uv run verify-declared-numerator.py '<JSON>'                  # positional
  uv run verify-declared-numerator.py --json-input '<JSON>'     # explicit flag
  cat input.json | uv run verify-declared-numerator.py --stdin  # piped input

Exit codes:
  0  verification emitted successfully
  1  no input, input that does not parse as JSON, or an --inputs file that cannot be read
  2  input parsed but schema/semantics invalid (error object emitted as JSON)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_INVENTORY_MODULE = None


def _inventory():
    """validate-inventory.py beside this script: the name match lives there."""
    global _INVENTORY_MODULE
    if _INVENTORY_MODULE is None:
        sibling = Path(__file__).resolve().parent / "validate-inventory.py"
        spec = importlib.util.spec_from_file_location("skf_validate_inventory", sibling)
        if spec is None or spec.loader is None or not sibling.is_file():
            raise ImportError(f"validate-inventory.py not found beside {Path(__file__).name}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _INVENTORY_MODULE = module
    return _INVENTORY_MODULE


def make_error(message):
    return {"error": message, "code": "INVALID_INPUT"}


def load_doc_text(skill_package_path):
    """SKILL.md ∪ references/*.md text, as validate-inventory.py reads it."""
    return _inventory().load_doc_text(skill_package_path)


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

    present = _inventory().names_present(declared_set, doc_text)
    absent = sorted(set(declared_set) - set(present))

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
    src.add_argument(
        "--inputs",
        metavar="PATH",
        help="load-coverage-inputs.py metadata output: declaredNames and inflationSignature.",
    )
    parser.add_argument("--skill-dir", metavar="DIR",
                        help="the skill package (with --inputs): SKILL.md and references/")
    parser.add_argument("--output", metavar="PATH", help="also write the result to this file")
    return parser


def verify_from_inputs(inputs, skill_dir, doc_text=None):
    """Verify the declared set of a load-coverage-inputs.py metadata result."""
    if not isinstance(inputs, dict):
        return make_error("--inputs must hold a JSON object")
    names = inputs.get("declaredNames")
    if inputs.get("inflationSignature") is not True:
        declared = len({n for n in names if isinstance(n, str) and n}) if isinstance(names, list) else 0
        return {"skipped": True, "declared": declared, "verified": None, "present": [], "absent": [],
                "inflated": False}
    result = verify({"declaredNames": names, "skillPackagePath": skill_dir}, doc_text=doc_text)
    if result.get("code") != "INVALID_INPUT":
        result = {"skipped": False, **result}
    return result


def _resolve_input(args):
    if args.stdin:
        return sys.stdin.read()
    if args.json_input_flag is not None:
        return args.json_input_flag
    if args.json_input is not None:
        return args.json_input
    return ""


def _write_output(path, result):
    target = Path(path)
    if result.get("code") == "INVALID_INPUT":
        target.unlink(missing_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((json.dumps(result, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.inputs is not None:
        if not args.skill_dir:
            parser.error("--inputs needs --skill-dir")
        try:
            inputs = json.loads(Path(args.inputs).read_bytes().decode("utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(f"error: cannot read --inputs {args.inputs}: {exc}", file=sys.stderr)
            return 1
        result = verify_from_inputs(inputs, args.skill_dir)
    else:
        raw = _resolve_input(args)
        if not raw.strip():
            parser.print_usage(file=sys.stderr)
            print(
                "error: no input provided (positional arg, --json-input, --stdin or --inputs)",
                file=sys.stderr,
            )
            return 1

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(json.dumps(make_error(f"Invalid JSON: {exc.msg}"), indent=2))
            return 1

        result = verify(data)
    if args.output:
        _write_output(args.output, result)
    print(json.dumps(result, indent=2))
    if isinstance(result, dict) and result.get("code") == "INVALID_INPUT":
        return 2
    return 0


def _force_utf8(*streams) -> None:
    """Reconfigure stdout and stderr to UTF-8, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which cannot print every character
    of the --help text, so --help would stop with UnicodeEncodeError.
    """
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


if __name__ == "__main__":
    _force_utf8(sys.stdout, sys.stderr)
    raise SystemExit(main())
