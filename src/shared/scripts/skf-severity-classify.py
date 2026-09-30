# /// script
# requires-python = ">=3.10"
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
    changed[]  one finding per export: changed/location when its line is
               the only field that changed; otherwise changed/signature with
               category_choices listing the categories a signature or type
               change can have, from signature (CRITICAL, the default) down
               to style and whitespace (LOW)
  A removed or added finding whose name the diff lists in ambiguous_names[]
  carries "ambiguous_name": true. A reviewer who judges a removed and an
  added finding of one ambiguous name to be one export that moved records
  it as the projection records a move: the added finding becomes
  {type: moved, category: export, detail: "moved from <removed file:line>
  to <file:line>"} without ambiguous_name, and the removed finding is
  dropped. Every other ambiguous finding stays as projected: a finding
  that keeps ambiguous_name with another type fits no rule.
  label_changes[] and signature_unverified[] are never findings. Only the
  categories with category_choices need judgment; the rest are fixed.

--rules:
  Prints the rule table: each rule's severity and text, and the types and
  categories it accepts, as JSON
  ({status, added_export_threshold, rules: [{severity, rule, types,
  categories, added_exports}]}) or, with --format markdown, as a table.

-o FILE writes the output to FILE and prints one summary line on stdout.

Exit codes:
  0  output written
  1  input error: unreadable or invalid JSON, not a findings array, a
     finding that fits no rule, or a --from-diff file that is not a
     structural diff ({status: "error", ...} on stdout)
  2  usage error (argparse, usage on stderr)
"""

from __future__ import annotations

import argparse
import json
import sys
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
CHANGED_CHOICES = (
    "signature", "parameter_count", "parameter_type", "return_type",
    "inheritance", "interface", "interface_contract",
    "default_value", "required_parameter",
    "optional_parameter", "implementation",
    "style", "whitespace",
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
        findings.append(_finding("changed", "signature", rec, detail, choices=CHANGED_CHOICES))

    for rec in records["moved"]:
        detail = (
            f"moved from {_where(rec.get('previous_file'), rec.get('previous_line'))} "
            f"to {_where(rec.get('current_file'), rec.get('line'))}"
        )
        findings.append(_finding("moved", "export", {**rec, "file": rec.get("current_file")}, detail))
    return findings


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
    modes = [args.findings is not None, args.from_diff is not None, args.rules]
    if sum(modes) != 1:
        parser.error("give exactly one of FINDINGS, --from-diff DIFF or --rules")
    if args.format and not args.rules:
        parser.error("--format applies to --rules only")

    if args.rules:
        if args.format == "markdown":
            text = rules_markdown()
        else:
            text = json.dumps(rules_table(), indent=2)
        failed = _emit(text, args.output, {})
    elif args.from_diff is not None:
        try:
            findings = project_diff(json.loads(Path(args.from_diff).read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, ValueError) as e:
            # json.JSONDecodeError is a ValueError.
            print(json.dumps(_error(str(e)), indent=2))
            return 1
        failed = _emit(json.dumps(findings, indent=2), args.output, {
            "findings": len(findings),
            "needs_judgment": sum(1 for f in findings if "category_choices" in f),
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
