#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Signature Accuracy and Type Coverage for SKF test-skill, from checked per-file results.

coverage-check.md section 2 compares each documented signature with the
source and section 4 scores two categories from the comparison: Signature
Accuracy and Type Coverage, 22% and 14% of a contextual score. Which
signature differs is a judgment, made by a subagent that reads the source;
everything after it has one answer per input and runs here: the list of
signatures to compare, the schema check of each subagent result, the two
ratios and the gap records of the wrong signatures.

  plan   the comparisons to make. For each documented export with a
         signature (an inventory entry of any kind but `method` that carries
         `params`, `return_type` or `usage_signature`) that the source
         surface lists, grouped by source file, with the line that defines
         it in the source and the documented signature. Also the whole
         documented-signature map, for the fallback scan that has no surface
         lines yet.
  score  the categories. Reads every subagent result, checks its schema,
         and computes:
           Signature Accuracy = matching / compared * 100, where compared is
             the documented signatures the whole surface lists (the `all`
             set, with a fallback scan's exports_found) and matching those
             no result names in signature_mismatches[]: a wrong signature is
             wrong whichever set the denominator counts
           Type Coverage = documented types / total types * 100, where
             total types counts the names of the --surface-set set (the
             denominator set coverage-check section 2b picked) whose kind is
             a type kind (TYPE_KINDS: interface, type alias, enum and class,
             with a Rust struct counted as a class and a trait as an
             interface) and documented types those the inventory documents
         A category with nothing to compare scores 100 (nothing documented
         is wrong) and says so in `warnings`. Each signature mismatch of a
         compared name becomes a Critical `signature-mismatch` record in the
         gap ledger's record format (gap-ledger.py append --input reads
         --gaps-output); a mismatch a result reports for any other name (one
         the skill does not document, or the surface lacks) is listed in
         `warnings` instead, and no gap.

Inputs, all files in the run folder:
  --inventory  the validated inventory validate-inventory.py wrote (--output)
  --surface    load-coverage-inputs.py surface output: `exports[]` (name,
               kind, file, line, signatureLine) and the name `sets`;
               --surface-set picks the set (default "all"): plan's
               comparisons and score's Type Coverage
  --results    a subagent result, as the subagent returned it (a wrapping
               markdown fence is stripped), repeatable. One object, or a
               list of them:
                 {"file": "<source file>",
                  "exports_found": ["..."],     (fallback scan only)
                  "types_found": ["..."],       (fallback scan only)
                  "signature_mismatches": [
                    {"name", "line", "source_sig", "documented_sig", "issue"}]}

Rounding is compute-score.py's (JS-compatible half-up, two decimals).

Usage:
  uv run score-signatures.py plan --inventory <file> [--surface <file>] [--output <file>]
  uv run score-signatures.py score --inventory <file> --surface <file> [--surface-set <set>] \\
      --results <file> [--results <file> ...] [--output <file>] [--gaps-output <file>]

Output (stdout; --output also writes it, --gaps-output writes the records):
  plan:  {"compared": N, "files": [{"file", "checks": [{"name", "line",
          "signatureLine", "documented": {...}}]}], "documentedSignatures": {...}}
  score: {"valid": true, "signatureAccuracy", "matchingSignatures",
          "totalDocumented", "typeCoverage", "documentedTypes", "totalTypes",
          "missingTypes": [...], "mismatches": [...], "gapRecords": [...],
          "warnings": [...]}
         or {"valid": false, "violations": [...]} when a result breaks the schema

Exit codes:
  0  the result was printed
  1  an input file cannot be read or is not the JSON it should be, or the
     surface has no --surface-set set
  2  a subagent result breaks the schema (violations[] names each breach;
     nothing is written to --output or --gaps-output)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path

# Surface kinds that count toward total_types. A Rust struct is a class and a
# trait an interface; `type` is a type alias.
TYPE_KINDS = frozenset({"interface", "type", "enum", "class", "struct", "trait"})
SIGNATURE_FIELDS = ("params", "return_type", "usage_signature")
MISMATCH_FIELDS = ("name", "line", "source_sig", "documented_sig", "issue")

