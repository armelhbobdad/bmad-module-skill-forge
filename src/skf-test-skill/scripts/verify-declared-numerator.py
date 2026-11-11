#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Deterministic numerator ground-truth verifier.

Lookup-and-count helper for the SKF test-skill workflow (coverage-check.md
§2b, its "Numerator ground truth" paragraph; §4b records the gap). It fires
only on the inflation signature
(`stats.exports_documented == effective_denominator` exactly, or, for a
provenance map with no `::` entry, its distinct entry names number
`effective_denominator`): the numerator equals the denominator, the tell of a
documented count padded to force 100% coverage. On that signature the declared
count is not trusted: every declared export name is checked against the
validated inventory and the skill's documentation surface, and only the names
that pass both (below) count toward coverage.

A declared name counts only when the validated §1 inventory gives it an entry
and the skill's text writes it (#1068): validate-inventory.py's
`listed_names` (an entry's `name`, a `method` entry's `{owner}.{name}` and
`{owner}::{name}`, and a name a module path qualifies by its last segment, so
`cognee.add` has the entry of `add`), then its `names_present`. A name the
inventory contract gives no entry (such as one the skill writes only as a
mention, bare in running text, a bullet list or a description cell, only in a
type position, only in a sentence saying it does not cover it, only as a local
import alias or a name it says the source does not export, or only in a form
marked removed or from an earlier version) is absent however often the text
writes it. A name `moduleNames` holds (the provenance map types it `module` or
`package`, which the inventory has no kind for) counts when the text writes
it. Without an inventory (no --inventory and no `exports`) the text alone
decides, as it did before.

