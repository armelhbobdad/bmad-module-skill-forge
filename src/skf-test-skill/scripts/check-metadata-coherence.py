#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Deterministic metadata export-count coherence cross-check.

Count-drift helper for the SKF test-skill workflow (coverage-check.md §4b).
Distinct from reconcile-coverage.py (which owns the coverage *numerator*
intersection) and compute-score.py (weights + INCONCLUSIVE floor): this script
performs the §4b *count-drift* arithmetic — binning the collected export counts
into the two canonical clusters and computing the intra-cluster / cross-cluster
percentage divergences — so the "13% drift → emit / 4% → skip" decision no
longer swings between runs on an in-prompt eyeball.

It reproduces exactly the §4b operationalized checks:

  * Cluster A — public-barrel surface (`__init__.py` / `index.ts` / `lib.rs`
    re-exports): `stats.exports_public_api`, `exports[].length`.

  * Cluster B — documented surface (extracted + documented, incl. methods and
    submodule members): `stats.exports_documented`, the provenance-map
    **named-export count** (entries whose `export_name` contains `::` are
    excluded — impl-block methods roll up under an already-counted type), and
    the `confidence_distribution` sum (`t1 + t1_low + t2 + t3`).

  * Intra-cluster divergence (Medium): within a cluster with >=2 present counts,
    if the largest and smallest disagree by more than the drift threshold
    (default 10%) of the larger, emit `metadata drift — {barrel|documented-surface}
    export counts diverge`.

  * Cross-cluster divergence (Info): if both clusters resolved to a
    representative count (the higher of each cluster's present counts) and they
    differ by more than the threshold, emit `multi-denominator reporting —
    barrel vs documented surface` (expected for skills whose documented surface
    intentionally exceeds the barrel — not drift, just made auditable).

Stack skills (`skill_type == "stack"`) and reference apps
(`scope_type == "reference-app"`) are skipped: their three counts measure
intentionally *different* surfaces, so comparing them yields only false drift.

CLI usage:
  uv run check-metadata-coherence.py '<JSON>'                  # positional
  uv run check-metadata-coherence.py --json-input '<JSON>'     # explicit flag
  cat input.json | uv run check-metadata-coherence.py --stdin  # piped

Input schema (one object; omit any count that is absent for the skill):
  {
    "skillType": "stack" | ... | null,          # metadata.json.skill_type
    "scopeType": "reference-app" | ... | null,   # metadata.json.scope_type
    "clusterA": {
      "exports_public_api": <int|null>,
      "exports_length": <int|null>
    },
    "clusterB": {
      "exports_documented": <int|null>
    },
    "provenanceExportNames": ["Type::method", "foo", ...] | null,  # raw entry names
    "confidenceDistribution": {"t1": N, "t1_low": N, "t2": N, "t3": N} | null,
    "driftThresholdPct": 10                       # optional, default 10
  }

Output (stdout, one object):
  {
    "skipped": <bool>,
    "skipReason": <str|null>,
    "driftThresholdPct": <int>,
    "clusterACounts": {label: count, ...},        # present counts only
    "clusterBCounts": {label: count, ...},        # present counts only, incl. derived
    "findings": [
      {"severity": "Medium|Info", "title": "...", "detail": "...",
       "category": "structural/metadata coherence", "driftPct": <int>}
    ]
  }

Exit codes:
  0  — cross-check emitted successfully (findings may be empty)
  1  — no input / input could not be parsed as JSON
  2  — input parsed but schema/semantics invalid (error object emitted as JSON)
"""

from __future__ import annotations

import argparse
import json
import sys

DEFAULT_DRIFT_PCT = 10
CATEGORY = "structural/metadata coherence"

# Stable source labels used in finding bodies (match coverage-check.md §4b examples).
LABEL_EXPORTS_PUBLIC_API = "stats.exports_public_api"
LABEL_EXPORTS_LENGTH = "exports[].length"
LABEL_EXPORTS_DOCUMENTED = "stats.exports_documented"
LABEL_PROVENANCE_NAMED = "provenance named-exports"
LABEL_CONFIDENCE_SUM = "confidence_distribution sum"


def make_error(message):
    return {"error": message, "code": "INVALID_INPUT"}


def _as_count(value, label, errors):
    """Return value if it is a non-negative int (not bool), else record an error."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        errors.append(f"{label} must be a non-negative integer (got {value!r})")
        return None
    return value


def _provenance_named_count(names, errors):
    """Count provenance entry names, excluding `::` impl-block methods."""
    if names is None:
        return None
    if not isinstance(names, list):
        errors.append("provenanceExportNames must be a list of strings")
        return None
    return sum(1 for n in names if isinstance(n, str) and n and "::" not in n)


def _confidence_sum(dist, errors):
    """Sum t1 + t1_low + t2 + t3 (each defaulting to 0 when absent)."""
    if dist is None:
        return None
    if not isinstance(dist, dict):
        errors.append("confidenceDistribution must be an object")
        return None
    total = 0
    for tier in ("t1", "t1_low", "t2", "t3"):
        v = dist.get(tier, 0)
        if v is None:
            v = 0
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            errors.append(
                f"confidenceDistribution.{tier} must be a non-negative integer (got {v!r})"
            )
            continue
        total += v
    return total


def drift_pct(counts):
    """Percentage divergence of the extreme counts: (max - min) / max * 100."""
    hi = max(counts)
    lo = min(counts)
    if hi == 0:
        return 0.0
    return (hi - lo) / hi * 100.0


def _intra_cluster_finding(present, cluster_label, title, threshold):
    """Emit an intra-cluster Medium finding when the extremes diverge > threshold."""
    if len(present) < 2:
        return None
    values = [c for _, c in present]
    pct = drift_pct(values)
    if pct <= threshold:
        return None
    enumerated = ", ".join(f"{label}={count}" for label, count in present)
    pct_display = round(pct)
    return {
        "severity": "Medium",
        "title": title,
        "detail": f"{enumerated} → {pct_display}% drift",
        "category": CATEGORY,
        "driftPct": pct_display,
    }


def check(inp):
    """Pure count-drift cross-check. Returns the result object (or an error object)."""
    if inp is None or not isinstance(inp, dict):
        return make_error("Input must be a JSON object")

    threshold = inp.get("driftThresholdPct", DEFAULT_DRIFT_PCT)
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or threshold < 0:
        return make_error("driftThresholdPct must be a non-negative number")

    skill_type = inp.get("skillType")
    scope_type = inp.get("scopeType")
    if skill_type == "stack":
        return {
            "skipped": True,
            "skipReason": "stack skill — the three counts measure intentionally "
            "different surfaces (empty own barrel, cited constituent contracts, "
            "per-constituent confidence bins); comparing them yields only false drift",
            "driftThresholdPct": threshold,
            "clusterACounts": {},
            "clusterBCounts": {},
            "findings": [],
        }
    if scope_type == "reference-app":
        return {
            "skipped": True,
            "skipReason": "reference app — counts measure pattern surfaces vs "
            "per-citation provenance, not a shared export barrel; comparing them "
            "yields only false drift",
            "driftThresholdPct": threshold,
            "clusterACounts": {},
            "clusterBCounts": {},
            "findings": [],
        }

    cluster_a_in = inp.get("clusterA") or {}
    cluster_b_in = inp.get("clusterB") or {}
    if not isinstance(cluster_a_in, dict) or not isinstance(cluster_b_in, dict):
        return make_error("clusterA and clusterB must be objects when present")

    errors: list[str] = []

    exports_public_api = _as_count(
        cluster_a_in.get("exports_public_api"), LABEL_EXPORTS_PUBLIC_API, errors
    )
    exports_length = _as_count(
        cluster_a_in.get("exports_length"), LABEL_EXPORTS_LENGTH, errors
    )
    exports_documented = _as_count(
        cluster_b_in.get("exports_documented"), LABEL_EXPORTS_DOCUMENTED, errors
    )
    provenance_named = _provenance_named_count(inp.get("provenanceExportNames"), errors)
    confidence_sum = _confidence_sum(inp.get("confidenceDistribution"), errors)

    if errors:
        return make_error("; ".join(errors))

    # Present-count lists preserve a stable cluster-canonical order for reporting.
    cluster_a = [
        (LABEL_EXPORTS_PUBLIC_API, exports_public_api),
        (LABEL_EXPORTS_LENGTH, exports_length),
    ]
    cluster_a = [(label, c) for label, c in cluster_a if c is not None]

    cluster_b = [
        (LABEL_EXPORTS_DOCUMENTED, exports_documented),
        (LABEL_PROVENANCE_NAMED, provenance_named),
        (LABEL_CONFIDENCE_SUM, confidence_sum),
    ]
    cluster_b = [(label, c) for label, c in cluster_b if c is not None]

    findings = []

    a_finding = _intra_cluster_finding(
        cluster_a, "barrel", "metadata drift — barrel export counts diverge", threshold
    )
    if a_finding:
        findings.append(a_finding)

    b_finding = _intra_cluster_finding(
        cluster_b,
        "documented-surface",
        "metadata drift — documented-surface export counts diverge",
        threshold,
    )
    if b_finding:
        findings.append(b_finding)

    # Cross-cluster: representative = the higher of each cluster's present counts.
    if cluster_a and cluster_b:
        repr_a = max(c for _, c in cluster_a)
        repr_b = max(c for _, c in cluster_b)
        pct = drift_pct([repr_a, repr_b])
        if pct > threshold:
            findings.append(
                {
                    "severity": "Info",
                    "title": "multi-denominator reporting — barrel vs documented surface",
                    "detail": f"barrel={repr_a}, documented={repr_b}",
                    "category": CATEGORY,
                    "driftPct": round(pct),
                }
            )

    return {
        "skipped": False,
        "skipReason": None,
        "driftThresholdPct": threshold,
        "clusterACounts": {label: count for label, count in cluster_a},
        "clusterBCounts": {label: count for label, count in cluster_b},
        "findings": findings,
    }


# --- CLI --------------------------------------------------------------------


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="check-metadata-coherence",
        description=(
            "Deterministic metadata export-count coherence cross-check "
            "(coverage-check.md §4b). Bins the collected export counts into the "
            "two canonical clusters and emits the intra-cluster / cross-cluster "
            "drift findings so the count-drift decision is reproducible."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  uv run check-metadata-coherence.py "
            "'{\"clusterA\":{\"exports_public_api\":55,\"exports_length\":48},"
            "\"clusterB\":{\"exports_documented\":114}}'"
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
    return parser


def _resolve_input(args):
    if args.stdin:
        return sys.stdin.read()
    if args.json_input_flag is not None:
        return args.json_input_flag
    if args.json_input is not None:
        return args.json_input
    return ""


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    raw = _resolve_input(args)
    if not raw.strip():
        parser.print_usage(file=sys.stderr)
        print(
            "error: no input provided (positional arg, --json-input, or --stdin)",
            file=sys.stderr,
        )
        return 1

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps(make_error(f"Invalid JSON: {exc.msg}"), indent=2))
        return 1

    result = check(data)
    print(json.dumps(result, indent=2))
    if isinstance(result, dict) and result.get("code") == "INVALID_INPUT":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
