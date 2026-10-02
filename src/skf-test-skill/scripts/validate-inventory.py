#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
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
prompt reads this verdict and owns only the HALT decision.

With --skill-package it also runs the ground-truth spot-check (coverage-check.md
§1a): it sorts the exports by name (a stable sort), samples the first, the
middle and the last (`min(3, exportsCount)` names, indices
`[0, len//2, len-1]`), and looks each sampled name up in the package's
SKILL.md and in every file the inventory's `references` list names, with
the documented-name match below. A sampled name none of them writes is a
fabricated export: the inventory is then invalid, each absent name is a
violation, and the prompt re-dispatches the subagent with them, as it does
for a schema violation. No grep runs in the prompt, so an export named
`$state` or `a.b` is never a shell variable or a regex.

Distinct from reconcile-coverage.py (coverage numerator arithmetic) and
compute-score.py (weight tables): this script only validates the *shape* of the
subagent inventory and, on success, echoes the fence-stripped parsed inventory
back so the prompt consumes it directly instead of re-parsing the raw response.

It also reports each documented item's completeness, the docs-only Export
Coverage rule: an item (one name and kind) is complete when it has a
non-empty `description` and, for a function or a method, `params` (a string
or a list, empty when the function takes none) and a non-empty
`return_type`. A missing description makes an item incomplete; it never
makes the inventory invalid. reconcile-coverage.py's docsOnly branch scores
with the same rule.

Shared helpers. The other coverage scripts load these from this file rather
than keep copies: `strip_fences` (score-signatures.py), `completeness`
(reconcile-coverage.py) and the documented-name match, `load_doc_text` and
`names_present` (reconcile-coverage.py, verify-declared-numerator.py,
load-coverage-inputs.py). A name is documented when SKILL.md or a .md file
directly in references/ writes it as a fixed string, case-sensitive, never
inside a longer identifier (the Export match rule of
skf-scan-skill-md-structure.py usage-scope): on a side where the name ends
in a letter, digit, `_` or `$`, the next character may not be one of those.
So `get` is found in `get(url)` but not in `target` or `getAll`.

CLI usage (mirrors reconcile-coverage.py):
  uv run validate-inventory.py --input <response file> [--output <inventory file>]
      [--skill-package <package folder>]
  uv run validate-inventory.py '<raw response>'                 # positional
  uv run validate-inventory.py --json-input '<raw response>'    # explicit flag
  echo '<raw response>' | uv run validate-inventory.py --stdin  # piped input

--input reads the raw response from a file (UTF-8): coverage-check.md saves
the subagent's response with the Write tool and passes its path, so a quote
or an apostrophe in a description never meets a shell. --output writes the
validated inventory object to a file (UTF-8 JSON) when it is valid, for
the steps that read it by path; an invalid inventory removes a file left
there by an earlier attempt. --skill-package names the skill package under
test (the folder that holds SKILL.md) and adds the spot-check.

Input: the subagent's RAW response text (JSON, optionally wrapped in a markdown
code fence — a leading line of three backticks with an optional language tag and
a trailing line of three backticks are stripped before parsing).

Output (stdout, one object):
  {
    "valid": <bool>,             # true only when parse + every schema check pass
    "violations": [<str>, ...],  # human-readable failures; empty when valid
    "rejectedCount": <int>,      # count of malformed exports[] entries
    "exportsCount": <int>,       # len(exports) when parsed; 0 otherwise
    "inventory": {...} | null,   # fence-stripped parsed inventory when valid; null otherwise
    "completeness": {            # present when valid
      "total": <int>,            # documented items, one per name and kind
      "complete": <int>,
      "incomplete": [{"name", "kind", "missing": ["description", "params", "return_type"]}]
    },
    "spotCheck": {               # with --skill-package, once the schema passed
      "sampled": [<name>, ...],  # the sampled names, in sample order
      "absent": [<name>, ...],   # the sampled names no file writes
      "files": [<path>, ...],    # the files read, relative to the package
      "unread": [<path>, ...]    # listed references that are missing,
    }                            # unreadable or outside the package
  }