_INVENTORY_MODULE = None


def _inventory():
    """validate-inventory.py beside this script: the fence rule lives there."""
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


class InputError(Exception):
    """An input file that cannot be read, or is not the JSON it should be."""


def round2(value: float) -> float:
    """Round to 2 decimals with JS-compatible half-up rounding (matches compute-score.py)."""
    return math.floor(value * 100 + 0.5) / 100


def _read_text(path: str, flag: str) -> str:
    try:
        return Path(path).read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"cannot read {flag} {path}: {exc}") from exc


def _read_json(path: str, flag: str):
    try:
        return json.loads(_read_text(path, flag))
    except json.JSONDecodeError as exc:
        raise InputError(f"{flag} {path} is not JSON: {exc.msg}") from exc


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------


def load_inventory(path: str) -> list[dict]:
    data = _read_json(path, "--inventory")
    if isinstance(data, dict) and isinstance(data.get("inventory"), dict):
        data = data["inventory"]  # validate-inventory.py's whole result
    if not isinstance(data, dict) or not isinstance(data.get("exports"), list):
        raise InputError(f"--inventory {path} holds no `exports` list")
    return [e for e in data["exports"] if isinstance(e, dict)]


def load_surface(path: str, surface_set: str) -> tuple[list[str], list[dict], list[str]]:
    """(the chosen name set, every surface export record, the `all` set)."""
    data = _read_json(path, "--surface")
    sets = data.get("sets") if isinstance(data, dict) else None

    def name_set(key: str) -> list[str]:
        names = sets.get(key) if isinstance(sets, dict) else None
        if not isinstance(names, list):
            raise InputError(f"--surface {path} has no name set `{key}`")
        return [n for n in names if isinstance(n, str) and n]

    exports = data.get("exports") if isinstance(data.get("exports"), list) else []
    return name_set(surface_set), [e for e in exports if isinstance(e, dict)], name_set("all")


def check_result(item: object, where: str) -> list[str]:
    """The schema breaches of one per-file result object."""
    if not isinstance(item, dict):
        return [f"{where} is not a JSON object"]
    errors = []
    if not (isinstance(item.get("file"), str) and item["file"].strip()):
        errors.append(f"{where}: `file` must be a non-empty string")
    for key in ("exports_found", "types_found"):
        value = item.get(key)
        if value is not None and not (isinstance(value, list) and all(isinstance(v, str) for v in value)):
            errors.append(f"{where}: `{key}` must be a list of strings when present")
    mismatches = item.get("signature_mismatches")
    if not isinstance(mismatches, list):
        errors.append(f"{where}: `signature_mismatches` must be present and a list (may be empty)")
        return errors
    for i, entry in enumerate(mismatches):
        at = f"{where}.signature_mismatches[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{at} is not an object")
            continue
        missing = [f for f in MISMATCH_FIELDS if f not in entry]
        if missing:
            errors.append(f"{at} missing field(s): {', '.join(missing)}")
            continue
        line = entry["line"]
        if isinstance(line, bool) or not isinstance(line, int) or line < 1:
            errors.append(f"{at}: `line` must be a line number (an integer from 1)")
        for field in ("name", "source_sig", "documented_sig", "issue"):
            if not (isinstance(entry[field], str) and entry[field].strip()):
                errors.append(f"{at}: `{field}` must be a non-empty string")
    return errors


def parse_result_text(text: str, where: str) -> tuple[list[dict], list[str]]:
    """(the result objects, the schema breaches) of one subagent response."""
    inner = _inventory().strip_fences(text)
    try:
        data = json.loads(inner)
    except json.JSONDecodeError as exc:
        return [], [f"{where} is not valid JSON: {exc.msg}"]
    items = data if isinstance(data, list) else [data]
    errors = []
    for i, item in enumerate(items):
        errors += check_result(item, where if len(items) == 1 else f"{where}[{i}]")
    return ([] if errors else items), errors


