#!/usr/bin/env python3
"""Tests for skf-render-metadata-stats.py.

The renderer is pure (reads a provenance-map + judgment payload, does
arithmetic) so most tests call derive_stats() / check_stats() /
coherence_compute() directly. A few drive the CLI via subprocess to cover
stdin parsing, --check, and exit codes.

Core guarantees under test:
  - the distribution is a Counter over entries[] (each entry once), so it can
    NEVER fold enrichment totals in — the documented 147≠59 miscount is
    structurally impossible
  - coverage ratios are null when the denominator is 0
  - array-length / file-entry cross-checks surface as coherence violations
  - shape carve-outs: reference-app distribution sums to the citation count,
    not to exports_documented
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-render-metadata-stats.py"

spec = importlib.util.spec_from_file_location("skf_render_metadata_stats", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _entries(t1=0, t1_low=0, t2=0, t3=0, *, extra=None):
    """Build a provenance entries[] list with the given per-tier counts."""
    out = []
    for tier, n in (("T1", t1), ("T1-low", t1_low), ("T2", t2), ("T3", t3)):
        for i in range(n):
            out.append({"export_name": f"{tier}_{i}", "signature_source": tier})
    if extra:
        out.extend(extra)
    return out


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# bin_signature_sources / distribution — the 147≠59 regression
# --------------------------------------------------------------------------


class TestDistribution:
    def test_counts_entries_once_by_tier(self):
        # 59 entries: 40 T1 / 5 T1-low / 10 T2 / 4 T3
        prov = {"entries": _entries(40, 5, 10, 4)}
        result = mod.derive_stats(prov, {"exports_public_api": 40, "exports_internal": 19})
        dist = result["confidence_distribution"]
        assert dist == {"t1": 40, "t1_low": 5, "t2": 10, "t3": 4}
        # sum == exports_documented == entry count: the miscount is impossible
        assert sum(dist.values()) == 59
        assert result["stats"]["exports_documented"] == 59

    def test_cannot_fold_enrichment_totals(self):
        # Even if the *caller* passed enrichment counts, the script only ever
        # counts entries — there is no code path that adds 8 + 80 to 59.
        prov = {"entries": _entries(40, 5, 10, 4)}
        result = mod.derive_stats(
            prov,
            {
                "exports_public_api": 40,
                "exports_internal": 19,
                # bogus fields the script must ignore
                "t2_annotation_count": 8,
                "t3_doc_item_count": 80,
            },
        )
        assert sum(result["confidence_distribution"].values()) == 59

    def test_tier_label_case_insensitive(self):
        prov = {"entries": [
            {"signature_source": "t1"},
            {"signature_source": "T1-LOW"},
            {"signature_source": "t1-low"},
            {"signature_source": "T2"},
        ]}
        result = mod.derive_stats(prov, {})
        assert result["confidence_distribution"] == {"t1": 1, "t1_low": 2, "t2": 1, "t3": 0}

    def test_unrecognized_signature_source_flagged_in_compute(self):
        prov = {"entries": [
            {"signature_source": "T1"},
            {"signature_source": "T1"},
            {"signature_source": "bogus"},   # unrecognized
            {"export_name": "x"},             # missing
        ]}
        result = mod.derive_stats(prov, {})
        assert sum(result["confidence_distribution"].values()) == 2
        coherence = mod.coherence_compute(result, prov)
        assert coherence["ok"] is False
        v = next(x for x in coherence["violations"] if x["field"] == "confidence_distribution")
        assert v["expected"] == 4 and v["actual"] == 2


# --------------------------------------------------------------------------
# Coverage ratios
# --------------------------------------------------------------------------


class TestCoverage:
    def test_public_api_coverage_null_when_zero(self):
        prov = {"entries": _entries(3)}
        result = mod.derive_stats(prov, {"exports_public_api": 0, "exports_internal": 0})
        assert result["stats"]["public_api_coverage"] is None
        assert result["stats"]["total_coverage"] is None

    def test_full_coverage(self):
        prov = {"entries": _entries(40)}
        result = mod.derive_stats(prov, {"exports_public_api": 40, "exports_internal": 0})
        assert result["stats"]["exports_total"] == 40
        assert result["stats"]["public_api_coverage"] == 1.0
        assert result["stats"]["total_coverage"] == 1.0

    def test_partial_coverage_rounded(self):
        prov = {"entries": _entries(59)}  # documented = 59
        result = mod.derive_stats(prov, {"exports_public_api": 60, "exports_internal": 0})
        assert result["stats"]["public_api_coverage"] == round(59 / 60, 4)

    def test_effective_denominator_passthrough(self):
        prov = {"entries": _entries(5)}
        result = mod.derive_stats(
            prov, {"exports_public_api": 5, "exports_internal": 0, "effective_denominator": 12}
        )
        assert result["stats"]["effective_denominator"] == 12


# --------------------------------------------------------------------------
# scripts / assets counts + coherence
# --------------------------------------------------------------------------


class TestScriptsAssets:
    def test_counts_from_arrays(self):
        prov = {"entries": _entries(2)}
        result = mod.derive_stats(
            prov,
            {"exports_public_api": 2, "exports_internal": 0,
             "scripts": [{"file": "scripts/a.py"}, {"file": "scripts/b.py"}],
             "assets": [{"file": "assets/x.md"}]},
        )
        assert result["stats"]["scripts_count"] == 2
        assert result["stats"]["assets_count"] == 1

    def test_scripts_count_vs_len_scripts_mismatch(self):
        # check mode: on-disk stats.scripts_count (3) disagrees with len(scripts[]) (2)
        prov = {"entries": _entries(2)}
        metadata = {
            "stats": {
                "exports_documented": 2, "exports_public_api": 2, "exports_internal": 0,
                "exports_total": 2, "public_api_coverage": 1.0, "total_coverage": 1.0,
                "scripts_count": 3, "assets_count": 0,
            },
            "confidence_distribution": {"t1": 2, "t1_low": 0, "t2": 0, "t3": 0},
            "scripts": [{"file": "scripts/a.py"}, {"file": "scripts/b.py"}],
        }
        derived = mod.derive_stats(prov, {"exports_public_api": 2, "exports_internal": 0,
                                          "scripts": metadata["scripts"]}, "library")
        coherence = mod.check_stats(derived, metadata, prov)
        assert coherence["ok"] is False
        v = next(x for x in coherence["violations"] if x["field"] == "stats.scripts_count")
        assert v["expected"] == 2 and v["actual"] == 3

    def test_file_entries_script_count_cross_check(self):
        prov = {
            "entries": _entries(2),
            "file_entries": [
                {"file_type": "script"}, {"file_type": "script"}, {"file_type": "doc"},
            ],
        }
        # compute mode: stats.scripts_count (1) disagrees with 2 script file_entries
        derived = mod.derive_stats(prov, {"exports_public_api": 2, "exports_internal": 0,
                                          "scripts_count": 1}, "library")
        coherence = mod.coherence_compute(derived, prov)
        assert coherence["ok"] is False
        v = next(x for x in coherence["violations"] if x["field"] == "stats.scripts_count")
        assert v["expected"] == 2 and v["actual"] == 1


# --------------------------------------------------------------------------
# Shape carve-outs
# --------------------------------------------------------------------------


class TestShapes:
    def test_reference_app_distribution_sums_to_citation_count(self):
        # 59 per-citation entries; pattern surfaces documented = 8
        prov = {"entries": _entries(40, 5, 10, 4)}
        result = mod.derive_stats(
            prov, {"pattern_surfaces_documented": 8}, "reference-app"
        )
        dist = result["confidence_distribution"]
        assert sum(dist.values()) == 59                       # citation count
        assert result["stats"]["exports_documented"] == 8     # NOT the citation count
        assert result["stats"]["pattern_surfaces_documented"] == 8
        # reference-app never carries effective_denominator
        result2 = mod.derive_stats(
            prov, {"pattern_surfaces_documented": 8, "effective_denominator": 99}, "reference-app"
        )
        assert "effective_denominator" not in result2["stats"]
        # citation-count sum is a healthy state, NOT a coherence violation
        assert mod.coherence_compute(result, prov)["ok"] is True

    def test_stack_distribution_sums_to_constituent_count(self):
        # 6 cited constituent-contract entries; own barrel empty
        prov = {"entries": _entries(4, 0, 2, 0)}
        result = mod.derive_stats(prov, {"exports_documented": 0}, "stack")
        assert sum(result["confidence_distribution"].values()) == 6
        assert result["stats"]["exports_documented"] == 0

    def test_check_mode_detects_shape_from_metadata(self):
        prov = {"entries": _entries(3)}
        metadata = {"scope_type": "reference-app", "stats": {"pattern_surfaces_documented": 5}}
        assert mod.detect_shape(metadata) == "reference-app"


# --------------------------------------------------------------------------
# check_stats — drift detection against on-disk metadata
# --------------------------------------------------------------------------


class TestCheckStats:
    def test_clean_metadata_no_violations(self):
        prov = {"entries": _entries(40, 5, 10, 4)}
        metadata = {
            "stats": {
                "exports_documented": 59, "exports_public_api": 40, "exports_internal": 19,
                "exports_total": 59, "public_api_coverage": round(59 / 40, 4),
                "total_coverage": 1.0, "scripts_count": 0, "assets_count": 0,
            },
            "confidence_distribution": {"t1": 40, "t1_low": 5, "t2": 10, "t3": 4},
        }
        derived = mod.derive_stats(
            prov, {"exports_public_api": 40, "exports_internal": 19}, "library"
        )
        assert mod.check_stats(derived, metadata, prov)["ok"] is True

    def test_the_147_miscount_is_caught(self):
        # metadata written with the classic bug: bins folded annotations+docs
        prov = {"entries": _entries(40, 5, 10, 4)}  # correct sum 59
        metadata = {
            "stats": {
                "exports_documented": 59, "exports_public_api": 40, "exports_internal": 19,
                "exports_total": 59, "public_api_coverage": round(59 / 40, 4),
                "total_coverage": 1.0, "scripts_count": 0, "assets_count": 0,
            },
            "confidence_distribution": {"t1": 40, "t1_low": 5, "t2": 18, "t3": 84},  # sum 147
        }
        derived = mod.derive_stats(
            prov, {"exports_public_api": 40, "exports_internal": 19}, "library"
        )
        coherence = mod.check_stats(derived, metadata, prov)
        assert coherence["ok"] is False
        fields = {v["field"] for v in coherence["violations"]}
        assert "confidence_distribution.t2" in fields
        assert "confidence_distribution.t3" in fields

    def test_coverage_precision_noise_not_flagged(self):
        # on-disk value written un-rounded must not trip a false violation
        prov = {"entries": _entries(59)}
        metadata = {
            "stats": {
                "exports_documented": 59, "exports_public_api": 60, "exports_internal": 0,
                "exports_total": 60, "public_api_coverage": 59 / 60, "total_coverage": 59 / 60,
                "scripts_count": 0, "assets_count": 0,
            },
            "confidence_distribution": {"t1": 59, "t1_low": 0, "t2": 0, "t3": 0},
        }
        derived = mod.derive_stats(
            prov, {"exports_public_api": 60, "exports_internal": 0}, "library"
        )
        assert mod.check_stats(derived, metadata, prov)["ok"] is True


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _run(args, stdin="", cwd=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        input=stdin, capture_output=True, text=True, cwd=cwd,
    )


class TestCLI:
    def test_compute_mode_stdin(self, tmp_path):
        prov = _write_json(tmp_path / "provenance-map.json", {"entries": _entries(40, 5, 10, 4)})
        payload = json.dumps({"exports_public_api": 40, "exports_internal": 19})
        res = _run([str(prov)], stdin=payload)
        assert res.returncode == 0, res.stderr
        out = json.loads(res.stdout)
        assert out["confidence_distribution"] == {"t1": 40, "t1_low": 5, "t2": 10, "t3": 4}
        assert out["stats"]["exports_documented"] == 59
        assert out["coherence"]["ok"] is True

    def test_check_mode_exit_1_on_violation(self, tmp_path):
        prov = _write_json(tmp_path / "provenance-map.json", {"entries": _entries(40, 5, 10, 4)})
        metadata = _write_json(tmp_path / "metadata.json", {
            "stats": {
                "exports_documented": 147, "exports_public_api": 40, "exports_internal": 19,
                "exports_total": 59, "public_api_coverage": 1.0, "total_coverage": 1.0,
                "scripts_count": 0, "assets_count": 0,
            },
            "confidence_distribution": {"t1": 40, "t1_low": 5, "t2": 18, "t3": 84},
        })
        res = _run([str(prov), "--check", str(metadata)])
        assert res.returncode == 1, res.stdout
        out = json.loads(res.stdout)
        assert out["coherence"]["ok"] is False
        # emitted stats are the corrected values validate.md §7 writes back
        assert out["stats"]["exports_documented"] == 59
        assert out["confidence_distribution"] == {"t1": 40, "t1_low": 5, "t2": 10, "t3": 4}

    def test_missing_provenance_exit_2(self, tmp_path):
        res = _run([str(tmp_path / "nope.json")], stdin="{}")
        assert res.returncode == 2

    def test_malformed_stdin_exit_2(self, tmp_path):
        prov = _write_json(tmp_path / "provenance-map.json", {"entries": _entries(1)})
        res = _run([str(prov)], stdin="{not json")
        assert res.returncode == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