Exit codes:
  0  inventory valid (and every sampled name found)
  1  no input provided, the --input file cannot be read, or the
     --skill-package folder holds no readable SKILL.md (usage error)
  2  inventory invalid (parse failure, schema violation or a sampled name
     absent; result JSON emitted)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

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

# Kinds whose documented item also needs its parameters and return type to
# be complete (the docs-only Export Coverage rule).
SIGNATURE_KINDS = ("function", "method")

# Characters that continue an identifier in the languages SKF documents
# (`$` for JS/TS names such as `$state`).
IDENT_CHARS = r"\w$"
_IDENT_RE = re.compile(f"[{IDENT_CHARS}]")

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


# --- Documented-name match --------------------------------------------------


def name_pattern(name):
    """Regex for `name` as a fixed string that is never part of a longer identifier.

    The guard only applies on a side where the name itself ends in an
    identifier character, so `.then` still matches inside `promise.then` and
    `Type::method` matches as written.
    """
    body = re.escape(name)
    if _IDENT_RE.match(name[0]):
        body = f"(?<![{IDENT_CHARS}])" + body
    if _IDENT_RE.match(name[-1]):
        body += f"(?![{IDENT_CHARS}])"
    return re.compile(body)


def load_doc_text(skill_package_path):
    """Concatenate SKILL.md ∪ references/*.md text for name lookups.

    Deterministic: references are read in sorted order, a references/
    subfolder does not count. Reads as UTF-8 so non-ASCII exports do not
    mojibake on Windows (cp1252 default).
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


def names_present(names, doc_text):
    """Return the sorted, de-duplicated set of `names` the doc text writes."""
    present = {n for n in names if isinstance(n, str) and n and name_pattern(n).search(doc_text)}
    return sorted(present)


# --- Spot-check -------------------------------------------------------------


def sample_names(exports):
    """The names the spot-check samples: first, middle and last after a stable sort by name.

    >>> sample_names([{"name": n} for n in ("d", "a", "c", "b", "e")])
    ['a', 'c', 'e']
    >>> sample_names([{"name": "b"}, {"name": "a"}])
    ['a', 'b']
    >>> sample_names([])
    []
    """
    named = sorted((e["name"] for e in exports or []
                    if isinstance(e, dict) and isinstance(e.get("name"), str) and e["name"]))
    picks = []
    for index in (0, len(named) // 2, len(named) - 1):
        if named and named[index] not in picks:
            picks.append(named[index])
    return picks


class PackageError(Exception):
    """The --skill-package folder holds no readable SKILL.md: exit 1."""


def _inside(path, root):
    path, root = os.path.normcase(path), os.path.normcase(root)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def spot_check(inventory, skill_package_path):
    """Look the sampled export names up in SKILL.md and the inventory's references.

    The file set is the package's SKILL.md plus each `references` entry,
    resolved against the package (a split-body skill documents some exports
    only in a reference file). A listed file that is missing, unreadable or
    resolves outside the package is not read and is named in `unread`.
    """
    root = Path(skill_package_path)
    real_root = os.path.realpath(root)
    try:
        texts = [(root / "SKILL.md").read_bytes().decode("utf-8-sig")]
    except (OSError, UnicodeDecodeError) as exc:
        raise PackageError(f"cannot read {(root / 'SKILL.md').as_posix()}: {exc}") from exc
    files, unread = ["SKILL.md"], []
    listed = inventory.get("references")
    for ref in listed if isinstance(listed, list) else []:
        if not isinstance(ref, str) or not ref.strip() or ref in files or ref in unread:
            continue
        target = os.path.realpath(root / ref)
        try:
            if not _inside(target, real_root):
                raise OSError("outside the package")
            texts.append(Path(target).read_bytes().decode("utf-8-sig"))
            files.append(ref)
        except (OSError, UnicodeDecodeError):
            unread.append(ref)
    doc_text = "\n".join(texts)
    sampled = sample_names(inventory.get("exports"))
    found = set(names_present(sampled, doc_text))
    return {
        "sampled": sampled,
        "absent": [name for name in sampled if name not in found],
        "files": files,
        "unread": unread,
    }


# --- Completeness -------------------------------------------------------------


def _filled(value):
    return isinstance(value, str) and bool(value.strip())


def missing_fields(entry):
    """The fields a documented item lacks to be complete (docs-only rule)."""
    missing = []
    if not _filled(entry.get("description")):
        missing.append("description")
    if entry.get("kind") in SIGNATURE_KINDS:
        if not isinstance(entry.get("params"), (str, list)):
            missing.append("params")
        if not _filled(entry.get("return_type")):
            missing.append("return_type")
    return missing


def completeness(exports):
    """Count complete documented items: one item per name and kind.

    An item the inventory lists twice is complete when either entry is.
    Entries without a string name or a known kind are not items.
    """
    items = {}
    for entry in exports or []:
        if not isinstance(entry, dict):
            continue
        name, kind = entry.get("name"), entry.get("kind")
        if not (isinstance(name, str) and name) or kind not in VALID_KINDS:
            continue
        missing = missing_fields(entry)
        key = (name, kind)
        if key not in items or not missing:
            items[key] = missing
    incomplete = [{"name": name, "kind": kind, "missing": missing}
                  for (name, kind), missing in items.items() if missing]
    return {
        "total": len(items),
        "complete": len(items) - len(incomplete),
        "incomplete": incomplete,
    }


# --- Validation ---------------------------------------------------------------


def validate_inventory(raw, skill_package_path=None):
    """Structural validation of the subagent inventory response, then the spot-check.

    `raw` is the raw response text. Returns the result dict documented in the
    module docstring. With `skill_package_path`, an inventory that passed the
    schema is spot-checked against the package (spot_check). Deterministic:
    identical input yields an identical verdict.
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

    checked = None
    if not violations and skill_package_path is not None:
        checked = spot_check(data, skill_package_path)
        for name in checked["absent"]:
            violations.append(
                f"spot-check: `{name}` is listed as an export, but SKILL.md and the "
                f"listed reference files never write it"
            )

    valid = not violations
    result = {
        "valid": valid,
        "violations": violations,
        "rejectedCount": rejected,
        "exportsCount": len(exports),
        "inventory": data if valid else None,
    }
    if valid:
        result["completeness"] = completeness(exports)
    if checked is not None:
        result["spotCheck"] = checked
    return result