def load_results(paths: list[str]) -> tuple[list[dict], list[str]]:
    """Every result object of the --results files, and every schema breach."""
    results, violations = [], []
    for path in paths:
        items, errors = parse_result_text(_read_text(path, "--results"), Path(path).name)
        results += items
        violations += errors
    return results, violations


# --------------------------------------------------------------------------
# Plan and score
# --------------------------------------------------------------------------


def _has_signature(entry: dict) -> bool:
    return any(
        isinstance(entry.get(f), list) or (isinstance(entry.get(f), str) and entry[f].strip())
        for f in SIGNATURE_FIELDS
    )


def documented_signatures(inventory: list[dict]) -> dict[str, dict]:
    """{name: its documented signature fields} for each documented export with one."""
    out: dict[str, dict] = {}
    for entry in inventory:
        name = entry.get("name")
        if entry.get("kind") == "method" or not (isinstance(name, str) and name) or name in out:
            continue
        if _has_signature(entry):
            out[name] = {f: entry[f] for f in SIGNATURE_FIELDS if f in entry}
    return out


def documented_names(inventory: list[dict]) -> set[str]:
    return {e["name"] for e in inventory
            if isinstance(e.get("name"), str) and e["name"] and e.get("kind") != "method"}


def _records_by_name(exports: list[dict]) -> dict[str, list[dict]]:
    by_name: dict[str, list[dict]] = {}
    for record in sorted(exports, key=lambda r: (str(r.get("file") or ""), r.get("line") or 0)):
        name = record.get("name")
        if isinstance(name, str) and name:
            by_name.setdefault(name, []).append(record)
    return by_name


def plan(inventory: list[dict], names: list[str] | None, exports: list[dict]) -> dict:
    signatures = documented_signatures(inventory)
    files: dict[str, list[dict]] = {}
    compared = 0
    if names is not None:
        by_name = _records_by_name(exports)
        for name in sorted(set(names) & set(signatures)):
            record = (by_name.get(name) or [{}])[0]
            compared += 1
            files.setdefault(str(record.get("file") or ""), []).append({
                "name": name,
                "line": record.get("line"),
                "signatureLine": record.get("signatureLine"),
                "documented": signatures[name],
            })
    return {
        "compared": compared,
        "files": [{"file": f, "checks": checks} for f, checks in sorted(files.items())],
        "documentedSignatures": signatures,
    }


def _gap_record(m: dict) -> dict:
    name, where = m["name"], f"{m['file']}:{m['line']}"
    return {
        "severity": "Critical",
        "category": "signature-mismatch",
        "title": f"Signature mismatch: {name}",
        "source": where,
        "export": name,
        "issue": f"documented `{m['documented_sig']}`, source `{m['source_sig']}`: {m['issue']}",
        "remediation": (f"Update the documented signature of `{name}` from `{m['documented_sig']}` "
                        f"to `{m['source_sig']}`, the signature the source defines at `{where}`."),
    }