Distinct from reconcile-coverage.py (whose stack branch, and scalar branch
when it counts no set, return only a residual missing *count*): this script
looks up the full declared metadata/provenance set and enumerates the *absent*
names so §4b can list them in a High-severity gap. Both scripts count a name
only when the inventory gives it an entry and the text writes it (the stack
branch on a provenance basis; on a composition basis it looks library and
integration pair names up in the text alone, since they name no export the
inventory lists), and both read the same text and match names the same way,
through validate-inventory.py beside them (SKILL.md ∪ sorted references/*.md,
UTF-8; the name as a fixed string, case-sensitive, never inside a longer
identifier, so `get` is not found in `target` or `getAll`), so a name both
look up is found by both or by neither.

Input schema (one JSON object):
  {
    "declaredNames": ["foo", "Bar::baz", ...],  # metadata.exports[] / provenance declared set
    "skillPackagePath": "/path/to/skill",       # SKILL.md ∪ references/*.md
    "exports": [{"name": "foo", ...}, ...],     # optional: the validated inventory's entries
    "moduleNames": ["connectors.localfs", ...]  # optional: names the provenance map types module or package
  }

or the files: --inputs <coverage-inputs.json> --skill-dir <skill package>.
--inventory <inventory.json>, with any input, sets `exports` from the
validated inventory validate-inventory.py wrote with --output (or its whole
result, `inventory.exports`) and wins over the JSON field.
--inputs reads load-coverage-inputs.py metadata's output: its `declaredNames`,
`moduleNames` and `inflationSignature`. Without the signature there is
nothing to verify, so the result is `skipped` and `inflated` is false; a
caller can run the command on every skill.

Output (stdout, one object):
  {
    "skipped":   <bool>,          # --inputs only: true when there is no inflation signature
    "declared":  <int>,           # de-duplicated declared name count
    "verified":  <int>,           # declared names the inventory gives an entry and the doc surface writes
    "present":   [names],         # sorted
    "absent":    [names],         # sorted (declared − verified): the gap list
    "inflated":  <bool>           # verified < declared (numerator was padded)
  }
  or {"error": ..., "code": "INVALID_INPUT"} on a schema violation.

`verified` is the numerator §2c's reconcile-coverage.py call uses (it
overrides the declared count when `inflated` is true): reconcile-coverage.py
--verified reads this result. --output writes it to a file and prints only
its summary: each field as the file gives it, a list as its length, and
"output": the --output path (#1063). A refused input prints its error object
either way and removes a file left there earlier.

CLI usage (mirrors reconcile-coverage.py):
  uv run verify-declared-numerator.py --inputs <file> --skill-dir <dir> [--inventory <file>] [--output <file>]
  uv run verify-declared-numerator.py '<JSON>'                  # positional
  uv run verify-declared-numerator.py --json-input '<JSON>'     # explicit flag
  cat input.json | uv run verify-declared-numerator.py --stdin  # piped input

Exit codes:
  0  verification emitted successfully
  1  no input, input that does not parse as JSON, an --inputs file that cannot be read, or an
     --inventory file that cannot be read, is not JSON or holds no `exports` list
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
    if inp.get("exports") is not None and not isinstance(inp["exports"], list):
        return "exports must be a list (the validated inventory's entries) when present"
    if inp.get("moduleNames") is not None and not isinstance(inp["moduleNames"], list):
        return "moduleNames must be a list (the names the provenance map types module or package) when present"
    return None


def verify(inp, doc_text=None):
    """Pure verification. `doc_text` may be injected (tests); else loaded from disk."""
    err = _validate(inp)
    if err:
        return make_error(err)

    declared_set = sorted({n for n in inp["declaredNames"] if isinstance(n, str) and n})
    if doc_text is None:
        doc_text = load_doc_text(inp["skillPackagePath"])

    candidates = declared_set
    if isinstance(inp.get("exports"), list):
        # #1068: a name the inventory gives no entry is not documented, whatever the text writes.
        candidates = _inventory().listed_names(declared_set, inp["exports"], inp.get("moduleNames"))
    present = _inventory().names_present(candidates, doc_text)
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
            "§2b). Greps the full declared export set against SKILL.md ∪ "
            "references/*.md, counting a name only when the validated inventory "
            "(--inventory) gives it an entry, and enumerates the present/absent "
            "names so a padded numerator is caught and the verified count replaces it."
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
        help="load-coverage-inputs.py metadata output: declaredNames, moduleNames and inflationSignature.",
    )
    parser.add_argument("--skill-dir", metavar="DIR",
                        help="the skill package (with --inputs): SKILL.md and references/")
    parser.add_argument("--inventory", metavar="PATH",
                        help="the validated inventory file (its `exports`): a declared name counts only when it "
                             "gives the name an entry; wins over the JSON `exports`")
    parser.add_argument("--output", metavar="PATH", help="write the result to this file and print only its summary")
    return parser


def verify_from_inputs(inputs, skill_dir, doc_text=None, exports=None):
    """Verify the declared set of a load-coverage-inputs.py metadata result, against the validated inventory's
    `exports` when given."""
    if not isinstance(inputs, dict):
        return make_error("--inputs must hold a JSON object")
    names = inputs.get("declaredNames")
    if inputs.get("inflationSignature") is not True:
        declared = len({n for n in names if isinstance(n, str) and n}) if isinstance(names, list) else 0
        return {"skipped": True, "declared": declared, "verified": None, "present": [], "absent": [],
                "inflated": False}
    inp = {"declaredNames": names, "skillPackagePath": skill_dir, "moduleNames": inputs.get("moduleNames")}
    if exports is not None:
        inp["exports"] = exports
    result = verify(inp, doc_text=doc_text)
    if result.get("code") != "INVALID_INPUT":
        result = {"skipped": False, **result}
    return result


class InputFileError(Exception):
    """An input file that cannot be read, or is not the file its flag names (exit 1)."""


def _read_inventory(path):
    """The `exports` list of the validated inventory validate-inventory.py wrote (or its whole result)."""
    try:
        data = json.loads(Path(path).read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError) as exc:
        raise InputFileError(f"cannot read --inventory {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise InputFileError(f"--inventory {path} is not JSON: {exc.msg}") from exc
    if isinstance(data, dict) and isinstance(data.get("inventory"), dict):
        data = data["inventory"]  # validate-inventory.py's whole result
    if not isinstance(data, dict) or not isinstance(data.get("exports"), list):
        raise InputFileError(f"--inventory {path} holds no `exports` list")
    return data["exports"]


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


def _summary(result, output):
    """What main prints when --output holds the result: each field as the file gives it, a list as its length, and
    the file's path as `output`. coverage-check reads the counts and the absent names from the file (#1063)."""
    return {**{key: len(value) if isinstance(value, list) else value for key, value in result.items()},
            "output": output}


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.inputs is not None and not args.skill_dir:
        parser.error("--inputs needs --skill-dir")
    exports = None
    if args.inventory is not None:
        try:
            exports = _read_inventory(args.inventory)
        except InputFileError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    if args.inputs is not None:
        try:
            inputs = json.loads(Path(args.inputs).read_bytes().decode("utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(f"error: cannot read --inputs {args.inputs}: {exc}", file=sys.stderr)
            return 1
        result = verify_from_inputs(inputs, args.skill_dir, exports=exports)
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

        if exports is not None and isinstance(data, dict):
            data["exports"] = exports
        result = verify(data)
    refused = isinstance(result, dict) and result.get("code") == "INVALID_INPUT"
    if args.output:
        _write_output(args.output, result)
    print(json.dumps(result if refused or not args.output else _summary(result, args.output), indent=2))
    return 2 if refused else 0


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