# --- CLI --------------------------------------------------------------------


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="validate-inventory",
        description=(
            "Deterministic schema validation of the §1 subagent inventory JSON "
            "(coverage-check.md §1a). Strips wrapping fences, parses, and asserts "
            "the required-keys/types/enum/mismatch-field contract, then with "
            "--skill-package spot-checks sampled names against the package, returning "
            "{valid, violations, rejectedCount, exportsCount, inventory, completeness, spotCheck}."
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
    src.add_argument(
        "--input",
        dest="input_file",
        metavar="PATH",
        help="Read the raw subagent response from this file (UTF-8).",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="Write the validated inventory to this file when it is valid.",
    )
    parser.add_argument(
        "--skill-package",
        metavar="DIR",
        help="Spot-check sampled names against this package's SKILL.md and listed references.",
    )
    return parser


def _resolve_input(args):
    if args.stdin:
        return sys.stdin.read()
    if args.input_file is not None:
        return Path(args.input_file).read_bytes().decode("utf-8-sig")
    if args.raw_input_flag is not None:
        return args.raw_input_flag
    if args.raw_input is not None:
        return args.raw_input
    return ""


def write_json(path, payload):
    """Write `payload` as indented UTF-8 JSON with a final newline."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        raw = _resolve_input(args)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: cannot read --input {args.input_file}: {exc}", file=sys.stderr)
        return 1
    if not raw.strip():
        parser.print_usage(file=sys.stderr)
        print(
            "error: no input provided (positional arg, --json-input, --stdin or --input)",
            file=sys.stderr,
        )
        return 1

    try:
        result = validate_inventory(raw, args.skill_package)
    except PackageError as exc:
        print(f"error: --skill-package: {exc}", file=sys.stderr)
        return 1
    if args.output:
        if result["valid"]:
            write_json(args.output, result["inventory"])
        else:
            Path(args.output).unlink(missing_ok=True)
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 2


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