def score(inventory: list[dict], names: list[str], exports: list[dict], results: list[dict],
          type_names: list[str] | None = None) -> dict:
    """The two categories: Signature Accuracy over `names` (the whole surface),
    Type Coverage over `type_names` when given, else over `names` too."""
    by_name = _records_by_name(exports)
    # A fallback scan reports its own names and types.
    fallback_types = {n for r in results for n in r.get("types_found") or []}
    surface = set(names) | {n for r in results for n in r.get("exports_found") or []}
    documented = documented_names(inventory)
    signatures = documented_signatures(inventory)
    compared = surface & set(signatures)
    warnings = []

    mismatches = []
    seen = set()
    for result in results:
        for entry in result["signature_mismatches"]:
            key = (entry["name"], result["file"], entry["line"])
            if key in seen:
                continue
            seen.add(key)
            if entry["name"] not in compared:
                warnings.append(f"{result['file']}:{entry['line']}: a signature mismatch for "
                                f"`{entry['name']}`, which is no documented signature on the source surface: "
                                "not scored, no gap")
                continue
            mismatches.append({"name": entry["name"], "file": result["file"], "line": entry["line"],
                               "source_sig": entry["source_sig"], "documented_sig": entry["documented_sig"],
                               "issue": entry["issue"]})
    mismatches.sort(key=lambda m: (m["file"], m["line"], m["name"]))

    wrong = {m["name"] for m in mismatches}
    if compared:
        signature_accuracy = round2((len(compared) - len(wrong)) / len(compared) * 100)
    else:
        signature_accuracy = 100.0
        warnings.append("no documented signature is on the source surface: Signature Accuracy has "
                        "nothing to compare and scores 100")

    def kind_of(name: str) -> str | None:
        if name in fallback_types:
            return "type"
        return next((r.get("kind") for r in by_name.get(name, []) if r.get("kind")), None)

    types = {n for n in (surface if type_names is None else set(type_names)) if kind_of(n) in TYPE_KINDS}
    documented_types = types & documented
    if types:
        type_coverage = round2(len(documented_types) / len(types) * 100)
    else:
        type_coverage = 100.0
        warnings.append("the source surface has no interface, type alias, enum or class: Type "
                        "Coverage has nothing to cover and scores 100")

    return {
        "valid": True,
        "signatureAccuracy": signature_accuracy,
        "matchingSignatures": len(compared) - len(wrong),
        "totalDocumented": len(compared),
        "typeCoverage": type_coverage,
        "documentedTypes": len(documented_types),
        "totalTypes": len(types),
        "missingTypes": sorted(types - documented),
        "mismatches": mismatches,
        "gapRecords": [_gap_record(m) for m in mismatches],
        "warnings": warnings,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _write_json(path: str, payload) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def _cmd_plan(args: argparse.Namespace) -> tuple[dict, int]:
    inventory = load_inventory(args.inventory)
    names, exports = (None, [])
    if args.surface is not None:
        names, exports, _ = load_surface(args.surface, args.surface_set)
    out = plan(inventory, names, exports)
    if args.output:
        _write_json(args.output, out)
    return out, 0


def _cmd_score(args: argparse.Namespace) -> tuple[dict, int]:
    inventory = load_inventory(args.inventory)
    chosen, exports, names = load_surface(args.surface, args.surface_set)
    results, violations = load_results(args.results or [])
    if violations:
        for path in (args.output, args.gaps_output):
            if path:
                Path(path).unlink(missing_ok=True)
        return {"valid": False, "violations": violations}, 2
    out = score(inventory, names, exports, results, None if args.surface_set == "all" else chosen)
    if args.output:
        _write_json(args.output, out)
    if args.gaps_output:
        _write_json(args.gaps_output, out["gapRecords"])
    return out, 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="score-signatures",
        description="Signature Accuracy and Type Coverage from schema-checked per-file results.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan", help="the signature comparisons for the subagents to make")
    p.add_argument("--inventory", required=True, help="the validated inventory file")
    p.add_argument("--surface", help="load-coverage-inputs.py surface output")
    p.add_argument("--surface-set", default="all", help="the surface name set (default: all)")
    p.add_argument("--output", help="also write the plan to this file")
    p.set_defaults(func=_cmd_plan)

    p = sub.add_parser("score", help="the two category scores and the mismatch gap records")
    p.add_argument("--inventory", required=True, help="the validated inventory file")
    p.add_argument("--surface", required=True, help="load-coverage-inputs.py surface output")
    p.add_argument("--surface-set", default="all",
                   help="the surface name set Type Coverage counts (default: all)")
    p.add_argument("--results", action="append", help="a subagent result file (repeatable)")
    p.add_argument("--output", help="also write the scores to this file")
    p.add_argument("--gaps-output", help="write the gap ledger records to this file")
    p.set_defaults(func=_cmd_score)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        out, code = args.func(args)
    except (InputError, ImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2))
    return code


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
    sys.exit(main())
