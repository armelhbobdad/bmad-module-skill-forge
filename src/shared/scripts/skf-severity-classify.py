# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Severity Classify — Rule-based severity classification for drift findings.

Applies severity rules to a list of drift findings and computes an overall
drift score. Used by audit-skill and test-skill.

CLI: python3 skf-severity-classify.py <findings-json>
     echo '<JSON>' | python3 skf-severity-classify.py -

Input: JSON array of findings, each with:
  - type: "removed"|"added"|"changed"|"moved"|"semantic"
  - category: "export"|"signature"|"parameter"|"module"|"pattern"|"convention"|...
  - detail: description string

Output: JSON with classified findings and overall drift score.
"""

from __future__ import annotations

import json
import sys

# --- Severity Rules (from severity-rules.md) ---

CRITICAL_RULES = [
    {"type": "removed", "categories": {"export", "module", "class", "interface"}},
    {"type": "changed", "categories": {"signature", "parameter_count", "return_type", "inheritance", "interface_contract"}},
    {"type": "renamed", "categories": {"export", "module"}},
]

HIGH_RULES = [
    {"type": "added", "categories": {"export"}, "threshold": 3},  # >3 new exports
    {"type": "removed", "categories": {"internal_helper"}},
    {"type": "changed", "categories": {"default_value", "required_parameter"}},
    {"type": "deprecated", "categories": {"export"}},
]

MEDIUM_RULES = [
    {"type": "changed", "categories": {"implementation", "optional_parameter", "internal_pattern"}},
    {"type": "added", "categories": {"export"}, "threshold_max": 3},  # 1-3 new exports
    {"type": "moved", "categories": {"export", "function"}},
]

LOW_CATEGORIES = {"style", "convention", "comment", "documentation", "whitespace", "test", "internal", "private"}


def classify_finding(finding, added_export_count=0):
    """Classify a single finding's severity. Returns severity string."""
    f_type = finding.get("type", "").lower()
    f_category = finding.get("category", "").lower()

    # Check CRITICAL
    for rule in CRITICAL_RULES:
        if f_type == rule["type"] and f_category in rule["categories"]:
            return "CRITICAL"

    # Check HIGH
    for rule in HIGH_RULES:
        if f_type == rule["type"]:
            if f_category in rule["categories"]:
                if "threshold" in rule:
                    if f_type == "added" and f_category == "export" and added_export_count > rule["threshold"]:
                        return "HIGH"
                else:
                    return "HIGH"

    # Check MEDIUM
    for rule in MEDIUM_RULES:
        if f_type == rule["type"]:
            if f_category in rule["categories"]:
                if "threshold_max" in rule:
                    if f_type == "added" and f_category == "export" and added_export_count <= rule["threshold_max"]:
                        return "MEDIUM"
                else:
                    return "MEDIUM"

    # Check LOW
    if f_category in LOW_CATEGORIES:
        return "LOW"

    # Semantic findings default to MEDIUM
    if f_type == "semantic":
        return "MEDIUM"

    # Default: MEDIUM for unrecognized patterns
    return "MEDIUM"


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
        return {"status": "error", "error": "Input must be a JSON array of findings"}

    # Count added exports for threshold rules
    added_export_count = sum(
        1 for f in findings
        if f.get("type", "").lower() == "added" and f.get("category", "").lower() == "export"
    )

    classified = []
    for finding in findings:
        severity = classify_finding(finding, added_export_count)
        classified.append({**finding, "severity": severity})

    # Sort by severity: CRITICAL > HIGH > MEDIUM > LOW
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    classified.sort(key=lambda f: severity_order.get(f["severity"], 4))

    drift_score = compute_drift_score(classified)

    # Summary
    by_severity = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in classified:
        by_severity[f["severity"]] = by_severity.get(f["severity"], 0) + 1

    return {
        "status": "ok",
        "drift_score": drift_score,
        "total_findings": len(classified),
        "by_severity": by_severity,
        "findings": classified,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 skf-severity-classify.py <findings-json-or-file>", file=sys.stderr)
        print("       echo '<JSON>' | python3 skf-severity-classify.py -", file=sys.stderr)
        sys.exit(1)

    arg = sys.argv[1]

    try:
        if arg == "-":
            data = json.load(sys.stdin)
        elif arg.startswith("["):
            data = json.loads(arg)
        else:
            with open(arg) as f:
                data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(json.dumps({"status": "error", "error": str(e)}))
        sys.exit(1)

    result = classify_all(data)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "ok" else 1)
