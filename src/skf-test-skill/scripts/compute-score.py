# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Deterministic Completeness Score Calculator.

Pure-function scoring script for the SKF test-skill workflow (step-05).
Implements the weight tables, skip conditions, and proportional redistribution
defined in scoring-rules.md.

CLI: python3 compute-score.py '<JSON>'
"""

from __future__ import annotations

import json
import math
import sys

# --- Weight Tables (from scoring-rules.md) ---

CONTEXTUAL_WEIGHTS = {
    "exportCoverage": 36,
    "signatureAccuracy": 22,
    "typeCoverage": 14,
    "coherence": 18,
    "externalValidation": 10,
}

NAIVE_WEIGHTS = {
    "exportCoverage": 45,
    "signatureAccuracy": 25,
    "typeCoverage": 20,
    "coherence": 0,
    "externalValidation": 10,
}

CATEGORIES = [
    "exportCoverage",
    "signatureAccuracy",
    "typeCoverage",
    "coherence",
    "externalValidation",
]

DEFAULT_THRESHOLD = 80


# --- Helpers ---


def round2(value):
    """Round to 2 decimal places using JavaScript-compatible rounding.

    JavaScript Math.round rounds .5 up (away from zero for positives).
    Python's built-in round uses banker's rounding (.5 to even).
    We replicate JS behavior: floor(value * 100 + 0.5) / 100.
    """
    return math.floor(value * 100 + 0.5) / 100


def make_error(message):
    return {"error": message, "code": "INVALID_INPUT"}


# --- Validation ---


def validate_input(inp):
    if inp is None or not isinstance(inp, dict):
        return "Input must be a JSON object"

    if not inp.get("mode") or inp["mode"] not in ("contextual", "naive"):
        return 'Missing or invalid required field: mode (must be "contextual" or "naive")'

    valid_tiers = ["Quick", "Forge", "Forge+", "Deep"]
    if not inp.get("tier") or inp["tier"] not in valid_tiers:
        return f"Missing or invalid required field: tier (must be one of: {', '.join(valid_tiers)})"

    if "scores" not in inp or not isinstance(inp.get("scores"), dict):
        return "Missing required field: scores"

    if inp["scores"].get("exportCoverage") is None:
        return "scores.exportCoverage is required and cannot be null"

    threshold = inp.get("threshold")
    if threshold is not None:
        if not isinstance(threshold, (int, float)) or threshold < 0 or threshold > 100:
            return "threshold must be a number between 0 and 100"

    for cat in CATEGORIES:
        score = inp["scores"].get(cat)
        if score is not None:
            if not isinstance(score, (int, float)):
                return f"scores.{cat} must be a number or null, got: {type(score).__name__}"
            if score < 0 or score > 100:
                return f"scores.{cat} must be between 0 and 100, got: {score}"

    return None


# --- Core Scoring Function ---


def compute_score(inp):
    # 1. Validate
    validation_error = validate_input(inp)
    if validation_error:
        return make_error(validation_error)

    mode = inp["mode"]
    tier = inp["tier"]
    docs_only = inp.get("docsOnly") is True
    state2 = inp.get("state2") is True
    threshold = inp.get("threshold") if inp.get("threshold") is not None else DEFAULT_THRESHOLD
    scores = inp["scores"]

    # 2. Select base weight table
    base_weights = dict(NAIVE_WEIGHTS if mode == "naive" else CONTEXTUAL_WEIGHTS)

    # 3. Determine skip set
    skip_reasons = {}
    skip_sig_type = tier == "Quick" or docs_only or state2

    if skip_sig_type:
        reasons = []
        if tier == "Quick":
            reasons.append("Quick tier")
        if docs_only:
            reasons.append("docs-only mode")
        if state2:
            reasons.append("State 2 (provenance-map)")
        reason = " + ".join(reasons)
        skip_reasons["signatureAccuracy"] = reason
        skip_reasons["typeCoverage"] = reason

    if scores.get("externalValidation") is None:
        skip_reasons["externalValidation"] = "No external validators available"

    # Collect warnings
    warnings = []
    for cat in skip_reasons:
        if scores.get(cat) is not None:
            warnings.append(
                f"{cat} score provided ({scores[cat]}) but category is skipped — score ignored"
            )

    # Validate active categories have scores
    skipped_set = set(skip_reasons.keys())
    for cat in CATEGORIES:
        is_active = cat not in skipped_set and base_weights[cat] > 0
        score_missing = scores.get(cat) is None
        if is_active and score_missing:
            return make_error(
                f"Category {cat} is active but score is null. "
                "Provide a numeric score or set the appropriate skip condition."
            )

    # 4. Redistribute weights
    adjusted_weights = dict(base_weights)
    for cat in skip_reasons:
        adjusted_weights[cat] = 0

    sum_active_weights = sum(adjusted_weights[cat] for cat in CATEGORIES)

    final_weights = {}
    for cat in CATEGORIES:
        if adjusted_weights[cat] == 0:
            final_weights[cat] = 0
        else:
            final_weights[cat] = round2((adjusted_weights[cat] / sum_active_weights) * 100)

    # 5. Compute weighted scores
    weighted_scores = {}
    for cat in CATEGORIES:
        if final_weights[cat] == 0:
            weighted_scores[cat] = 0
        else:
            weighted_scores[cat] = round2((final_weights[cat] / 100) * scores[cat])

    # 6. Compute total
    total_score = round2(sum(weighted_scores[cat] for cat in CATEGORIES))

    # Weight sum for verification
    weight_sum = round2(sum(final_weights[cat] for cat in CATEGORIES))

    # 7. Determine result
    result = "PASS" if total_score >= threshold else "FAIL"

    # 8. Build output
    active_categories = [cat for cat in CATEGORIES if final_weights[cat] > 0]
    skipped_categories = [
        cat for cat in CATEGORIES if cat in skipped_set or base_weights[cat] == 0
    ]

    # Build scores echo with null preservation
    scores_echo = {}
    for cat in CATEGORIES:
        scores_echo[cat] = scores.get(cat)

    output = {
        "input": {
            "mode": mode,
            "tier": tier,
            "docsOnly": docs_only,
            "state2": state2,
            "threshold": threshold,
            "scores": scores_echo,
        },
        "activeCategories": active_categories,
        "skippedCategories": skipped_categories,
        "skipReasons": skip_reasons,
        "weights": final_weights,
        "weightedScores": weighted_scores,
        "totalScore": total_score,
        "threshold": threshold,
        "result": result,
        "weightSum": weight_sum,
    }

    if warnings:
        output["warnings"] = warnings

    return output


# --- CLI Entry Point ---

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 compute-score.py '<JSON>'", file=sys.stderr)
        print(
            'Example: python3 compute-score.py \'{"mode":"contextual","tier":"Deep",'
            '"scores":{"exportCoverage":92,"signatureAccuracy":85,"typeCoverage":100,'
            '"coherence":80,"externalValidation":78}}\'',
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        data = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        print(
            json.dumps(make_error(f"Invalid JSON: {sys.argv[1][:100]}"), indent=2)
        )
        sys.exit(1)

    result = compute_score(data)
    print(json.dumps(result, indent=2))
    sys.exit(1 if "error" in result else 0)
