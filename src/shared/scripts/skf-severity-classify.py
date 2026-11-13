# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Severity Classify: rule-based severity classification for drift findings.

Applies the severity rules of audit-skill's references/severity-rules.md to a
list of drift findings and computes an overall drift score. Used by
audit-skill (severity-classify step).

CLI:
  python3 skf-severity-classify.py findings.json [-o result.json]
  python3 skf-severity-classify.py - < findings.json
  python3 skf-severity-classify.py --from-diff structural-diff.json [-o findings.json]
  python3 skf-severity-classify.py [--from-diff DIFF] [--file-drift FILE] [--constituents FILE]
                                   [--semantic FILE] [--doc-drift FILE]
                                   [--set-category INDEX=CATEGORY]...
                                   [--pair-move REMOVED_INDEX ADDED_INDEX]...
                                   [-o findings.json]
  python3 skf-severity-classify.py --rules [--format json|markdown]

Classify (the default mode):
  FINDINGS is a file path, `-` for stdin, or the JSON array itself. Pass a
  file: a `detail` that quotes a signature reaches the helper intact, where
  `echo '<JSON>'` breaks on the first single quote.

  Input: a JSON array of findings, each an object with:
    - type:     removed | added | changed | moved | renamed | deprecated |
                semantic
    - category: what the change is about. The (type, category) pair must be
                one the rule table below accepts (--rules prints it); a pair
                it does not accept is an error, never a default severity.
                A Script/Asset Drift row (skf-compare-file-hashes.py compare)
                is added/file, removed/file or changed/file.
    - count:    optional positive integer: the exports a rollup row stands
                for (default 1)
    - category_choices: optional list (written by --from-diff): when it is
                present, category must be one of it
    - every other key (detail, name, file, line, confidence, ...) is carried
      through untouched. type, category and category_choices compare case-
      insensitively.

  The added-exports rule counts exports, not rows: the counts of every
  added/export finding are summed, and more than 3 grade each of them HIGH,
  3 or fewer MEDIUM. A rollup row of 15 added exports therefore grades HIGH.

  Output:
    {
      "status": "ok",
      "drift_score": "CLEAN" | "MINOR" | "SIGNIFICANT" | "CRITICAL",
      "total_findings": N,        # rows
      "total_items": N,           # rows weighted by count
      "added_export_count": N,    # what the added-exports rule compared
      "by_severity": {"CRITICAL": N, "HIGH": N, "MEDIUM": N, "LOW": N},
      "findings": [ {<finding>, "severity": "...", "rule": "<the rule>"} ]
    }
  by_severity counts rows weighted by count, so it sums to total_items.
  findings are sorted CRITICAL first, input order kept within a severity.
  drift_score follows severity-rules.md's Overall Drift Score table: CLEAN
  (no findings), MINOR (LOW only), SIGNIFICANT (any MEDIUM or HIGH, no
  CRITICAL), CRITICAL (any CRITICAL).

  Findings that fit no rule print {status: "error", error, problems:
  [{index, type, category, problem}]}, naming every one of them, and exit
  1; an input that is not an array prints {status: "error", error}.

--from-diff DIFF:
  Projects a skf-structural-diff.py result into the findings array, so the
  diff's buckets reach the classifier without a hand-built table. Each
  finding carries name, detail, file, line and confidence (and
  source_library for a --group-by source_library diff), and a fixed
  category where the bucket decides it:
    added[]    added/export
    removed[]  removed/export, category_choices [export, internal_helper]:
               an internal helper referenced in documented patterns grades
               HIGH, a public export CRITICAL
    moved[]    moved/export
    changed[]  one finding per export, its category settled by the
               diff's fields (see Changed exports below)
  A removed or added finding whose name the diff lists in ambiguous_names[]
  carries "ambiguous_name": true. It stays as projected unless
  --pair-move records it as a move: a finding that keeps ambiguous_name
  with another type fits no rule.
  label_changes[] and signature_unverified[] are never findings. Only the
  findings with category_choices or ambiguous_name need judgment (the
  summary line's judge lists them); the rest are fixed.

  Changed exports. The items of one export (one name, file and library)
  are one finding. Its line is the only field that changed: location.
  Otherwise, the line left out:
    whitespace  every item is equal on both sides once squashed: each
                whitespace run one space, a space beside a character that
                is not a letter, digit or _ dropped, the ends stripped,
                each quoted literal left as written (from ', " or a
                backtick to its closing quote, a backslash escaping the
                next character; in a Rust file from " only, since ' opens
                a lifetime there), a list item by item
    open        the kind (type) changed
  Else each side's parameters come from the params item (each typed
  string read as the recipe runner reads a JS/TS parameter, a name that
  starts with * optional too) and its return type from the return_type
  item, and each part no such item holds from the signature item, by the
  runner's signature_parts for the file's language. A signature it cannot
  parse, an export with no file, a language the reader does not read
  (.vue, Java, Ruby), or a params value that is not a list of strings or
  holds a bare * or / item leaves that part unknown. When either side's
  parameters are unknown, only return_type can hold. Parameters match by
  squashed name in a Python file (a nameless one by position), where a
  caller can pass any of them by keyword, and by position in any other.
  In a Python file a * parameter (*args) matches the other side's * one
  and a ** parameter (**kwargs) its ** one whatever their names, and a
  positional-only one whose name is gone matches the positional-only one
  at its place, since no caller passes any of them by name: a rename
  alone settles nothing. A type or a return type compares only when both
  sides state one; in a Python file it compares as Python reads it: a
  quoted annotation or a quoted part of one ('Node', 'list[Node]',
  Optional['pkg.Node']) as the type it quotes, Optional[X] and
  Union[X, Y] as X | None and X | Y, a union's members in any order, and
  List, Dict, Set, FrozenSet, Tuple, Type, Deque and DefaultDict as the
  builtins they name (list[int] for List[int]). The first that holds:
    parameter_count     a baseline parameter is gone
    parameter_type      a kept parameter's type differs
    return_type         both return types are known and differ
    open                in a Python file, the kept parameters changed
                        their order, or a kept one its kind
                        (positional-only, positional or keyword,
                        keyword-only: read with Python's own parser, or
                        from a params value, keyword-only after a * name)
                        or its place among the ones a caller passes by
                        position; outside a Python file, a kept
                        parameter's squashed name changed at its place (a
                        rename, a swap or a parameter inserted before it)
    required_parameter  a new parameter that is not optional, or a kept
                        one made required with its default unchanged
    default_value       a kept parameter's default is set, changed or
                        dropped
    optional_parameter  a new optional parameter (a default, ?, or a rest
                        or variadic one), or a kept one made optional with
                        its default unchanged
  An open finding, and one none holds for, is changed/signature with
  category_choices [signature, interface_contract, inheritance,
  implementation, style], signature (CRITICAL) first. When a side's
  parameters are unknown, the choices also hold what those fields would
  have settled: [signature, parameter_count, parameter_type, return_type,
  interface_contract, inheritance, required_parameter, default_value,
  optional_parameter, implementation, style]. A settled finding has no
  category_choices; detail lists every changed item either way. The
  runner, skf-extract-public-api.py, is loaded once from beside this
  script.

