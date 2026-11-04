#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Signature Accuracy and Type Coverage for SKF test-skill, from checked per-file results.

coverage-check.md section 2 compares each documented signature with the
source and section 2b scores two categories from the comparison: Signature
Accuracy and Type Coverage, 22% and 14% of a contextual score. Which
signature differs is a judgment, made by a subagent that reads the source;
everything after it has one answer per input and runs here: the list of
signatures to compare, the schema check of each subagent result, the two
ratios and the gap records of the wrong signatures.

  plan   the comparisons to make. For each documented export with a
         signature (an inventory entry of any kind but `method` that carries
         `params`, `return_type` or `usage_signature`; a function's `params`
         counts when empty, its form for one that takes none) in the
         signature universe, grouped by source file, with the line that
         defines it in the source and the documented signature (with the
         entry's `signature_form` when it has one; of several entries of one
         name, one that lists parameters or gives a usage form before one
         that does neither, then a full one before a partial one, then, of
         two full or two partial forms, one that lists parameters before one
         that gives only a usage form, else the first). The signature
         universe is the surface's `all` set plus every name on its export
         records, so the names of a Python sub-package load-coverage-inputs.py
         keeps out of `all` (excluded.nestedEntries) keep their checks. A check sits at the
         name's first surface record (one with a file before one with none
         or a blank one). For a name the surface records in more than one
         file, --skill-dir (the skill package) picks the record whose file
         the skill cites on a line that names it
         (validate-inventory.py's _skill_cited_files) when exactly one of
         those files is cited; otherwise the check stays at the first record
         and lists every record with a file as `candidates` for the judge to
         read. Also the whole documented-signature map, for the fallback scan
         that has no surface lines yet.
  score  the categories. Reads every subagent result, checks its schema,
         and computes:
           Signature Accuracy = matching / compared * 100, where compared is
             the documented signatures of the signature universe (with a
             fallback scan's exports_found) and matching those no result
             names in a Critical mismatch: a wrong signature is wrong
             whichever set the denominator counts
           Type Coverage = documented types / total types * 100, where
             total types counts the names of the --surface-set set (the
             denominator set coverage-check section 2b picked) whose kind is
             a type kind (TYPE_KINDS: interface, type alias, enum and class,
             with a Rust struct counted as a class and a trait as an
             interface) and documented types those the inventory documents
         A category with nothing to compare scores 100 (nothing documented
         is wrong) and says so in `warnings`. Each signature mismatch of a
         compared name is graded (grade()) and becomes a record in the gap
         ledger's record format (gap-ledger.py append --input reads
         --gaps-output). The judge's `difference` tag alone never lowers a
         grade: the script checks the fact each one rests on.
           Low `signature-mismatch`  `difference` "parameter-name" reported
             at a file the plan offered for the name (the file it sent the
             check to, or a candidate), when that file is of a language
             whose callers cannot pass an argument by its name
             (POSITIONAL_EXTENSIONS: TS/JS, Go, Rust, Java, C, C++; never
             Python, whose positional-only parameters the script cannot see,
             nor a Vue component, whose props callers set by name)
           Info `observation`, titled `Partial signature: {name}`
             `difference` "omitted-optional" on a documented signature whose
             inventory entry is `signature_form` "partial"
           Info `observation`, titled `Annotation contradicted: {name}`
             `difference` "annotation-contradicted" (the documented return
             type is the one the body returns, the declared annotation says
             otherwise) whose facts check: the documented entry states a
             return type (a non-blank `return_type`, or a `documented_sig`
             that writes one); `documented_sig` and `source_sig` write the
             same parameters (the text before the return, whitespace runs
             read as one space); `evidence_line` comes after the
             declaration line (of the name's surface records at the
             mismatch's file, the closest at or before the mismatch's
             `line`, else the first; with none, the mismatch's `line`) and
             before the next surface record in that file; and, with
             --source-root, that line of the file under it starts with
             `return`, or is the declaration line itself with its
             expression body after its parameters (an arrow function's
             `=> expr`, a Python `def ...: return x`). Its remediation
             changes nothing in the skill: the annotation is reported
             upstream. A tagged mismatch whose facts do not check is graded
             as an untagged one, and `warnings` names the fact that failed
           Critical `signature-mismatch`  every other mismatch
         A mismatch's `file` (normalized: `/` separated, no `./`) is the file
         it is graded and recorded at (the gap's Source) when the plan
         offered that file for the name: the file of its check or one of the
         check's candidates, read from --plan, else every file the surface
         records for the name. Any other `file` is listed in `warnings`, and
         the result's `file` stands, as it does when there is none. Results
         that report one declaration (name, file and line) more than once
         keep its most severe grade: Critical, then Low, then Info. Of the
         mismatches of a check that offered several files, the least severe
         stands (the closest candidate), the first by file and line on a
         tie: one documented signature, one gap. A Low or an Info mismatch
         still counts as matching. A mismatch a result reports for any
         other name (one the skill does not document, or the surface lacks)
         is listed in `warnings` instead, and no gap.

Inputs, all files in the run folder:
  --inventory  the validated inventory validate-inventory.py wrote (--output)
  --surface    load-coverage-inputs.py surface output: `exports[]` (name,
               kind, file, line, signatureLine) and the name `sets`;
               --surface-set picks the set (default "all") score's Type
               Coverage counts, while plan and Signature Accuracy compare
               the signature universe whichever set it picks
  --results    a subagent result, as the subagent returned it (a wrapping
               markdown fence is stripped), repeatable. One object, or a
               list of them:
                 {"file": "<source file>",
                  "exports_found": ["..."],     (fallback scan only)
                  "types_found": ["..."],       (fallback scan only)
                  "signature_mismatches": [
                    {"name", "line", "source_sig", "documented_sig", "issue",
                     "difference", "file", "evidence_line"}]}
                                      (difference optional: one of
                                       DIFFERENCES, absent or null for none;
                                       file optional: the candidate the
                                       mismatch was found at, a non-empty
                                       string, absent or null for the
                                       result's `file`; evidence_line, the
                                       body line that returns the documented
                                       type, an integer from 1, required
                                       with "annotation-contradicted" and
                                       refused with any other difference)
  --skill-dir  plan only: the skill package under test (the folder that
               holds SKILL.md), whose citations pick the declaration of a
               name the surface records in several files
  --plan       score only: the plan's output, whose checks name the files a
               mismatch of each name may be recorded at
  --source-root  score only: the local source tree the judges read (a
               drifted workspace included), where an annotation-contradicted
               mismatch's `evidence_line` is checked in its file

Rounding is compute-score.py's (JS-compatible half-up, two decimals).

Usage:
  uv run score-signatures.py plan --inventory <file> [--surface <file>] [--skill-dir <dir>] [--output <file>]
  uv run score-signatures.py score --inventory <file> --surface <file> [--surface-set <set>] [--plan <file>] \\
      [--source-root <dir>] --results <file> [--results <file> ...] [--output <file>] [--gaps-output <file>]

Output (stdout; --output also writes it, --gaps-output writes the records):
  plan:  {"compared": N, "files": [{"file", "checks": [{"name", "line",
          "signatureLine", "documented": {...}, "candidates": [{"file",
          "line", "signatureLine"}] (only when the citation does not settle
          the declaration)}]}], "documentedSignatures": {...}}
  score: {"valid": true, "signatureAccuracy", "matchingSignatures",
          "totalDocumented", "comparedNames": [the names compared],
          "typeCoverage", "documentedTypes", "totalTypes",
          "missingTypes": [...], "mismatches": [{"name", "file", "line",
          "source_sig", "documented_sig", "issue", "difference" (null for
          none), "evidence_line" (with "annotation-contradicted" alone),
          "severity" (Critical, Low or Info)}], "gapRecords": [...],
          "warnings": [...]}
         or {"valid": false, "violations": [...]} when a result breaks the schema

Exit codes:
  0  the result was printed
  1  an input file cannot be read or is not the JSON it should be, the
     surface has no --surface-set set, the --skill-dir folder holds no
     readable SKILL.md, or the --source-root folder does not exist
  2  a subagent result breaks the schema (violations[] names each breach;
     nothing is written to --output or --gaps-output)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import sys
from pathlib import Path, PurePosixPath

# Surface kinds that count toward total_types. A Rust struct is a class and a
# trait an interface; `type` is a type alias.
TYPE_KINDS = frozenset({"interface", "type", "enum", "class", "struct", "trait"})
SIGNATURE_FIELDS = ("params", "return_type", "usage_signature")
MISMATCH_FIELDS = ("name", "line", "source_sig", "documented_sig", "issue")
# The optional `difference` a judge tags a mismatch with, defined in
# references/signature-comparison-rules.md (Difference tags): only the
# parameter names differ, only members the documented form leaves out that
# the source marks optional, or only a return annotation the body contradicts
# (the body returns the documented type at the mismatch's `evidence_line`).
DIFFERENCES = ("parameter-name", "omitted-optional", "annotation-contradicted")
CONTRADICTED = "annotation-contradicted"
# grade()'s default: an annotation-contradicted mismatch whose facts no one checked stays Critical.
UNCHECKED = "its facts were not checked"
# A body line that returns starts with the `return` keyword. The declaration
# line itself returns when its expression body follows its parameters: an
# arrow function assigned with `=` or `export default` (`=> expr`, not a
# `{` block), or a Python `def ...: return x`. A `type` alias's arrow is a type.
RETURN_START_RE = re.compile(r"return(?![\w$])")
ARROW_OPENER_RE = re.compile(r"(?:=|\bdefault)\s*(?:async\s*)?(?:<[^()]*>\s*)?\(")
ARROW_BODY_RE = re.compile(r"\s*(?::[^=]*)?=>\s*[^\s{]")
PYTHON_DEF_RE = re.compile(r"(?:async\s+)?def\s+\w+\s*\(")
PYTHON_BODY_RE = re.compile(r"\s*(?:->[^:]*)?:\s*return(?![\w$])")
TYPE_DECLARATION_RE = re.compile(r"(?:export\s+)?(?:declare\s+)?type\s")
# Where a signature's return type starts, with no parenthesized parameters.
RETURN_ARROW_RE = re.compile(r"->|=>|→")
# Source files of the languages with no keyword arguments, where a caller
# never writes a parameter's name: TS/JS, Go, Rust, Java, C and C++. Not
# Python, which has keyword arguments (the script cannot see which
# parameters a caller must pass by position), nor Kotlin, C#, Swift or
# Scala, which name arguments at the call, nor a Vue component, whose
# documented parameters are props callers set by name.
POSITIONAL_EXTENSIONS = frozenset({".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs",
                                   ".java", ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp"})
# The grades of a mismatch, most severe first: one declaration reported
# twice keeps the most severe.
GRADES = ("Critical", "Low", "Info")

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


def load_plan(path: str) -> dict[str, list[str]]:
    """{name: the files plan offered its check at, the planned one first,
    then its candidates'} from plan's output."""
    data = _read_json(path, "--plan")
    groups = data.get("files") if isinstance(data, dict) else None
    if not isinstance(groups, list):
        raise InputError(f"--plan {path} is not score-signatures.py plan output (no `files` list)")
    offered: dict[str, list[str]] = {}
    for group in groups:
        checks = group.get("checks") if isinstance(group, dict) else None
        for check in checks if isinstance(checks, list) else []:
            if not (isinstance(check, dict) and isinstance(check.get("name"), str)):
                continue
            files = [str(group.get("file") or "")]
            candidates = check.get("candidates")
            for candidate in candidates if isinstance(candidates, list) else []:
                file = candidate.get("file") if isinstance(candidate, dict) else None
                if isinstance(file, str) and file.strip() and file not in files:
                    files.append(file)
            offered[check["name"]] = files
    return offered


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
        if entry.get("difference") is not None and entry["difference"] not in DIFFERENCES:
            errors.append(f"{at}: `difference` must be one of {', '.join(DIFFERENCES)} when present, "
                          f"not {json.dumps(entry['difference'])}")
        # The body line that returns the documented type: the fact an annotation-contradicted mismatch rests on.
        evidence = entry.get("evidence_line")
        if entry.get("difference") == CONTRADICTED:
            if isinstance(evidence, bool) or not isinstance(evidence, int) or evidence < 1:
                errors.append(f"{at}: `evidence_line` must be a line number (an integer from 1) with `difference` "
                              f"{CONTRADICTED}, not {json.dumps(evidence)}")
        elif evidence is not None:
            errors.append(f"{at}: `evidence_line` is given only with `difference` {CONTRADICTED}, "
                          f"not {json.dumps(entry.get('difference'))}")
        # The candidate a mismatch was found at, when the plan handed the judge several.
        if entry.get("file") is not None and not (isinstance(entry["file"], str) and entry["file"].strip()):
            errors.append(f"{at}: `file` must be a non-empty string when present, not {json.dumps(entry['file'])}")
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
    """`params`, `return_type` or `usage_signature` as a list or a non-blank
    string, or, for a kind the inventory contract gives `params`
    (validate-inventory.py's SIGNATURE_KINDS), an empty `params` string: the
    form of one that takes none."""
    if entry.get("kind") in _inventory().SIGNATURE_KINDS and isinstance(entry.get("params"), str):
        return True
    return any(
        isinstance(entry.get(f), list) or (isinstance(entry.get(f), str) and entry[f].strip())
        for f in SIGNATURE_FIELDS
    )


def _partial(fields: dict) -> bool:
    return fields.get("signature_form") == "partial"


def _lists_params(fields: dict) -> bool:
    params = fields.get("params")
    return (isinstance(params, str) and bool(params.strip())) or (isinstance(params, list) and bool(params))


def _gives_usage(fields: dict) -> bool:
    """A non-blank `usage_signature` string, or a list holding one."""
    usage = fields.get("usage_signature")
    return any(isinstance(u, str) and bool(u.strip()) for u in (usage if isinstance(usage, list) else [usage]))


def _lists_members(fields: dict) -> bool:
    """A non-blank `params` string or non-empty list, or a non-blank
    `usage_signature` string or a list holding one: an entry that says what
    the name takes (a component's usage form names its props even when its
    `params` is empty)."""
    return _lists_params(fields) or _gives_usage(fields)


def _rank(fields: dict) -> tuple[bool, bool, bool]:
    """How one of several entries of a name ranks, lowest compared first."""
    return not _lists_members(fields), _partial(fields), not _lists_params(fields)


def documented_signatures(inventory: list[dict]) -> dict[str, dict]:
    """{name: its documented signature fields} for each documented export
    with one, with the entry's `signature_form` when it has one. Of several
    entries of one name, one that lists parameters or gives a usage form
    (_lists_members) is compared before one that does neither (empty or no
    `params` and no usage form: it never hides one that says what the name
    takes), then a full one (no `signature_form`, or `full`) before a
    partial one (a form the skill also gives in full is held to it), then,
    of two full or two partial forms, one that lists parameters is
    compared before one that gives only a usage form, else the first."""
    out: dict[str, dict] = {}
    for entry in inventory:
        name = entry.get("name")
        if entry.get("kind") == "method" or not (isinstance(name, str) and name) or not _has_signature(entry):
            continue
        fields = {f: entry[f] for f in SIGNATURE_FIELDS if f in entry}
        if entry.get("signature_form") is not None:
            fields["signature_form"] = entry["signature_form"]
        if name not in out or _rank(fields) < _rank(out[name]):
            out[name] = fields
    return out


def documented_names(inventory: list[dict]) -> set[str]:
    return {e["name"] for e in inventory
            if isinstance(e.get("name"), str) and e["name"] and e.get("kind") != "method"}


def _record_file(record: dict) -> str:
    """A surface record's file, "" for none or a blank one."""
    file = str(record.get("file") or "")
    return file if file.strip() else ""


def _records_by_name(exports: list[dict]) -> dict[str, list[dict]]:
    """{name: its surface records}, by file then line, a record with no file
    last: a by-eye record never stands in for the file an extraction names."""
    by_name: dict[str, list[dict]] = {}
    for record in sorted(exports, key=lambda r: (not _record_file(r), _record_file(r), r.get("line") or 0)):
        name = record.get("name")
        if isinstance(name, str) and name:
            by_name.setdefault(name, []).append(record)
    return by_name


def signature_universe(names: list[str], exports: list[dict]) -> set[str]:
    """The names whose documented signature is compared: the `all` set
    (`names`) plus every name on the surface's export records. A nested
    Python top's names leave `all` but keep their records, so a documented
    one still has its signature checked."""
    return set(names) | set(_records_by_name(exports))


def _path(file: str) -> str:
    """A path as a citation, a candidate and a surface record compare (validate-inventory.py's _cited_path)."""
    return _inventory()._cited_path(file)


def _check_at(name: str, records: list[dict], skill_dir: str | None,
              texts: list[list[str]] | None) -> tuple[dict, list[dict] | None]:
    """(the surface record the check of `name` is planned at, the candidates
    the judge reads, or None). One file among `records`: the first record.
    Several: the record whose file the skill cites on a line that names
    `name` when exactly one of them is cited (the first such record), else
    the first record, with every record that names a file as a candidate.
    `texts` is the skill's Markdown, read once (skill_markdown_lines)."""
    first = records[0] if records else {}
    filed = [r for r in records if _record_file(r)]
    if len(filed) < 2 or len({_path(_record_file(r)) for r in filed}) < 2:
        return first, None
    if skill_dir is not None:
        cited = {_path(_record_file(r)) for r in filed} & _inventory()._skill_cited_files(Path(skill_dir), name, texts)
        if len(cited) == 1:
            return next(r for r in filed if _path(_record_file(r)) in cited), None
    return first, [{"file": _record_file(r), "line": r.get("line"), "signatureLine": r.get("signatureLine")}
                   for r in filed]


def plan(inventory: list[dict], names: list[str] | None, exports: list[dict], skill_dir: str | None = None) -> dict:
    """The comparisons over the signature universe of `names` (the `all`
    set) and `exports`; none without a surface (`names` None). `skill_dir`,
    the skill package, settles which declaration a name the surface records
    in several files is compared with (_check_at)."""
    signatures = documented_signatures(inventory)
    files: dict[str, list[dict]] = {}
    compared = 0
    if names is not None:
        by_name = _records_by_name(exports)
        texts = _inventory().skill_markdown_lines(Path(skill_dir)) if skill_dir is not None else None
        for name in sorted(signature_universe(names, exports) & set(signatures)):
            record, candidates = _check_at(name, by_name.get(name) or [], skill_dir, texts)
            compared += 1
            check = {
                "name": name,
                "line": record.get("line"),
                "signatureLine": record.get("signatureLine"),
                "documented": signatures[name],
            }
            if candidates:
                check["candidates"] = candidates
            files.setdefault(_record_file(record), []).append(check)
    return {
        "compared": compared,
        "files": [{"file": f, "checks": checks} for f, checks in sorted(files.items())],
        "documentedSignatures": signatures,
    }


def _extension(file: str) -> str:
    """The lower-case extension of a source path, `/` or `\\` separated."""
    return PurePosixPath(file.replace("\\", "/")).suffix.lower()


def _offered_files(offered: dict[str, list[str]] | None, by_name: dict[str, list[dict]], name: str) -> list[str]:
    """The files a mismatch of `name` may be recorded at, the planned one
    first: the plan's check of `name` (its file, then its candidates') when
    `offered` (read from --plan) holds it, else every file the surface
    records for `name` ("" for a record with none); [] for a name the
    surface lacks (a fallback scan's exports_found name)."""
    if offered is not None and name in offered:
        return offered[name]
    files: list[str] = []
    for record in by_name.get(name) or []:
        if _record_file(record) not in files:
            files.append(_record_file(record))
    return files


def _is_offered_file(files: list[str], file: str) -> bool:
    """Whether `file` is one of `files` (_offered_files), however either writes its path."""
    return _path(file) in {_path(f) for f in files}


def _is_line(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _lines_in(exports: list[dict], file: str) -> list[int]:
    """The lines of the surface records in `file`, however either writes its path."""
    return [r["line"] for r in exports
            if _record_file(r) and _path(_record_file(r)) == _path(file) and _is_line(r.get("line"))]


def _declaration_line(by_name: dict[str, list[dict]], name: str, file: str, line: int) -> int:
    """The line `name` is declared at in `file`: of its surface records there
    (the plan's check, or the candidate it offered), the closest one at or
    before the mismatch's `line` (a name declared twice in one file), else
    the first; with none there, the mismatch's own `line`."""
    lines = _lines_in(by_name.get(name) or [], file)
    before = [at for at in lines if at <= line]
    return max(before) if before else min(lines, default=line)


def _next_declaration(exports: list[dict], file: str, line: int) -> int | None:
    """The line of the first surface record in `file` after `line`, None when there is none."""
    return min((at for at in _lines_in(exports, file) if at > line), default=None)


def _source_lines(source_root: str, file: str) -> list[str] | None:
    """The lines of `file` under `source_root`, None when it is no readable
    file there (a path that leaves the root included)."""
    root = Path(source_root).resolve()
    path = (root / file).resolve()
    try:
        path.relative_to(root)
        return path.read_bytes().decode("utf-8-sig", errors="replace").splitlines()
    except (ValueError, OSError):
        return None


def _after_parens(text: str, start: int) -> int:
    """The index past the `)` that closes the `(` at `start`, -1 when none does."""
    depth = 0
    for i in range(start, len(text)):
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        if depth == 0:
            return i + 1
    return -1


def _signature_parts(sig: str) -> tuple[str, str]:
    """(the text before the return, its whitespace runs read as one space;
    the return type it writes, "" for none) of a signature. The return
    follows the first parenthesized group (after a `->`, `=>`, `→` or `:`),
    or, with no group, the first such arrow."""
    text = sig.strip()
    end = _after_parens(text, text.find("(")) if "(" in text else -1
    if end == -1:
        arrow = RETURN_ARROW_RE.search(text)
        head, tail = (text[:arrow.start()], text[arrow.end():]) if arrow else (text, "")
    else:
        head, tail = text[:end], re.sub(r"^\s*(?:->|=>|→|:)", "", text[end:])
    return " ".join(head.split()), tail.strip().rstrip("{:").strip()


def _returns(lines: list[str], number: int, declaration_line: int) -> bool:
    """Whether line `number` (from 1) of `lines` returns: a line after the
    declaration whose text starts with the `return` keyword, or the
    declaration line itself when its own expression body follows its
    parameters there (an arrow function's `=> expr`, a Python
    `def ...: return x`). A type arrow, a callback parameter, a match arm, a
    string or a comment never does."""
    code = lines[number - 1].strip()
    if number != declaration_line:
        return bool(RETURN_START_RE.match(code))
    if TYPE_DECLARATION_RE.match(code):
        return False
    for opener, body in ((PYTHON_DEF_RE.match(code), PYTHON_BODY_RE), (ARROW_OPENER_RE.search(code), ARROW_BODY_RE)):
        end = _after_parens(code, opener.end() - 1) if opener else -1
        if end != -1 and body.match(code, end):
            return True
    return False


def contradiction_fact(entry: dict, documented: dict, file: str, declaration_line: int,
                       next_line: int | None = None, source_root: str | None = None) -> str | None:
    """The first fact an annotation-contradicted mismatch rests on that does
    not check, None when each does: the documented entry states a return
    type (a non-blank `return_type`, or a `documented_sig` that writes one);
    `documented_sig` and `source_sig` write the same parameters (the text
    before the return); `evidence_line` comes after the declaration line and
    before `next_line`, the next surface record in the file; and, with
    `source_root`, that line of `file` under it returns (_returns), which
    alone lets the declaration line itself stand."""
    evidence = entry.get("evidence_line")
    documented_params, documented_return = _signature_parts(entry["documented_sig"])
    source_params, _ = _signature_parts(entry["source_sig"])
    return_type = documented.get("return_type")
    if not (isinstance(return_type, str) and return_type.strip()) and not documented_return:
        return "the documented signature states no return type"
    if documented_params != source_params:
        return f"its parameters differ: documented `{documented_params}`, source `{source_params}`"
    if not _is_line(evidence) or evidence < declaration_line:
        return f"evidence_line {json.dumps(evidence)} is before the declaration"
    if next_line is not None and evidence >= next_line:
        return f"evidence_line {evidence} is not before the next declaration in the file, at line {next_line}"
    if source_root is None:
        return None if evidence > declaration_line else (
            f"evidence_line {evidence} is the declaration line, which only --source-root can check")
    lines = _source_lines(source_root, file)
    if lines is None:
        return f"evidence_line {evidence} is in no readable file under --source-root"
    if evidence > len(lines):
        return f"evidence_line {evidence} is past the end of the file ({len(lines)} lines)"
    if not _returns(lines, evidence, declaration_line):
        if evidence == declaration_line:
            return f"evidence_line {evidence}, the declaration line, has no expression body after its parameters"
        return f"evidence_line {evidence} does not start with `return`"
    return None


def grade(difference: str | None, file: str, documented: dict, declared: str | None = None,
          contradiction: str | None = UNCHECKED) -> str:
    """The severity of one mismatch the result reports at `file`. The judge's
    `difference` lowers it only where the script confirms the fact it rests
    on: a parameter-name difference is Low when `declared`, the file the
    plan offered the check at (else `file`), is the mismatch's file and of a
    language with no keyword arguments; an omitted-optional difference on a
    form the inventory marks partial is Info; an annotation-contradicted
    difference is Info when `contradiction`, the fact contradiction_fact
    found failing, is None; every other mismatch is Critical."""
    if difference == "parameter-name":
        at = file if declared is None else declared
        if at.replace("\\", "/") == file.replace("\\", "/") and _extension(at) in POSITIONAL_EXTENSIONS:
            return "Low"
    if difference == "omitted-optional" and _partial(documented):
        return "Info"
    if difference == CONTRADICTED and contradiction is None:
        return "Info"
    return "Critical"


def _gap_record(m: dict) -> dict:
    name, where = m["name"], f"{m['file']}:{m['line']}"
    issue = f"documented `{m['documented_sig']}`, source `{m['source_sig']}`: {m['issue']}"
    remediation = (f"Update the documented signature of `{name}` from `{m['documented_sig']}` "
                   f"to `{m['source_sig']}`, the signature the source defines at `{where}`.")
    if m["severity"] == "Info" and m["difference"] == CONTRADICTED:
        body = f"{m['file']}:{m['evidence_line']}"
        return {
            "severity": "Info",
            "category": "observation",
            "title": f"Annotation contradicted: {name}",
            "source": where,
            "export": name,
            "issue": (f"the source annotates the return of `{name}` otherwise than the skill documents, and its "
                      f"body returns the documented type at `{body}`: {issue}"),
            "remediation": (f"No change to the skill: it documents what `{name}` returns, as `{body}` shows. "
                            f"Report the return annotation at `{where}` upstream, since the body contradicts it."),
        }
    if m["severity"] == "Info":
        return {
            "severity": "Info",
            "category": "observation",
            "title": f"Partial signature: {name}",
            "source": where,
            "export": name,
            "issue": (f"the skill labels its documented form of `{name}` partial, and it leaves out only "
                      f"members the source marks optional: {issue}"),
            "remediation": (f"No change: the documented form of `{name}` is labelled partial and leaves out "
                            f"only optional members of the signature the source defines at `{where}`."),
        }
    if m["severity"] == "Low":
        issue = (f"{issue} (only the parameter names differ, and a caller of a `{_extension(m['file'])}` "
                 "file passes its arguments by position)")
    return {
        "severity": m["severity"],
        "category": "signature-mismatch",
        "title": f"Signature mismatch: {name}",
        "source": where,
        "export": name,
        "issue": issue,
        "remediation": remediation,
    }


def score(inventory: list[dict], names: list[str], exports: list[dict], results: list[dict],
          type_names: list[str] | None = None, offered: dict[str, list[str]] | None = None,
          source_root: str | None = None) -> dict:
    """The two categories: Signature Accuracy over the signature universe of
    `names` (the `all` set) and `exports`, Type Coverage over `type_names`
    when given, else over `names`. A fallback scan's exports_found join the
    universe, and `names` when no `type_names` is given. `offered` (read
    from --plan) names the files the plan offered each check at;
    `source_root` (--source-root) is the local tree an
    annotation-contradicted mismatch's `evidence_line` is checked in."""
    by_name = _records_by_name(exports)
    # A fallback scan reports its own names and types.
    fallback_types = {n for r in results for n in r.get("types_found") or []}
    surface = set(names) | {n for r in results for n in r.get("exports_found") or []}
    documented = documented_names(inventory)
    signatures = documented_signatures(inventory)
    compared = (surface | signature_universe(names, exports)) & set(signatures)
    warnings = []

    graded: dict[tuple, dict] = {}
    seen = set()
    for result in results:
        for entry in result["signature_mismatches"]:
            name = entry["name"]
            files = _offered_files(offered, by_name, name)
            # A mismatch found at one of a check's candidates names that file; any other file is not taken.
            file = result["file"]
            if entry.get("file") is not None:
                if _is_offered_file(files, entry["file"]):
                    file = entry["file"]
                elif name in compared:
                    warnings.append(f"{result['file']}:{entry['line']}: a signature mismatch for `{name}` names "
                                    f"`{entry['file']}`, no file the plan offered its check at: recorded at "
                                    "the result's file")
            file = _path(file)
            key = (name, file, entry["line"])
            if name not in compared:
                if key not in seen:
                    warnings.append(f"{file}:{entry['line']}: a signature mismatch for "
                                    f"`{name}`, which is no documented signature on the source surface: "
                                    "not scored, no gap")
                seen.add(key)
                continue
            difference = entry.get("difference")
            # Graded at the file only when the plan offered it: never Low at a namesake it did not offer.
            declared = (file if _is_offered_file(files, file) else files[0]) if files else None
            # The facts of an annotation-contradicted mismatch, checked once and handed to grade().
            fact = None
            if difference == CONTRADICTED:
                at_line = _declaration_line(by_name, name, file, entry["line"])
                fact = contradiction_fact(entry, signatures[name], file, at_line,
                                          _next_declaration(exports, file, at_line), source_root)
                warning = (f"{file}:{at_line}: the mismatch for `{name}` is tagged {CONTRADICTED}, but {fact}: "
                           "graded as an untagged mismatch (Critical)")
                if fact is not None and warning not in warnings:
                    warnings.append(warning)
            severity = grade(difference, file, signatures[name], declared, fact)
            # Every entry is graded: one declaration reported twice keeps its most severe grade.
            if key in graded and GRADES.index(graded[key]["severity"]) <= GRADES.index(severity):
                continue
            graded[key] = {"name": name, "file": file, "line": entry["line"],
                           "source_sig": entry["source_sig"], "documented_sig": entry["documented_sig"],
                           "issue": entry["issue"], "difference": difference, "severity": severity}
            if difference == CONTRADICTED:
                graded[key]["evidence_line"] = entry.get("evidence_line")
    # A check that offered several files keeps one mismatch, its least severe (the closest candidate).
    mismatches, closest = [], {}
    for m in sorted(graded.values(), key=lambda m: (m["file"], m["line"], m["name"])):
        if len({_path(f) for f in _offered_files(offered, by_name, m["name"])}) < 2:
            mismatches.append(m)
        elif m["name"] not in closest or GRADES.index(m["severity"]) > GRADES.index(closest[m["name"]]["severity"]):
            closest[m["name"]] = m
    mismatches = sorted(mismatches + list(closest.values()), key=lambda m: (m["file"], m["line"], m["name"]))

    # A Low or an Info mismatch is a caller-invisible difference: it still matches.
    wrong = {m["name"] for m in mismatches if m["severity"] == "Critical"}
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
        "comparedNames": sorted(compared),
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
        _, exports, names = load_surface(args.surface, args.surface_set)
    if args.skill_dir is not None:
        if not args.skill_dir.strip():
            raise InputError("--skill-dir is empty: pass the skill package (the folder that holds SKILL.md)")
        _read_text(str(Path(args.skill_dir) / "SKILL.md"), "--skill-dir")
    out = plan(inventory, names, exports, args.skill_dir)
    if args.output:
        _write_json(args.output, out)
    return out, 0


def _cmd_score(args: argparse.Namespace) -> tuple[dict, int]:
    if args.source_root is not None and not (args.source_root.strip() and Path(args.source_root).is_dir()):
        raise InputError(f"--source-root {args.source_root!r} is no folder: pass the local source tree the judges read")
    inventory = load_inventory(args.inventory)
    chosen, exports, names = load_surface(args.surface, args.surface_set)
    results, violations = load_results(args.results or [])
    if violations:
        for path in (args.output, args.gaps_output):
            if path:
                Path(path).unlink(missing_ok=True)
        return {"valid": False, "violations": violations}, 2
    offered = load_plan(args.plan) if args.plan is not None else None
    out = score(inventory, names, exports, results, None if args.surface_set == "all" else chosen, offered,
                args.source_root)
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
    p.add_argument("--surface-set", default="all",
                   help="a surface name set, which must exist (default: all); the plan compares the signature "
                        "universe whichever set it names")
    p.add_argument("--skill-dir", help="the skill package under test: its citations pick the declaration of a name "
                                       "the surface records in several files")
    p.add_argument("--output", help="also write the plan to this file")
    p.set_defaults(func=_cmd_plan)

    p = sub.add_parser("score", help="the two category scores and the mismatch gap records")
    p.add_argument("--inventory", required=True, help="the validated inventory file")
    p.add_argument("--surface", required=True, help="load-coverage-inputs.py surface output")
    p.add_argument("--surface-set", default="all",
                   help="the surface name set Type Coverage counts (default: all)")
    p.add_argument("--plan", help="the plan's output: the files each check offered a mismatch at")
    p.add_argument("--source-root", help="the local source tree the judges read: an annotation-contradicted "
                                         "mismatch's evidence_line must start with `return` there, or be the "
                                         "declaration line with its expression body")
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
