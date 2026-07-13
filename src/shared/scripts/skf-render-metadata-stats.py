#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Render Metadata Stats — derive metadata.json's computed stats block and
confidence_distribution deterministically from the staged provenance-map.

Two places in `skf-create-skill` do the same pure arithmetic over the staged
staging JSON, by hand, every run:

  1. **compile.md §4 (Build metadata.json)** bins each provenance entry by its
     `signature_source` tier into `confidence_distribution.{t1,t1_low,t2,t3}`,
     counts documented exports, and computes the coverage ratios. This is the
     step that documents the LLM's recurring miscount — binning ~8 T2
     annotations + ~80 T3 doc items *on top of* 59 exports and getting a
     distribution that sums to 147 ≠ 59.

  2. **validate.md §7 (Validate metadata.json)** re-derives the same sums,
     ratios, and array-length counts to auto-fix any drift ("these are
     computed values").

Both are pure projections over the provenance-map plus a small judgment
payload — the values the prompt genuinely decides (which count feeds
`exports_public_api`, the gated `effective_denominator`). This script owns the
arithmetic so the prompt stops doing it by hand; the judgment stays in the
prompt and is passed in.

Because the distribution is a `Counter` over `entries[]` — one entry counted
once by its tier — the script **cannot** reproduce the 147≠59 miscount: the
four bins always sum to the number of entries with a recognized
`signature_source`, never to an enrichment total.

Shape carve-outs (mirroring `skf-test-skill` coverage-check §4b): the
distribution ALWAYS bins `entries[]`, so it always sums to `len(entries)`. What
`exports_documented` equals is what differs by shape:

  - **library** — `exports_documented = len(entries)`; the four bins sum to it.
  - **reference-app** — `entries[]` are per-citation, so the distribution sums
    to the *citation count* (= `len(entries)`), NOT to `exports_documented`
    (which is the pattern-surface proxy `pattern_surfaces_documented`, a
    judgment value). `effective_denominator` is never emitted.
  - **stack** — `entries[]` are the cited constituent contracts, so the
    distribution sums to the *constituent count* (= `len(entries)`), NOT to
    `exports_documented` (a stack's own barrel is empty by design).

Modes
-----

Default (compute) — read the provenance-map path + a judgment payload on stdin;
emit the derived `stats` + `confidence_distribution` + a `coherence` report.
`compile.md §4` writes the returned values verbatim.

`--check <metadata.json>` — read the provenance-map path + the on-disk
metadata.json; re-derive the computed values (taking the judgment values —
`exports_public_api`, `exports_internal`, `effective_denominator` — from the
on-disk metadata itself) and compare against what is on disk. `coherence.ok`
is false with a `violations[]` list when the on-disk file drifted; the emitted
`stats`/`confidence_distribution` are the corrected values `validate.md §7`
writes back.

Judgment payload (stdin JSON, compute mode)::

    {
      "exports_public_api":  40,          # int  — public-entry-point export count (judgment)
      "exports_internal":    19,          # int  — non-underscore internal export count (judgment)
      "effective_denominator": 12,        # int|null — optional, stratified-scope monorepo only
      "pattern_surfaces_documented": 8,   # int  — reference-app only (exports_documented proxy)
      "exports_documented":  0,           # int  — stack only (own-barrel count, usually 0)
      "scripts": [ ... ],                 # list — scripts[] array (or "scripts_count": int)
      "assets":  [ ... ]                  # list — assets[]  array (or "assets_count":  int)
    }

Output JSON (both modes)::

    {
      "stats": {
        "exports_documented":  59,
        "exports_public_api":  40,
        "exports_internal":    19,
        "exports_total":       59,
        "public_api_coverage": 1.475,     # documented/public_api, null if public_api == 0
        "total_coverage":      1.0,        # documented/total,      null if total == 0
        "scripts_count":       0,
        "assets_count":        0
      },
      "confidence_distribution": {"t1": 40, "t1_low": 5, "t2": 10, "t3": 4},
      "coherence": {"ok": true, "violations": []}
    }

Exit codes:
  0  — coherence ok (no violations)
  1  — coherence violations present (drift to auto-fix / bad signature_source);
       the JSON on stdout is still authoritative — rely on it, not the code
  2  — usage / IO / JSON-decode error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# Canonical signature_source tiers → distribution bin keys. Compared
# case-insensitively so "T1-low" / "t1-low" both land in t1_low.
_SIG_MAP = {"T1": "t1", "T1-LOW": "t1_low", "T2": "t2", "T3": "t3"}
_VALID_SHAPES = ("library", "stack", "reference-app")
_DIST_KEYS = ("t1", "t1_low", "t2", "t3")


# --------------------------------------------------------------------------
# IO
# --------------------------------------------------------------------------


def load_json(path: Path) -> object:
    """Read + parse a JSON file. Raises ValueError on any failure."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"failed to read {path}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {path}: {exc}") from exc


# --------------------------------------------------------------------------
# Pure derivations
# --------------------------------------------------------------------------


def bin_signature_sources(entries: list) -> tuple[dict[str, int], int]:
    """Counter over provenance entries by signature_source tier.

    Returns (distribution, unrecognized) where distribution has the four
    canonical bin keys and `unrecognized` counts entries whose
    `signature_source` is missing or not one of T1/T1-low/T2/T3. Counting
    entries (each exactly once, by its own tier) is what makes the 147≠59
    enrichment-fold miscount structurally impossible.
    """
    dist = {k: 0 for k in _DIST_KEYS}
    unrecognized = 0
    if not isinstance(entries, list):
        return dist, unrecognized
    for entry in entries:
        raw = entry.get("signature_source") if isinstance(entry, dict) else None
        key = _SIG_MAP.get(raw.strip().upper()) if isinstance(raw, str) else None
        if key is not None:
            dist[key] += 1
        else:
            unrecognized += 1
    return dist, unrecognized


def ratio(numerator: int, denominator: int) -> float | None:
    """Coverage ratio; None when the denominator is 0 (per the spec's
    null-when-empty rule). Rounded to 4 dp for deterministic output."""
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def _int(value: object, default: int = 0) -> int:
    """Coerce a judgment value to int, tolerating None / bad types."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _count(judgment: dict, arr_key: str, count_key: str) -> int:
    """Length of an array field if present, else the scalar count field."""
    arr = judgment.get(arr_key)
    if isinstance(arr, list):
        return len(arr)
    return _int(judgment.get(count_key), 0)


def count_file_entries_by_type(prov: dict) -> dict[str, int]:
    """Count provenance-map file_entries[] by file_type."""
    counts = {"script": 0, "asset": 0, "doc": 0, "other": 0}
    fe = prov.get("file_entries")
    if isinstance(fe, list):
        for row in fe:
            if not isinstance(row, dict):
                counts["other"] += 1
                continue
            ft = row.get("file_type")
            counts[ft if ft in ("script", "asset", "doc") else "other"] += 1
    return counts


def derive_stats(prov: dict, judgment: dict, shape: str = "library") -> dict:
    """Derive the stats block + confidence_distribution for one skill.

    `prov` is the parsed provenance-map. `judgment` carries the values the
    prompt decides. `shape` selects how `exports_documented` is set. The
    distribution always bins `entries[]`.
    """
    entries = prov.get("entries")
    entries = entries if isinstance(entries, list) else []
    dist, unrecognized = bin_signature_sources(entries)
    entry_count = len(entries)

    if shape == "reference-app":
        exports_documented = _int(judgment.get("pattern_surfaces_documented"), 0)
    elif shape == "stack":
        exports_documented = _int(judgment.get("exports_documented"), 0)
    else:  # library
        exports_documented = entry_count

    exports_public_api = _int(judgment.get("exports_public_api"), 0)
    exports_internal = _int(judgment.get("exports_internal"), 0)
    exports_total = exports_public_api + exports_internal

    stats: dict[str, object] = {
        "exports_documented": exports_documented,
        "exports_public_api": exports_public_api,
        "exports_internal": exports_internal,
        "exports_total": exports_total,
        "public_api_coverage": ratio(exports_documented, exports_public_api),
        "total_coverage": ratio(exports_documented, exports_total),
        "scripts_count": _count(judgment, "scripts", "scripts_count"),
        "assets_count": _count(judgment, "assets", "assets_count"),
    }

    # reference-app: emit the pattern-surface proxy alongside exports_documented
    if shape == "reference-app":
        stats["pattern_surfaces_documented"] = exports_documented

    # effective_denominator: optional, and never for a reference app (its
    # coverage basis is pattern surfaces, not an export barrel).
    eff = judgment.get("effective_denominator")
    if eff is not None and shape != "reference-app":
        stats["effective_denominator"] = _int(eff, 0)

    return {
        "stats": stats,
        "confidence_distribution": dist,
        "_derivation": {
            "shape": shape,
            "entry_count": entry_count,
            "distribution_sum": sum(dist.values()),
            "unrecognized_signature_source": unrecognized,
        },
    }


# --------------------------------------------------------------------------
# Coherence
# --------------------------------------------------------------------------


def _cmp_int(violations: list, field: str, expected, actual, note: str | None = None) -> None:
    if expected != actual:
        v = {"field": field, "expected": expected, "actual": actual}
        if note:
            v["note"] = note
        violations.append(v)


def _cmp_ratio(violations: list, field: str, expected, actual) -> None:
    norm = round(float(actual), 4) if isinstance(actual, (int, float)) and not isinstance(actual, bool) else actual
    exp = round(expected, 4) if isinstance(expected, float) else expected
    if exp != norm:
        violations.append({"field": field, "expected": expected, "actual": actual})


def coherence_compute(derived: dict, prov: dict) -> dict:
    """Internal-consistency checks for compute mode.

    The distribution must account for every provenance entry (a bin-sum below
    the entry count means some entries carry a missing/unrecognized
    signature_source). When the provenance-map already tracks scripts/assets in
    file_entries[], those counts must agree with the stats counts.
    """
    violations: list[dict] = []
    entry_count = derived["_derivation"]["entry_count"]
    dist_sum = derived["_derivation"]["distribution_sum"]
    if dist_sum != entry_count:
        missing = entry_count - dist_sum
        violations.append({
            "field": "confidence_distribution",
            "expected": entry_count,
            "actual": dist_sum,
            "note": (
                f"{missing} provenance entr{'y' if abs(missing) == 1 else 'ies'} "
                "with missing or unrecognized signature_source"
            ),
        })

    fe = count_file_entries_by_type(prov)
    sc = derived["stats"]["scripts_count"]
    ac = derived["stats"]["assets_count"]
    # Conservative: only cross-check a type once the provenance-map actually
    # carries rows of that type (file_entries are written in a later compile
    # section, so an empty count is "not yet populated", not "zero").
    if fe["script"] > 0:
        _cmp_int(violations, "stats.scripts_count", fe["script"], sc,
                 "stats.scripts_count disagrees with provenance-map file_entries[file_type=script]")
    if fe["asset"] > 0:
        _cmp_int(violations, "stats.assets_count", fe["asset"], ac,
                 "stats.assets_count disagrees with provenance-map file_entries[file_type=asset]")

    return {"ok": not violations, "violations": violations}


def check_stats(derived: dict, metadata: dict, prov: dict) -> dict:
    """Compare re-derived values against the on-disk metadata.json.

    Every mismatch is a `{field, expected, actual}` violation, where `expected`
    is the re-derived (correct) value and `actual` is what is on disk.
    validate.md §7 either writes `derived` verbatim or fixes each violation.
    """
    violations: list[dict] = []
    m_stats = metadata.get("stats") if isinstance(metadata.get("stats"), dict) else {}
    d_stats = derived["stats"]

    _cmp_int(violations, "stats.exports_documented", d_stats["exports_documented"],
             m_stats.get("exports_documented"))
    _cmp_int(violations, "stats.exports_total", d_stats["exports_total"],
             m_stats.get("exports_total"))
    _cmp_ratio(violations, "stats.public_api_coverage", d_stats["public_api_coverage"],
               m_stats.get("public_api_coverage"))
    _cmp_ratio(violations, "stats.total_coverage", d_stats["total_coverage"],
               m_stats.get("total_coverage"))

    m_dist = metadata.get("confidence_distribution") if isinstance(metadata.get("confidence_distribution"), dict) else {}
    for key in _DIST_KEYS:
        _cmp_int(violations, f"confidence_distribution.{key}",
                 derived["confidence_distribution"][key], m_dist.get(key))

    # array length vs its stats count (validate.md §7: "verify
    # stats.scripts_count/stats.assets_count match array lengths")
    scripts_arr = metadata.get("scripts")
    if isinstance(scripts_arr, list):
        _cmp_int(violations, "stats.scripts_count", len(scripts_arr),
                 m_stats.get("scripts_count"),
                 "stats.scripts_count does not match len(scripts[])")
    assets_arr = metadata.get("assets")
    if isinstance(assets_arr, list):
        _cmp_int(violations, "stats.assets_count", len(assets_arr),
                 m_stats.get("assets_count"),
                 "stats.assets_count does not match len(assets[])")

    # provenance-map file_entries count vs metadata scripts/assets counts
    if isinstance(scripts_arr, list) or isinstance(assets_arr, list):
        fe = count_file_entries_by_type(prov)
        claimed_sc = _int(m_stats.get("scripts_count"), 0)
        claimed_ac = _int(m_stats.get("assets_count"), 0)
        if fe["script"] != claimed_sc and (fe["script"] > 0 or claimed_sc > 0):
            _cmp_int(violations, "provenance.file_entries.script", claimed_sc, fe["script"],
                     "provenance-map file_entries[file_type=script] count disagrees with metadata scripts_count")
        if fe["asset"] != claimed_ac and (fe["asset"] > 0 or claimed_ac > 0):
            _cmp_int(violations, "provenance.file_entries.asset", claimed_ac, fe["asset"],
                     "provenance-map file_entries[file_type=asset] count disagrees with metadata assets_count")

    return {"ok": not violations, "violations": violations}


def detect_shape(metadata: dict) -> str:
    """Infer the shape from an on-disk metadata.json (used by --check when
    --shape is not supplied)."""
    if metadata.get("scope_type") == "reference-app":
        return "reference-app"
    if metadata.get("skill_type") == "stack":
        return "stack"
    return "library"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _read_stdin_judgment() -> dict:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    if not raw.strip():
        return {}
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("stdin judgment payload must be a JSON object")
    return payload


def _emit(result: dict, out_path: str | None) -> None:
    text = json.dumps(result, indent=2)
    if out_path:
        Path(out_path).write_text(text + "\n", encoding="utf-8")
    else:
        sys.stdout.write(text + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-render-metadata-stats",
        description=(
            "Derive metadata.json stats + confidence_distribution from the staged "
            "provenance-map (compute mode), or re-verify an on-disk metadata.json "
            "against the map (--check). Replaces the hand-binning/summing in "
            "skf-create-skill compile.md §4 and validate.md §7."
        ),
    )
    parser.add_argument("provenance_map", help="path to the staged provenance-map.json")
    parser.add_argument(
        "--check", metavar="METADATA_JSON", dest="check",
        help="verify this on-disk metadata.json against the provenance-map instead of "
             "reading judgment from stdin; emits corrected stats + a violations list",
    )
    parser.add_argument(
        "--shape", choices=_VALID_SHAPES, default=None,
        help="assembly shape (default: library in compute mode; inferred from "
             "metadata.json in --check mode). Selects what exports_documented equals.",
    )
    parser.add_argument("-o", "--output", dest="output", help="write JSON here (default: stdout)")
    parser.add_argument("--verbose", action="store_true", help="diagnostics to stderr")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    prov_path = Path(args.provenance_map)
    if not prov_path.is_file():
        sys.stderr.write(f"error: provenance-map not found: {prov_path}\n")
        return 2
    try:
        prov = load_json(prov_path)
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    if not isinstance(prov, dict):
        sys.stderr.write("error: provenance-map must be a JSON object at top level\n")
        return 2

    if args.check:
        meta_path = Path(args.check)
        if not meta_path.is_file():
            sys.stderr.write(f"error: metadata.json not found: {meta_path}\n")
            return 2
        try:
            metadata = load_json(meta_path)
        except ValueError as exc:
            sys.stderr.write(f"error: {exc}\n")
            return 2
        if not isinstance(metadata, dict):
            sys.stderr.write("error: metadata.json must be a JSON object at top level\n")
            return 2
        shape = args.shape or detect_shape(metadata)
        m_stats = metadata.get("stats") if isinstance(metadata.get("stats"), dict) else {}
        judgment = {
            "exports_public_api": m_stats.get("exports_public_api"),
            "exports_internal": m_stats.get("exports_internal"),
            "effective_denominator": m_stats.get("effective_denominator"),
            "pattern_surfaces_documented": m_stats.get("pattern_surfaces_documented"),
            "exports_documented": m_stats.get("exports_documented"),
            "scripts": metadata.get("scripts"),
            "assets": metadata.get("assets"),
        }
        derived = derive_stats(prov, judgment, shape)
        coherence = check_stats(derived, metadata, prov)
    else:
        try:
            judgment = _read_stdin_judgment()
        except (ValueError, json.JSONDecodeError) as exc:
            sys.stderr.write(f"error: {exc}\n")
            return 2
        shape = args.shape or "library"
        derived = derive_stats(prov, judgment, shape)
        coherence = coherence_compute(derived, prov)

    if args.verbose:
        sys.stderr.write(
            f"shape={shape} entries={derived['_derivation']['entry_count']} "
            f"dist_sum={derived['_derivation']['distribution_sum']} "
            f"unrecognized={derived['_derivation']['unrecognized_signature_source']} "
            f"violations={len(coherence['violations'])}\n"
        )

    result = {
        "stats": derived["stats"],
        "confidence_distribution": derived["confidence_distribution"],
        "coherence": coherence,
    }
    _emit(result, args.output)
    return 0 if coherence["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