--set-category INDEX=CATEGORY, --pair-move REMOVED_INDEX ADDED_INDEX:
  The judgments the projection leaves open, given with the projection
  flags only (a usage error otherwise), each repeatable. An index is a
  finding's 0-based place in the projected array, the index judge gives,
  and is used once. They apply before the findings are written, so the
  same flags over the same files write the same file:
    --set-category  the finding carries category_choices and CATEGORY (any
                    case, written lowercase) is one of them
    --pair-move     REMOVED_INDEX is a removed and ADDED_INDEX an added
                    finding, both ambiguous_name, of one name and
                    source_library, judged one export that moved: the
                    added finding becomes {type: moved, category: export,
                    detail: "moved from <removed file:line> to
                    <file:line>"} without ambiguous_name, keeping its
                    name, file, line, confidence and source_library, and
                    the removed finding is dropped
  An index out of range or used twice, or a finding the flag's rule does
  not fit, is an error that names the flag, and nothing is written.

--file-drift FILE, --constituents FILE, --semantic FILE, --doc-drift FILE:
  Project the other drift sources into the same findings array, after the
  diff's findings and in this order. A hash comparison labels no export,
  so its findings carry a null line and confidence:
    --file-drift    a skf-compare-file-hashes.py compare result: each
                    added[] path is added/file, each removed[] path
                    removed/file and each changed[] item changed/file,
                    with the path as name and file
    --constituents  a skf-hash-content.py compare-constituent-hashes
                    result: each drifted[] entry is changed/constituent
                    (detail "metadata.json <stored> -> <current>"), each
                    missing[] entry removed/constituent (its reason as the
                    detail), with skill_name as name and skill_path as
                    file; fresh[] and skipped_null_hash[] are no findings
    --semantic      the semantic diff's findings, an array of objects whose
                    type is semantic, kept as written
    --doc-drift     a skf-detect-docs.py compare-hashes result, the whole
                    drift of a docs-only skill: each changed[] entry is
                    changed/doc_source (detail "content <old> -> <new>"),
                    with its url as name and file; unchanged[],
                    fetch_failed[] and skipped_null_hash[] are no findings
  Each may be given with or without --from-diff. A FILE of these four
  that does not exist is skipped (the stage that saves it did not run),
  but at least one source file must exist. The summary line's sources
  gives the findings each flag added, or null for a skipped file.

--rules:
  Prints the rule table: each rule's severity and text, and the types and
  categories it accepts, as JSON
  ({status, added_export_threshold, rules: [{severity, rule, types,
  categories, added_exports}]}) or, with --format markdown, as a table.

-o FILE writes the output to FILE and prints one summary line on stdout.
  With the projection flags it is {status, output, findings,
  needs_judgment, judge, sources}: judge lists {index, type, category,
  name, file, line}, plus category_choices or ambiguous_name, for each
  written finding that holds either, by the index the flags take, and
  needs_judgment is its length.

Exit codes:
  0  output written
  1  input error: unreadable or invalid JSON, not a findings array, a
     finding that fits no rule, a source file that is not what its flag
     reads, no source file that exists, a --set-category or --pair-move
     its rule refuses, a recipe runner beside this script that cannot be
     loaded (an error that starts "cannot load"), or an -o FILE that
     cannot be written (an error that starts "Cannot write output")
     ({status: "error", ...} on stdout)
  2  usage error (argparse, usage on stderr)
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import re
import sys
import warnings
from pathlib import Path

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")

# More new public exports than this grade HIGH; this many or fewer MEDIUM.
ADDED_EXPORT_THRESHOLD = 3

# Categories that name a public export of any kind.
PUBLIC_EXPORTS = ("export", "function", "class", "type", "interface")
# The types a LOW bucket applies to.
STRUCTURAL_TYPES = ("added", "removed", "changed", "moved", "renamed")

LINE_ONLY_RULE = "Line-only changes (same export and file, only the line number changed)"
CONSTITUENT_CHANGED_RULE = "Constituent skills changed since the stack was composed (compose-mode stacks)"
CONSTITUENT_MISSING_RULE = "Constituent skills that can no longer be found (compose-mode stacks)"
SCRIPT_ASSET_RULE = "Added or changed script, asset or doc files (Script/Asset Drift)"
DOC_SOURCE_RULE = "Changed documentation sources of a docs-only skill (doc drift)"


def _rule(severity, rule, types, categories, above_threshold=None):
    """One row of the rule table. above_threshold: True when the rule applies
    only above ADDED_EXPORT_THRESHOLD added exports, False only at or below
    it, None always."""
    return {
        "severity": severity,
        "rule": rule,
        "types": tuple(types),
        "categories": tuple(categories),
        "above_threshold": above_threshold,
    }


# --- Severity Rules (severity-rules.md, in its order) ---

RULES = (
    _rule("CRITICAL", "Removed or renamed public exports (functions, classes, types)",
          ("removed", "renamed"), PUBLIC_EXPORTS),
    _rule("CRITICAL", "Changed function signatures (parameter count, parameter types, return type)",
          ("changed",), ("signature", "parameter_count", "parameter_type", "return_type")),
    _rule("CRITICAL", "Removed or renamed modules/files referenced in skill",
          ("removed", "renamed"), ("module", "file")),
    _rule("CRITICAL", "Changed class inheritance or interface contracts",
          ("changed",), ("inheritance", "interface", "interface_contract")),
    _rule("HIGH", "New public API exports not documented in skill (>3 new exports)",
          ("added",), ("export",), above_threshold=True),
    _rule("HIGH", "Removed internal helpers that are referenced in documented patterns",
          ("removed",), ("internal_helper",)),
    _rule("HIGH", "Changed default parameter values that affect documented behavior",
          ("changed",), ("default_value",)),
    _rule("HIGH", "New required parameters added to documented functions",
          ("changed",), ("required_parameter",)),
    _rule("HIGH", "Deprecated APIs still documented as current in skill",
          ("deprecated",), PUBLIC_EXPORTS),
    _rule("HIGH", CONSTITUENT_CHANGED_RULE, ("changed",), ("constituent",)),
    _rule("HIGH", DOC_SOURCE_RULE, ("changed",), ("doc_source",)),
    _rule("MEDIUM", "Implementation changes behind a stable public API",
          ("changed",), ("implementation",)),
    _rule("MEDIUM", "Implementation changes behind a stable public API",
          ("semantic",), ("behavior", "dependency", "architecture")),
    _rule("MEDIUM", "New optional parameters with defaults on documented functions",
          ("changed",), ("optional_parameter",)),
    _rule("MEDIUM", "New public exports not in skill (1-3 new exports)",
          ("added",), ("export",), above_threshold=False),
    _rule("MEDIUM", "Moved functions between files (same API, different location)",
          ("moved",), PUBLIC_EXPORTS),
    _rule("MEDIUM", "Changed internal implementation patterns documented in skill conventions",
          ("changed",), ("internal_pattern",)),
    _rule("MEDIUM", "Changed internal implementation patterns documented in skill conventions",
          ("semantic",), ("pattern", "convention", "deprecated_pattern")),
    _rule("MEDIUM", SCRIPT_ASSET_RULE, ("added", "changed"), ("file",)),
    _rule("MEDIUM", CONSTITUENT_MISSING_RULE, ("removed",), ("constituent",)),
    _rule("LOW", "Style or convention changes (formatting, naming patterns)",
          STRUCTURAL_TYPES, ("style", "convention")),
    _rule("LOW", "Comment or documentation changes in source",
          STRUCTURAL_TYPES, ("comment", "documentation")),
    _rule("LOW", "Whitespace or structural reorganization",
          STRUCTURAL_TYPES, ("whitespace",)),
    _rule("LOW", LINE_ONLY_RULE, ("changed",), ("location",)),
    _rule("LOW", "New private/internal functions not affecting public API",
          STRUCTURAL_TYPES, ("private", "internal")),
    _rule("LOW", "Test file changes", STRUCTURAL_TYPES, ("test",)),
)


def _index_rules(rules):
    """(type, category) -> the rules that accept the pair."""
    index = {}
    for rule in rules:
        for f_type in rule["types"]:
            for category in rule["categories"]:
                index.setdefault((f_type, category), []).append(rule)
    return index


PAIRS = _index_rules(RULES)

# What --from-diff offers for a finding whose category needs judgment.
REMOVED_CHOICES = ("export", "internal_helper")
# A changed export whose category no field of the diff settles.
CHANGED_CHOICES = ("signature", "interface_contract", "inheritance", "implementation", "style")
# A changed export whose parameters the helper cannot read on one side: the
# categories those fields would have settled are offered too.
UNREAD_CHOICES = (
    "signature", "parameter_count", "parameter_type", "return_type",
    "interface_contract", "inheritance", "required_parameter", "default_value",
    "optional_parameter", "implementation", "style",
)


def _norm(value):
    return value.strip().lower() if isinstance(value, str) else None


def _pair(finding):
    return _norm(finding.get("type")), _norm(finding.get("category"))


def _count(finding):
    return finding.get("count", 1)


def match_rule(finding, added_export_count=0):
    """The rule that grades a finding, or None when no rule accepts its pair."""
    above = added_export_count > ADDED_EXPORT_THRESHOLD
    for rule in PAIRS.get(_pair(finding), ()):
        if rule["above_threshold"] is None or rule["above_threshold"] == above:
            return rule
    return None


def classify_finding(finding, added_export_count=0):
    """Classify a single finding's severity. Returns the severity, or None
    for a type/category pair no rule accepts."""
    rule = match_rule(finding, added_export_count)
    return rule["severity"] if rule else None


def _problem(finding):
    """Why a finding does not fit the rule table, or None."""
    if not isinstance(finding, dict):
        return "a finding must be a JSON object"
    f_type, category = _pair(finding)
    if f_type is None or category is None:
        return "type and category must both be strings"
    if (f_type, category) not in PAIRS:
        return "unknown type/category pair"
    choices = finding.get("category_choices")
    if choices is not None and (not isinstance(choices, list) or category not in {_norm(c) for c in choices}):
        return "category is not one of category_choices"
    if finding.get("ambiguous_name") and f_type not in ("removed", "added"):
        return "an ambiguous_name finding stays removed or added: a move judged from it drops the flag"
    count = _count(finding)
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        return "count must be a positive integer"
    return None


def _error(message, problems=None):
    out = {"status": "error", "error": message}
    if problems is not None:
        out["problems"] = problems
    return out


def compute_drift_score(classified):
    """Compute overall drift score from classified findings."""
    severities = {f["severity"] for f in classified}

    if not classified:
        return "CLEAN"
    if "CRITICAL" in severities:
        return "CRITICAL"
    if "HIGH" in severities or "MEDIUM" in severities:
        return "SIGNIFICANT"
    return "MINOR"


def classify_all(findings):
    """Classify all findings and compute drift score."""
    if not isinstance(findings, list):
        return _error("Input must be a JSON array of findings")

    problems = []
    for index, finding in enumerate(findings):
        problem = _problem(finding)
        if problem:
            given = finding if isinstance(finding, dict) else {}
            problems.append({
                "index": index,
                "type": given.get("type"),
                "category": given.get("category"),
                "problem": problem,
            })
    if problems:
        named = "; ".join(
            f"finding {p['index']} ({p['type']}/{p['category']}): {p['problem']}" for p in problems[:10]
        )
        more = f"; and {len(problems) - 10} more" if len(problems) > 10 else ""
        return _error(
            f"{len(problems)} finding(s) fit no severity rule: {named}{more}. "
            "Run with --rules for the accepted type/category pairs.",
            problems,
        )

    # The added-exports threshold counts exports: a rollup row adds its count.
    added_export_count = sum(_count(f) for f in findings if _pair(f) == ("added", "export"))

    classified = []
    for finding in findings:
        rule = match_rule(finding, added_export_count)
        classified.append({**finding, "severity": rule["severity"], "rule": rule["rule"]})

    # Sort by severity: CRITICAL > HIGH > MEDIUM > LOW
    severity_order = {s: i for i, s in enumerate(SEVERITIES)}
    classified.sort(key=lambda f: severity_order[f["severity"]])

    by_severity = {s: 0 for s in SEVERITIES}
    for f in classified:
        by_severity[f["severity"]] += _count(f)

    return {
        "status": "ok",
        "drift_score": compute_drift_score(classified),
        "total_findings": len(classified),
        "total_items": sum(by_severity.values()),
        "added_export_count": added_export_count,
        "by_severity": by_severity,
        "findings": classified,
    }


# --------------------------------------------------------------------------
# --from-diff: a structural diff projected into findings
# --------------------------------------------------------------------------


def _text(value):
    if isinstance(value, list):
        return "(" + ", ".join(str(v) for v in value) + ")"
    return str(value)


def _shape(rec):
    """An export's signature for a detail: its signature, else its params and
    return type, else None."""
    if rec.get("signature"):
        return str(rec["signature"])
    if rec.get("params") is None and not rec.get("return_type"):
        return None
    shape = _text(rec.get("params") or [])
    if rec.get("return_type"):
        shape += f" -> {rec['return_type']}"
    return shape


def _where(file, line):
    return f"{file}:{line}" if line is not None else str(file)


# The recipe runner, whose parameter readers settle a changed signature.
RUNNER = "skf-extract-public-api.py"
_RUNNER = None


class RunnerError(Exception):
    """The recipe runner beside this script cannot be loaded (exit 1)."""


def _runner():
    """skf-extract-public-api.py, loaded once from beside this script."""
    global _RUNNER
    if _RUNNER is None:
        path = Path(__file__).resolve().parent / RUNNER
        try:
            spec = importlib.util.spec_from_file_location("skf_extract_public_api", path)
            if spec is None or spec.loader is None:
                raise ImportError(f"no loader for {path}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as exc:  # whatever the script raises, the projection reports it
            raise RunnerError(f"cannot load {RUNNER} beside {Path(__file__).name}: {exc}") from exc
        missing = [need for need in ("signature_parts", "_file_language", "_js_param")
                   if getattr(module, need, None) is None]
        if missing:
            raise RunnerError(f"cannot load {RUNNER} beside {Path(__file__).name}: it has no {', '.join(missing)}")
        _RUNNER = module
    return _RUNNER


_SPACES_RE = re.compile(r"\s+")
# A space beside a character that is not a letter, digit, _ or space.
_LOOSE_SPACE_RE = re.compile(r" (?=[^\w ])|(?<=[^\w ]) ")


# The characters that open a quoted literal; in Rust a ' opens a lifetime
# (&'a str), so only " does, as the runner's own reader takes it there.
QUOTES = "'\"`"
RUST_QUOTES = '"'


def _quotes(file):
    """The characters that open a quoted literal in `file`."""
    return RUST_QUOTES if isinstance(file, str) and file.strip().lower().endswith(".rs") else QUOTES


def _squash_text(text):
    return _LOOSE_SPACE_RE.sub("", _SPACES_RE.sub(" ", text))


def _squash(value, quotes=QUOTES):
    """A value with each whitespace run one space, a space beside a
    character that is not a letter, digit or _ dropped, and the ends
    stripped, each quoted literal left as written (from a character of
    `quotes` to its closing quote, a backslash escaping the next
    character); a list item by item."""
    if isinstance(value, list):
        return [_squash(item, quotes) for item in value]
    if not isinstance(value, str):
        return value
    # runs of (literal, text): the text between literals, then each literal
    runs, start, quote, i = [], 0, None, 0
    while i < len(value):
        ch = value[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                runs.append((True, value[start:i + 1]))
                start, quote = i + 1, None
        elif ch in quotes:
            runs.append((False, value[start:i]))
            start, quote = i, ch
        i += 1
    runs.append((quote is not None, value[start:]))
    out = []
    for n, (literal, text) in enumerate(runs):
        if literal:
            out.append(text)
            continue
        # squashed beside the quotes around it, which are no letter or digit
        before = runs[n - 1][1][-1:] if n else ""
        after = runs[n + 1][1][:1] if n + 1 < len(runs) else ""
        squashed = _squash_text(before + text + after)
        out.append(squashed[len(before):len(squashed) - len(after)])
    if not runs[0][0]:
        out[0] = out[0].lstrip()
    if not runs[-1][0]:
        out[-1] = out[-1].rstrip()
    return "".join(out)


def _typed_params(value):
    """A params value's parameters, each typed string read as the runner
    reads a JS/TS one (a name that starts with * is optional too); None when
    the value is not a list of strings."""
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    params = []
    for text in value:
        param = _runner()._js_param(text) if text.strip() else None
        if param is None:
            continue
        if (param.get("name") or "").startswith("*"):
            param = {**param, "optional": True}
        params.append(param)
    return params


def _sides(items, file, name):
    """(params, return_type) of the baseline and the current side of one
    changed export, each None where the items do not tell it."""
    by_field = {item.get("field"): item for item in items}
    sides = []
    for key in ("baseline_value", "current_value"):
        params = ret = None
        if "params" in by_field:
            params = _typed_params(by_field["params"].get(key))
        if "return_type" in by_field:
            ret = by_field["return_type"].get(key)
        signature = by_field.get("signature", {}).get(key)
        parts = {"params", "return_type"} - set(by_field)
        if parts and isinstance(signature, str) and isinstance(file, str) and file and isinstance(name, str):
            language = _runner()._file_language(file)
            try:
                with warnings.catch_warnings():
                    # a default such as '\s+' makes Python's parser warn on stderr
                    warnings.simplefilter("ignore")
                    parsed = _runner().signature_parts(signature, language, name) if language else (None, None)
            except (ValueError, RecursionError):
                parsed = (None, None)
            if "params" in parts:
                params = parsed[0]
            if "return_type" in parts:
                ret = parsed[1]
        sides.append((params, ret if isinstance(ret, str) and ret.strip() else None))
    return sides


def _keyed(params, by_name):
    """Parameters by squashed name when `by_name` (a Python file), a
    nameless one by its position; else each by its position."""
    keyed = {}
    for index, param in enumerate(params):
        name = param.get("name")
        named = by_name and isinstance(name, str) and name.strip()
        keyed.setdefault(("name", _squash(name)) if named else ("at", index), param)
    return keyed


def _slot(key, kinds):
    """The slot of a keyed Python parameter no caller passes by name: ("*",)
    or ("**",) for a star one, its (kind, place) from `kinds` for a
    positional-only one; None for any other."""
    kind, name = key
    if kind != "name":
        return None
    if name.startswith("**"):
        return ("**",)
    if name.startswith("*"):
        return ("*",)
    found = (kinds or {}).get(name)
    return found if found and found[0] == "positional" else None


def _renamed(base, curr, base_kinds, curr_kinds):
    """`curr` with each new parameter no caller passes by name keyed as the
    baseline one gone from its slot (see _slot), so a rename alone keeps
    it; the order of `curr` is kept."""
    gone = {}
    for key in base:
        slot = _slot(key, base_kinds)
        if slot is not None and key not in curr:
            gone.setdefault(slot, key)
    out = {}
    for key, param in curr.items():
        slot = _slot(key, curr_kinds) if key not in base else None
        out[gone.pop(slot, key) if slot is not None else key] = param
    return out


def _side_kinds(fields, sides):
    """(before, after): the {name: (kind, place)} of each side of a Python
    export, from the params item when there is one, else from the
    signature item (None where it does not parse)."""
    by_field = {item.get("field"): item for item in fields}
    if "params" in by_field:
        return tuple(_listed_kinds(params) for params in sides)
    signature = by_field.get("signature", {})
    return tuple(_python_kinds(signature.get(key)) for key in ("baseline_value", "current_value"))


def _unread(params):
    """True when a side's parameters are unknown: none read, or a params
    value with a bare * or / item, whose marker the reader takes for a
    parameter."""
    return params is None or any(isinstance(param.get("name"), str) and param["name"].strip() in ("*", "/")
                                 for param in params)


# A quoted name or dotted name: in a Python annotation, the forward
# reference to the type it names ('Node', Optional['pkg.Node']).
_QUOTED_NAME_RE = re.compile(r"""(['"])([^\W\d]\w*(?:\.[^\W\d]\w*)*)\1""")


def _unquoted(value, python):
    """In a Python file, a type with each quoted name or dotted name
    unquoted; any other value as it is."""
    return _QUOTED_NAME_RE.sub(r"\2", value) if python and isinstance(value, str) else value


def _parsed(text, mode="exec"):
    """Python's parse of `text`, None when it does not parse; a parse that
    warns (a default such as '\\s+') prints nothing."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return ast.parse(text, mode=mode)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None


# typing's names for the builtin and collections generics (PEP 585); the
# diff has already dropped a `typing.` or `collections.` prefix.
_GENERIC_ALIASES = {"List": "list", "Dict": "dict", "Set": "set", "FrozenSet": "frozenset", "Tuple": "tuple",
                    "Type": "type", "Deque": "deque", "DefaultDict": "defaultdict"}


def _members(node):
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _members(node.left) + _members(node.right)
    return [node]


def _union(nodes):
    """One `|` union of `nodes`' members, once each, in a fixed order."""
    by_text = {ast.unparse(member): member for node in nodes for member in _members(node)}
    ordered = [by_text[text] for text in sorted(by_text)]
    union = ordered[0]
    for member in ordered[1:]:
        union = ast.BinOp(left=union, op=ast.BitOr(), right=member)
    return union


class _TypeForm(ast.NodeTransformer):
    """A Python annotation as Python reads it: a quoted part as the type it
    quotes, Optional and Union as a `|` union whose members are in a fixed
    order, and typing's generic aliases as the builtins they name."""

    def visit_Constant(self, node):
        if isinstance(node.value, str):
            quoted = _parsed(node.value.strip(), "eval")
            if quoted is not None:
                return self.visit(quoted.body)
        return node

    def visit_Name(self, node):
        return ast.Name(id=_GENERIC_ALIASES.get(node.id, node.id), ctx=node.ctx)

    def visit_BinOp(self, node):
        node = self.generic_visit(node)
        return _union([node]) if isinstance(node.op, ast.BitOr) else node

    def visit_Subscript(self, node):
        if isinstance(node.value, ast.Name) and node.value.id == "Literal":
            return node  # its quoted parts are values, not types
        node = self.generic_visit(node)
        if isinstance(node.value, ast.Name) and node.value.id == "Optional":
            return _union([node.slice, ast.Constant(value=None)])
        if isinstance(node.value, ast.Name) and node.value.id == "Union":
            return _union(node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice])
        return node


def _python_type(value):
    """A Python type in the form _TypeForm gives it, or with its quoted
    names unquoted when it does not parse."""
    tree = _parsed(value.strip(), "eval") if isinstance(value, str) else None
    if tree is None:
        return _unquoted(value, True)
    try:
        return ast.unparse(_TypeForm().visit(tree.body))
    except (ValueError, TypeError, AttributeError, RecursionError):
        return _unquoted(value, True)


def _stated(base, curr, quotes, python=False):
    """True when both sides state a value and the two differ once squashed
    (a type of a Python file in the form _python_type gives it)."""
    if python:
        base, curr = _python_type(base), _python_type(curr)
    return (isinstance(base, str) and bool(base.strip()) and isinstance(curr, str) and bool(curr.strip())
            and _squash(base, quotes) != _squash(curr, quotes))


def _turned(base, curr, optional, quotes):
    """True when a kept parameter turns optional (or required) with its
    default unchanged."""
    return (bool(base.get("optional")) != optional and bool(curr.get("optional")) == optional
            and _squash(base.get("default"), quotes) == _squash(curr.get("default"), quotes))


def _python_kinds(signature):
    """{name: (kind, place)} of a Python def's named parameters, read with
    Python's own parser (the runner's reader drops the kind): kind
    positional (positional-only), either or keyword (keyword-only), place
    its index among the ones a caller can pass by position, None for a
    keyword-only one. None when the signature does not parse."""
    if not isinstance(signature, str):
        return None
    head = signature.strip()
    head = head[:-1] if head.endswith(":") else head
    tree = _parsed(head + ": pass")
    if tree is None:
        return None
    node = tree.body[0] if tree.body else None
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None
    args = node.args
    kinds = {arg.arg: ("positional", place) for place, arg in enumerate(args.posonlyargs)}
    kinds.update({arg.arg: ("either", len(args.posonlyargs) + place) for place, arg in enumerate(args.args)})
    kinds.update({arg.arg: ("keyword", None) for arg in args.kwonlyargs})
    return kinds


def _listed_kinds(params):
    """{name: (kind, place)}, as _python_kinds gives them, of a params
    value's Python parameters: either up to the first one whose name starts
    with *, keyword after it."""
    kinds, place = {}, 0
    for param in params:
        name = param.get("name") if isinstance(param.get("name"), str) else ""
        if name.startswith("*"):
            place = None
            continue
        if name.strip():
            kinds.setdefault(_squash(name), ("either", place) if place is not None else ("keyword", None))
        if place is not None:
            place += 1
    return kinds


def _reordered(fields, sides, base, curr):
    """True when the kept parameters of a Python export, keyed by name in
    `base` and `curr`, changed their order, or a kept one its kind
    (positional-only, positional or keyword, keyword-only) or its place
    among the ones a caller passes by position. `sides` are the two
    parameter lists, from the params item when there is one, else from the
    signature item."""
    if [key for key in base if key in curr] != [key for key in curr if key in base]:
        return True
    by_field = {item.get("field"): item for item in fields}
    if "params" in by_field:
        before, after = (_listed_kinds(params) for params in sides)
    else:
        signature = by_field.get("signature", {})
        before, after = (_python_kinds(signature.get(key)) for key in ("baseline_value", "current_value"))
    if before is None or after is None:
        return False
    return any(before[name] != after[name] for kind, name in base
               if kind == "name" and (kind, name) in curr and name in before and name in after)


def settle_changed(items, rec):
    """(category, None) for the category the diff's fields settle for one
    changed export's items, or (None, the category_choices a reviewer picks
    from) when they settle none (see --from-diff)."""
    file = rec.get("file")
    quotes = _quotes(file)
    fields = [item for item in items if item.get("field") != "line"]
    if all(_squash(item.get("baseline_value"), quotes) == _squash(item.get("current_value"), quotes)
           for item in fields):
        return "whitespace", None
    if any(item.get("field") == "type" for item in fields):
        return None, CHANGED_CHOICES
    (base_params, base_ret), (curr_params, curr_ret) = _sides(fields, file, rec.get("name"))
    python = isinstance(file, str) and _runner()._file_language(file) == "python"
    if _unread(base_params) or _unread(curr_params):
        return ("return_type", None) if _stated(base_ret, curr_ret, quotes, python) else (None, UNREAD_CHOICES)
    base, curr = _keyed(base_params, python), _keyed(curr_params, python)
    if python:
        # a *, ** or positional-only parameter only renamed keeps its slot
        curr = _renamed(base, curr, *_side_kinds(fields, (base_params, curr_params)))
    kept = [key for key in base if key in curr]
    new = [curr[key] for key in curr if key not in base]
    if len(kept) < len(base):
        return "parameter_count", None
    if any(_stated(base[key].get("type"), curr[key].get("type"), quotes, python) for key in kept):
        return "parameter_type", None
    if _stated(base_ret, curr_ret, quotes, python):
        return "return_type", None
    # a change no category names holds the finding open
    if python and _reordered(fields, (base_params, curr_params), base, curr):
        return None, CHANGED_CHOICES
    # outside Python a new name at a kept place: a rename, a swap or a shift
    if not python and any(_squash(base[key].get("name"), quotes) != _squash(curr[key].get("name"), quotes)
                          for key in kept):
        return None, CHANGED_CHOICES
    if any(not param.get("optional") for param in new) or any(
            _turned(base[key], curr[key], False, quotes) for key in kept):
        return "required_parameter", None
    if any(_squash(base[key].get("default"), quotes) != _squash(curr[key].get("default"), quotes) for key in kept):
        return "default_value", None
    if new or any(_turned(base[key], curr[key], True, quotes) for key in kept):
        return "optional_parameter", None
    return None, CHANGED_CHOICES


def _finding(f_type, category, rec, detail, choices=None, ambiguous=False):
    finding = {"type": f_type, "category": category}
    if choices:
        finding["category_choices"] = list(choices)
    finding.update(
        name=rec.get("name"),
        detail=detail,
        file=rec.get("file"),
        line=rec.get("line"),
        confidence=rec.get("confidence"),
    )
    if "source_library" in rec:
        finding["source_library"] = rec["source_library"]
    if ambiguous:
        finding["ambiguous_name"] = True
    return finding


def project_diff(diff):
    """The findings array for a skf-structural-diff.py result (see --from-diff).

    Raises ValueError when diff is not a structural diff.
    """
    buckets = ("added", "removed", "changed", "moved")
    if not isinstance(diff, dict) or not all(isinstance(diff.get(b), list) for b in buckets):
        raise ValueError(
            "not a structural diff: expected an object with added, removed, changed "
            "and moved lists (the output of skf-structural-diff.py)"
        )
    ambiguous = {
        (item.get("source_library"), item.get("name"))
        for item in diff.get("ambiguous_names") or []
        if isinstance(item, dict)
    }
    records = {b: [r for r in diff[b] if isinstance(r, dict)] for b in buckets}

    findings = []
    for rec in records["added"]:
        kind = rec.get("type") or "export"
        shape = _shape(rec)
        detail = f"new {kind}: {shape}" if shape else f"new {kind}"
        findings.append(_finding("added", "export", rec, detail,
                                 ambiguous=(rec.get("source_library"), rec.get("name")) in ambiguous))
    for rec in records["removed"]:
        kind = rec.get("type") or "export"
        shape = _shape(rec)
        detail = f"removed {kind}: {shape}" if shape else f"removed {kind}"
        findings.append(_finding("removed", "export", rec, detail, choices=REMOVED_CHOICES,
                                 ambiguous=(rec.get("source_library"), rec.get("name")) in ambiguous))

    # One finding per changed export, in the diff's order.
    changes = {}
    for item in records["changed"]:
        key = (item.get("source_library"), item.get("name"), item.get("file"))
        changes.setdefault(key, []).append(item)
    for items in changes.values():
        rec = items[0]
        fields = [item.get("field") for item in items]
        if fields == ["line"]:
            detail = f"line {rec.get('baseline_value')} -> {rec.get('current_value')}"
            findings.append(_finding("changed", "location", rec, detail))
            continue
        detail = "; ".join(
            f"{item.get('field')}: {_text(item.get('baseline_value'))} -> {_text(item.get('current_value'))}"
            for item in items
        )
        category, choices = settle_changed(items, rec)
        if category is None:
            findings.append(_finding("changed", "signature", rec, detail, choices=choices))
        else:
            findings.append(_finding("changed", category, rec, detail))

    for rec in records["moved"]:
        detail = (
            f"moved from {_where(rec.get('previous_file'), rec.get('previous_line'))} "
            f"to {_where(rec.get('current_file'), rec.get('line'))}"
        )
        findings.append(_finding("moved", "export", {**rec, "file": rec.get("current_file")}, detail))
    return findings


def _lists(data, keys, what):
    """Raise ValueError unless data is an object holding a list at each key."""
    if not isinstance(data, dict) or not all(isinstance(data.get(k), list) for k in keys):
        raise ValueError(f"not {what}: expected an object with {', '.join(keys)} lists")


def project_file_drift(data):
    """The findings for a skf-compare-file-hashes.py compare result (see --file-drift).

    Raises ValueError when data is not one.
    """
    _lists(data, ("added", "removed", "changed"),
           "a file drift result (the output of skf-compare-file-hashes.py compare)")
    findings = []
    for f_type, detail in (("added", "new file"), ("removed", "file removed")):
        for path in data[f_type]:
            if isinstance(path, str):
                findings.append(_finding(f_type, "file", {"name": path, "file": path}, detail))
    for item in data["changed"]:
        if isinstance(item, dict):
            path = item.get("path")
            detail = f"content {item.get('stored_hash')} -> {item.get('current_hash')}"
            findings.append(_finding("changed", "file", {"name": path, "file": path}, detail))
    return findings


def project_constituents(data):
    """The findings for a skf-hash-content.py compare-constituent-hashes result
    (see --constituents).

    Raises ValueError when data is not one.
    """
    _lists(data, ("drifted", "missing"),
           "a constituent freshness result (the output of skf-hash-content.py compare-constituent-hashes)")
    findings = []
    for rec in data["drifted"]:
        if isinstance(rec, dict):
            detail = f"metadata.json {rec.get('stored_hash')} -> {rec.get('current_hash')}"
            findings.append(_finding("changed", "constituent",
                                     {"name": rec.get("skill_name"), "file": rec.get("skill_path")}, detail))
    for rec in data["missing"]:
        if isinstance(rec, dict):
            findings.append(_finding("removed", "constituent",
                                     {"name": rec.get("skill_name"), "file": rec.get("skill_path")},
                                     rec.get("reason")))
    return findings


def project_semantic(data):
    """The semantic diff's findings, kept as written (see --semantic).

    Raises ValueError unless data is an array of semantic findings.
    """
    if not isinstance(data, list) or not all(
            isinstance(f, dict) and _norm(f.get("type")) == "semantic" for f in data):
        raise ValueError("not a semantic findings file: expected an array of objects whose type is semantic")
    return list(data)


def project_doc_drift(data):
    """The findings for a skf-detect-docs.py compare-hashes result (see
    --doc-drift).

    Raises ValueError when data is not one.
    """
    _lists(data, ("changed", "unchanged", "fetch_failed"),
           "a doc drift result (the output of skf-detect-docs.py compare-hashes)")
    findings = []
    for rec in data["changed"]:
        if isinstance(rec, dict):
            url = rec.get("url")
            detail = f"content {rec.get('old_hash')} -> {rec.get('new_hash')}"
            findings.append(_finding("changed", "doc_source", {"name": url, "file": url}, detail))
    return findings


# Each projection source: its name in the summary line, its argparse dest,
# its projection, and whether a file that does not exist is skipped.
SOURCES = (
    ("diff", "from_diff", project_diff, False),
    ("file_drift", "file_drift", project_file_drift, True),
    ("constituents", "constituents", project_constituents, True),
    ("semantic", "semantic", project_semantic, True),
    ("doc_drift", "doc_drift", project_doc_drift, True),
)


def project_sources(paths):
    """(findings, sources) for the projection flags.

    paths maps each source name to its file, or None when its flag is not
    given. sources gives the findings each given flag added, or None for a
    skipped file. Raises ValueError, naming the file, when a file cannot be
    read or is not what its flag reads, or when no source file exists.
    """
    findings, sources = [], {}
    for name, _, project, optional in SOURCES:
        path = paths.get(name)
        if path is None:
            continue
        path = Path(path)
        if optional and not path.exists():
            sources[name] = None
            continue
        try:
            part = project(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, ValueError) as e:
            # json.JSONDecodeError is a ValueError.
            raise ValueError(f"{path}: {e}") from e
        findings.extend(part)
        sources[name] = len(part)
    if sources and all(count is None for count in sources.values()):
        raise ValueError("none of the source files exists: " + ", ".join(str(paths[n]) for n in sources))
    return findings, sources


# --------------------------------------------------------------------------
# --set-category and --pair-move: the judgments the projection leaves open
# --------------------------------------------------------------------------


def _judgment_error(flag, args, problem):
    return ValueError(f"{flag} {args}: {problem}")


def apply_judgments(findings, set_categories=(), pair_moves=()):
    """(written, indices): the projected findings with each --set-category
    and --pair-move applied, and the projected index of each written
    finding (see --set-category).

    set_categories holds (index, category) pairs, pair_moves (removed,
    added) index pairs. Raises ValueError, naming the flag, for an index out
    of range or used twice, or a finding the flag's rule does not fit.
    """
    written = list(findings)
    used = set()

    def take(flag, args, index):
        if not 0 <= index < len(findings):
            raise _judgment_error(flag, args, f"index {index} is out of range: the projection has "
                                              f"{len(findings)} finding(s)")
        if index in used:
            raise _judgment_error(flag, args, f"index {index} is used twice")
        used.add(index)
        return findings[index]

    for index, category in set_categories:
        args = f"{index}={category}"
        finding = take("--set-category", args, index)
        choices = finding.get("category_choices") if isinstance(finding, dict) else None
        if not isinstance(choices, list):
            raise _judgment_error("--set-category", args, f"finding {index} has no category_choices")
        if _norm(category) not in {_norm(c) for c in choices}:
            raise _judgment_error("--set-category", args, f"{category} is not one of finding {index}'s "
                                                          f"category_choices ({', '.join(map(str, choices))})")
        written[index] = {**finding, "category": _norm(category)}

    dropped = set()
    for removed_at, added_at in pair_moves:
        args = f"{removed_at} {added_at}"
        removed = take("--pair-move", args, removed_at)
        added = take("--pair-move", args, added_at)
        for at, finding, kind in ((removed_at, removed, "a removed"), (added_at, added, "an added")):
            if not isinstance(finding, dict) or _norm(finding.get("type")) != kind.split()[1] \
                    or finding.get("ambiguous_name") is not True:
                raise _judgment_error("--pair-move", args, f"finding {at} is not {kind} finding with ambiguous_name")
        for key in ("name", "source_library"):
            if removed.get(key) != added.get(key):
                raise _judgment_error("--pair-move", args, f"findings {removed_at} and {added_at} differ in {key}")
        detail = f"moved from {_where(removed.get('file'), removed.get('line'))} to " \
                 f"{_where(added.get('file'), added.get('line'))}"
        written[added_at] = _finding("moved", "export", added, detail)
        dropped.add(removed_at)

    indices = [i for i in range(len(written)) if i not in dropped]
    return [written[i] for i in indices], indices


def judge(written, indices):
    """The summary line's judge: each written finding that holds
    category_choices or ambiguous_name, by the index the flags take."""
    listed = []
    for index, finding in zip(indices, written):
        if not isinstance(finding, dict) or not ("category_choices" in finding or finding.get("ambiguous_name")):
            continue
        entry = {"index": index, **{key: finding.get(key) for key in ("type", "category", "name", "file", "line")}}
        for key in ("category_choices", "ambiguous_name"):
            if key in finding:
                entry[key] = finding[key]
        listed.append(entry)
    return listed


# --------------------------------------------------------------------------
# --rules
# --------------------------------------------------------------------------


def _added_exports(rule):
    if rule["above_threshold"] is None:
        return None
    if rule["above_threshold"]:
        return f"more than {ADDED_EXPORT_THRESHOLD}"
    return f"{ADDED_EXPORT_THRESHOLD} or fewer"


def rules_table():
    """The rule table as --rules prints it in JSON."""
    return {
        "status": "ok",
        "added_export_threshold": ADDED_EXPORT_THRESHOLD,
        "rules": [
            {
                "severity": rule["severity"],
                "rule": rule["rule"],
                "types": list(rule["types"]),
                "categories": list(rule["categories"]),
                "added_exports": _added_exports(rule),
            }
            for rule in RULES
        ],
    }


def rules_markdown():
    """The rule table as a Markdown table."""
    lines = ["| Severity | Types | Categories | Rule |", "| --- | --- | --- | --- |"]
    for rule in RULES:
        types = ", ".join(f"`{t}`" for t in rule["types"])
        categories = ", ".join(f"`{c}`" for c in rule["categories"])
        lines.append(f"| {rule['severity']} | {types} | {categories} | {rule['rule']} |")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _load_findings(arg):
    """Parse FINDINGS: `-` for stdin, a JSON array given inline, or a file."""
    if arg == "-":
        return json.loads(sys.stdin.buffer.read().decode("utf-8"))
    if arg.lstrip().startswith("["):
        return json.loads(arg)
    return json.loads(Path(arg).read_text(encoding="utf-8"))


def _index_category(text):
    """An INDEX=CATEGORY value of --set-category."""
    index, sep, category = text.partition("=")
    try:
        number = int(index.strip())
    except ValueError:
        number = None
    if not sep or number is None or not category.strip():
        raise argparse.ArgumentTypeError(f"expected INDEX=CATEGORY, got {text!r}")
    return number, category.strip()


def _build_parser():
    # --help prints the module docstring: the findings, --from-diff and
    # --rules contracts a calling step cites.
    parser = argparse.ArgumentParser(
        prog="skf-severity-classify.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "findings",
        nargs="?",
        metavar="FINDINGS",
        help="findings JSON file, - for stdin, or a JSON array",
    )
    parser.add_argument(
        "--from-diff",
        metavar="DIFF",
        help="project a skf-structural-diff.py result file into a findings array",
    )
    parser.add_argument(
        "--file-drift",
        metavar="FILE",
        help="also project a skf-compare-file-hashes.py compare result (skipped when FILE does not exist)",
    )
    parser.add_argument(
        "--constituents",
        metavar="FILE",
        help="also project a compare-constituent-hashes result (skipped when FILE does not exist)",
    )
    parser.add_argument(
        "--semantic",
        metavar="FILE",
        help="also add the semantic diff's findings array (skipped when FILE does not exist)",
    )
    parser.add_argument(
        "--doc-drift",
        metavar="FILE",
        help="also project a skf-detect-docs.py compare-hashes result (skipped when FILE does not exist)",
    )
    parser.add_argument(
        "--set-category",
        action="append",
        type=_index_category,
        default=[],
        metavar="INDEX=CATEGORY",
        help="with the projection flags: set the category of the projected finding INDEX, one of its "
             "category_choices (repeatable)",
    )
    parser.add_argument(
        "--pair-move",
        action="append",
        nargs=2,
        type=int,
        default=[],
        metavar=("REMOVED_INDEX", "ADDED_INDEX"),
        help="with the projection flags: record an ambiguous removed and added finding of one name as one "
             "moved export (repeatable)",
    )
    parser.add_argument(
        "--rules",
        action="store_true",
        help="print the rule table: severities and the accepted type/category pairs",
    )
    parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        help="with --rules: print JSON (the default) or a Markdown table",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="write the output to FILE and print a summary line on stdout",
    )
    return parser


def _emit(text, output, summary):
    """Print text, or write it to output and print the summary line. Returns
    an error dict when output cannot be written."""
    if not output:
        print(text)
        return None
    try:
        Path(output).write_text(text + "\n", encoding="utf-8")
    except OSError as exc:
        return _error(f"Cannot write output: {exc}")
    print(json.dumps({"status": "ok", "output": str(output), **summary}))
    return None


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    paths = {name: getattr(args, dest) for name, dest, _, _ in SOURCES}
    projecting = any(path is not None for path in paths.values())
    modes = [args.findings is not None, projecting, args.rules]
    if sum(modes) != 1:
        parser.error("give exactly one of FINDINGS, the projection flags (--from-diff, --file-drift, "
                     "--constituents, --semantic, --doc-drift) or --rules")
    if args.format and not args.rules:
        parser.error("--format applies to --rules only")
    if (args.set_category or args.pair_move) and not projecting:
        parser.error("--set-category and --pair-move apply with the projection flags only")

    if args.rules:
        if args.format == "markdown":
            text = rules_markdown()
        else:
            text = json.dumps(rules_table(), indent=2)
        failed = _emit(text, args.output, {})
    elif projecting:
        try:
            findings, sources = project_sources(paths)
            findings, indices = apply_judgments(findings, args.set_category, [tuple(p) for p in args.pair_move])
        except (ValueError, RunnerError) as e:
            print(json.dumps(_error(str(e)), indent=2))
            return 1
        listed = judge(findings, indices)
        failed = _emit(json.dumps(findings, indent=2), args.output, {
            "findings": len(findings),
            "needs_judgment": len(listed),
            "judge": listed,
            "sources": sources,
        })
    else:
        try:
            data = _load_findings(args.findings)
        except (OSError, UnicodeDecodeError, ValueError) as e:
            print(json.dumps(_error(str(e)), indent=2))
            return 1
        result = classify_all(data)
        if result["status"] != "ok":
            print(json.dumps(result, indent=2))
            return 1
        failed = _emit(json.dumps(result, indent=2), args.output, {
            key: result[key] for key in ("drift_score", "total_findings", "total_items", "by_severity")
        })

    if failed:
        print(json.dumps(failed, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
