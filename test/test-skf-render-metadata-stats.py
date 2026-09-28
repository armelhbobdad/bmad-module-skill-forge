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
  - labels follow the extraction tool: every T1 or T1-low entry's confidence,
    signature_source and ast_node_type must match its extraction_method, in
    compute and --check mode alike (issue #530)
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
# Label agreement: provenance labels follow the extraction tool (#530)
# --------------------------------------------------------------------------


_ABSENT = object()
KNOWN_METHODS = sorted(
    ["ast-grep", "source-read", "ast_bridge", "source_reading", "qmd_bridge", "compose-from-skill"]
)
VIOLATION_KEYS = {"field", "export_name", "expected", "actual", "note"}


def _row(name, method=_ABSENT, confidence=_ABSENT, sig=_ABSENT, node=_ABSENT):
    """One provenance entry; a field left _ABSENT is omitted from the dict."""
    row = {"export_name": name}
    for key, value in (("extraction_method", method), ("confidence", confidence),
                       ("signature_source", sig), ("ast_node_type", node)):
        if value is not _ABSENT:
            row[key] = value
    return row


def _judgment(prov):
    """A judgment payload the map agrees with, so only label violations can fire."""
    scripts = sum(1 for fe in prov.get("file_entries", []) if fe.get("file_type") == "script")
    return {"exports_public_api": len(prov["entries"]), "exports_internal": 0, "scripts_count": scripts}


def _metadata(prov):
    """An on-disk metadata.json that matches the map's derived stats exactly."""
    derived = mod.derive_stats(prov, _judgment(prov), "library")
    return {"stats": dict(derived["stats"]),
            "confidence_distribution": dict(derived["confidence_distribution"])}


def _coherence(prov, mode):
    """Run the coherence checks of `mode` (compute or check) over a matching payload."""
    derived = mod.derive_stats(prov, _judgment(prov), "library")
    if mode == "compute":
        return mod.coherence_compute(derived, prov)
    return mod.check_stats(derived, _metadata(prov), prov)


def _labels(coherence):
    return [v for v in coherence["violations"] if v["field"].startswith("provenance.entries[")]


def _by_field(violations):
    return {v["field"]: v for v in violations}


# The I/O matrix rows of the #530 spec: (entries, file_entries, label violations, exit code).
LABEL_ROWS = {
    "read-by-eye-labeled-t1": (
        [_row("search", "source-read", "T1", "T1", "function_definition")], [], 3, 1),
    "ast-grep-without-t1-or-kind": (
        [_row("add", "ast-grep", "T1-low", "T1-low", None)], [], 2, 1),
    "unknown-method": (
        [_row("cognify", "direct-read", "T1", "T1", "function_definition")], [], 1, 1),
    "missing-method": (
        [_row("memify", confidence="T1-low", sig="T1-low")], [], 1, 1),
    "source_reading-labeled-t1": (
        [_row("prune", "source_reading", "T1", "T1", "function_definition")], [], 2, 1),
    "ast_bridge-labeled-t1-low": (
        [_row("visualize", "ast_bridge", "T1-low", "T1-low", None)], [], 1, 1),
    "source-read-lowercase-t1-signature": (
        [_row("config", "source-read", "T1-low", "t1", None)], [], 1, 1),
    "ast-grep-kind-copied-from-expected": (
        [_row("search", "ast-grep", "T1", "T1", "non-null")], [], 1, 1),
    "exempt-rows": (
        [_row("a", "ast_bridge", "T1", "T1", None),
         _row("b", "source_reading", "T1-low", "T2", "function_definition"),
         _row("c", "qmd_bridge", "T1", "T1", None),
         _row("d", "compose-from-skill", "T1-low", "T1"),
         _row("e", "direct-read", "T2", "T2", "function_definition"),
         _row("f", "source-read", "T3", "T3", "function_definition"),
         _row("g", "direct-read", sig="T1", node="function_definition")],
        [{"file_name": "scripts/run.sh", "file_type": "script", "confidence": "T1",
          "extraction_method": "file-copy"}],
        0, 0),
    "clean-library-map": (
        [_row("search", "ast-grep", "T1", "T1", "function_definition"),
         _row("Client", "ast-grep", "T1", "T1", "class_definition"),
         _row("config", "source-read", "T1-low", "T1-low", None),
         _row("helpers", "source-read", "T1-low", "T1-low")],
        [], 0, 0),
}
MODES = ("compute", "check")


class TestLabelAgreement:
    @pytest.mark.parametrize("mode", MODES)
    def test_read_by_eye_labeled_t1(self, mode):
        prov = {"entries": [_row("search", "source-read", "T1", "T1", "function_definition")]}
        coherence = _coherence(prov, mode)
        assert coherence["ok"] is False
        labels = _labels(coherence)
        assert labels == coherence["violations"]  # nothing else drifts
        assert all(set(v) == VIOLATION_KEYS for v in labels)
        by = _by_field(labels)
        assert set(by) == {"provenance.entries[0].confidence",
                           "provenance.entries[0].signature_source",
                           "provenance.entries[0].ast_node_type"}
        assert by["provenance.entries[0].confidence"]["expected"] == "T1-low"
        assert by["provenance.entries[0].confidence"]["actual"] == "T1"
        assert by["provenance.entries[0].confidence"]["note"] == (
            "extraction_method source-read pairs with confidence T1-low")
        assert by["provenance.entries[0].signature_source"]["expected"] == "T1-low"
        assert by["provenance.entries[0].signature_source"]["actual"] == "T1"
        assert "any tier but T1 passes" in by["provenance.entries[0].signature_source"]["note"]
        assert by["provenance.entries[0].ast_node_type"]["expected"] is None
        assert by["provenance.entries[0].ast_node_type"]["actual"] == "function_definition"
        assert all(v["export_name"] == "search" for v in labels)

    @pytest.mark.parametrize("mode", MODES)
    @pytest.mark.parametrize("node", [None, _ABSENT, "", "  "], ids=["null", "absent", "empty", "blank"])
    def test_ast_grep_without_t1_or_kind(self, mode, node):
        prov = {"entries": [_row("add", "ast-grep", "T1-low", "T1-low", node)]}
        coherence = _coherence(prov, mode)
        assert coherence["ok"] is False
        labels = _labels(coherence)
        assert labels == coherence["violations"]
        by = _by_field(labels)
        assert set(by) == {"provenance.entries[0].confidence", "provenance.entries[0].ast_node_type"}
        assert by["provenance.entries[0].confidence"]["expected"] == "T1"
        assert by["provenance.entries[0].confidence"]["actual"] == "T1-low"
        assert by["provenance.entries[0].ast_node_type"]["expected"] == "non-null"
        assert "node kind of the rule that matched" in by["provenance.entries[0].ast_node_type"]["note"]

    @pytest.mark.parametrize("mode", MODES)
    @pytest.mark.parametrize("node", ["non-null", " Non-Null "], ids=["literal", "padded-mixed-case"])
    def test_ast_grep_kind_copied_from_expected_is_still_missing(self, mode, node):
        # "non-null" is the violation's expected value; copying it records no kind
        prov = {"entries": [_row("search", "ast-grep", "T1", "T1", node)]}
        coherence = _coherence(prov, mode)
        assert coherence["ok"] is False
        labels = _labels(coherence)
        assert labels == coherence["violations"]
        assert [v["field"] for v in labels] == ["provenance.entries[0].ast_node_type"]
        assert labels[0]["expected"] == "non-null"
        assert labels[0]["actual"] == node

    @pytest.mark.parametrize("mode", MODES)
    def test_source_reading_labeled_t1(self, mode):
        # stack value: pairs like source-read, but carries no ast_node_type rule
        prov = {"entries": [_row("prune", "source_reading", "T1", "T1", "function_definition")]}
        coherence = _coherence(prov, mode)
        assert coherence["ok"] is False
        labels = _labels(coherence)
        assert labels == coherence["violations"]
        by = _by_field(labels)
        assert set(by) == {"provenance.entries[0].confidence", "provenance.entries[0].signature_source"}
        assert by["provenance.entries[0].confidence"]["expected"] == "T1-low"
        assert by["provenance.entries[0].confidence"]["note"] == (
            "extraction_method source_reading pairs with confidence T1-low")
        assert by["provenance.entries[0].signature_source"]["expected"] == "T1-low"
        assert by["provenance.entries[0].signature_source"]["actual"] == "T1"

    @pytest.mark.parametrize("mode", MODES)
    def test_ast_bridge_labeled_t1_low(self, mode):
        # stack value: pairs like ast-grep, but needs no node kind
        prov = {"entries": [_row("visualize", "ast_bridge", "T1-low", "T1-low", None)]}
        coherence = _coherence(prov, mode)
        assert coherence["ok"] is False
        labels = _labels(coherence)
        assert labels == coherence["violations"]
        assert len(labels) == 1
        assert labels[0]["field"] == "provenance.entries[0].confidence"
        assert labels[0]["expected"] == "T1"
        assert labels[0]["actual"] == "T1-low"

    @pytest.mark.parametrize("mode", MODES)
    def test_source_read_lowercase_t1_signature(self, mode):
        prov = {"entries": [_row("config", "source-read", "T1-low", "t1", None)]}
        coherence = _coherence(prov, mode)
        assert coherence["ok"] is False
        labels = _labels(coherence)
        assert labels == coherence["violations"]
        assert len(labels) == 1
        assert labels[0]["field"] == "provenance.entries[0].signature_source"
        assert labels[0]["expected"] == "T1-low"
        assert labels[0]["actual"] == "t1"

    @pytest.mark.parametrize("mode", MODES)
    @pytest.mark.parametrize("confidence", ["T1", "T1-low", "t1-LOW"])
    @pytest.mark.parametrize("method", ["direct-read", "Source-Read", _ABSENT, None],
                             ids=["direct-read", "wrong-case", "absent", "null"])
    def test_unknown_or_missing_method(self, mode, confidence, method):
        # The other labels disagree with every known method too, yet only the
        # method is reported: the pairing cannot be judged without it.
        prov = {"entries": [_row("cognify", method, confidence, "T1", "function_definition")]}
        coherence = _coherence(prov, mode)
        assert coherence["ok"] is False
        labels = _labels(coherence)
        assert labels == coherence["violations"]
        assert len(labels) == 1
        v = labels[0]
        assert v["field"] == "provenance.entries[0].extraction_method"
        assert v["expected"] == KNOWN_METHODS
        assert v["actual"] == (None if method is _ABSENT else method)
        assert v["export_name"] == "cognify"
        assert set(v) == VIOLATION_KEYS

    @pytest.mark.parametrize("mode", MODES)
    @pytest.mark.parametrize("row", [
        _row("a", "ast_bridge", "T1", "T1", None),
        _row("b", "source_reading", "T1-low", "T2", "function_definition"),
        _row("b2", "source_reading", "T1-low", "T3"),
        _row("c", "qmd_bridge", "T1", "T1", None),
        _row("c2", "qmd_bridge", "T1-low", "T1", "function_definition"),
        _row("d", "compose-from-skill", "T1-low", "T1"),
        _row("d2", "compose-from-skill", "T1", "T1", None),
        _row("e", "direct-read", "T2", "T2", "function_definition"),
        _row("f", "source-read", "T3", "T3", "function_definition"),
        _row("g", "direct-read", sig="T1", node="function_definition"),
        _row("h", "ast-grep", "t1", "T1", "function_declaration"),
        _row("i", "source-read", " t1-low ", "t2", None),
    ], ids=["ast_bridge-t1", "source_reading-t1-low", "source_reading-no-kind", "qmd_bridge",
            "qmd_bridge-t1-low", "compose-from-skill", "compose-from-skill-t1", "t2-row", "t3-row",
            "no-confidence", "ast-grep-lower-case", "source-read-padded"])
    def test_exempt_rows(self, mode, row):
        prov = {"entries": [row]}
        coherence = _coherence(prov, mode)
        assert _labels(coherence) == []
        assert coherence["ok"] is True

    @pytest.mark.parametrize("mode", MODES)
    def test_file_entries_are_not_checked(self, mode):
        prov = {
            "entries": [_row("search", "ast-grep", "T1", "T1", "function_definition")],
            "file_entries": [
                {"file_name": "scripts/run.sh", "file_type": "script", "confidence": "T1",
                 "extraction_method": "file-copy"},
                {"file_name": "docs/authoritative/llms.txt", "file_type": "doc",
                 "confidence": "T1-low", "extraction_method": "promoted-authoritative",
                 "ast_node_type": "document"},
            ],
        }
        coherence = _coherence(prov, mode)
        assert _labels(coherence) == []
        assert coherence["ok"] is True

    @pytest.mark.parametrize("mode", MODES)
    def test_clean_library_map(self, mode):
        entries = LABEL_ROWS["clean-library-map"][0]
        prov = {"entries": entries}
        coherence = _coherence(prov, mode)
        assert coherence == {"ok": True, "violations": []}
        derived = mod.derive_stats(prov, _judgment(prov), "library")
        assert derived["confidence_distribution"] == {"t1": 2, "t1_low": 2, "t2": 0, "t3": 0}

    def test_keyed_by_index_when_names_repeat(self):
        # reference-app and stack maps cite one export several times
        prov = {"entries": [
            _row("search", "ast-grep", "T1", "T1", "function_definition"),
            _row("search", "source-read", "T1", "T1-low", None),
            _row("search", "source-read", "T1-low", "T1-low", None),
        ]}
        labels = mod.check_label_agreement(prov)
        assert [v["field"] for v in labels] == ["provenance.entries[1].confidence"]
        assert labels[0]["export_name"] == "search"

    def test_labels_do_not_move_the_distribution(self):
        # The check reports; it never rebins. A mislabeled signature_source
        # still lands in its own bin until the caller relabels and re-runs.
        prov = {"entries": [_row("search", "source-read", "T1", "T1", "function_definition")]}
        derived = mod.derive_stats(prov, _judgment(prov), "library")
        assert derived["confidence_distribution"]["t1"] == 1
        relabeled = {"entries": [_row("search", "source-read", "T1-low", "T1-low", None)]}
        assert mod.check_label_agreement(relabeled) == []
        again = mod.derive_stats(relabeled, _judgment(relabeled), "library")
        assert again["confidence_distribution"] == {"t1": 0, "t1_low": 1, "t2": 0, "t3": 0}

    def test_non_list_entries_and_non_dict_rows(self):
        assert mod.check_label_agreement({}) == []
        assert mod.check_label_agreement({"entries": "nope"}) == []
        assert mod.check_label_agreement({"entries": ["x", 3, None]}) == []


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

    @pytest.mark.parametrize("mode", MODES)
    @pytest.mark.parametrize("row", sorted(LABEL_ROWS))
    def test_label_rows_exit_codes(self, tmp_path, mode, row):
        entries, file_entries, label_count, exit_code = LABEL_ROWS[row]
        prov_doc = {"entries": entries}
        if file_entries:
            prov_doc["file_entries"] = file_entries
        prov = _write_json(tmp_path / "provenance-map.json", prov_doc)
        if mode == "compute":
            res = _run([str(prov)], stdin=json.dumps(_judgment(prov_doc)))
        else:
            meta = _write_json(tmp_path / "metadata.json", _metadata(prov_doc))
            res = _run([str(prov), "--check", str(meta)])
        assert res.returncode == exit_code, res.stdout + res.stderr
        out = json.loads(res.stdout)
        assert out["coherence"]["ok"] is (exit_code == 0)
        assert len(_labels(out["coherence"])) == label_count
        assert len(out["coherence"]["violations"]) == label_count  # nothing else drifts

    def test_check_mode_reports_labels_beside_drift(self, tmp_path):
        # oms-cognee 1.0.0 in miniature: every entry read by eye but labeled
        # T1, and a distribution that folded doc items on top of the entries.
        entries = [_row(f"fn_{i}", "source-read", "T1", "T1", "function_definition") for i in range(3)]
        prov = _write_json(tmp_path / "provenance-map.json", {"entries": entries})
        meta_doc = _metadata({"entries": entries})
        meta_doc["confidence_distribution"]["t3"] = 5
        meta = _write_json(tmp_path / "metadata.json", meta_doc)
        res = _run([str(prov), "--check", str(meta)])
        assert res.returncode == 1, res.stdout + res.stderr
        out = json.loads(res.stdout)
        assert "confidence_distribution.t3" in [v["field"] for v in out["coherence"]["violations"]]
        labels = _labels(out["coherence"])
        assert len(labels) == 9  # 3 entries x confidence, signature_source, ast_node_type
        assert {v["field"].rsplit(".", 1)[1] for v in labels} == {
            "confidence", "signature_source", "ast_node_type"}
        # the stats come from the map as it stands; the caller relabels, then re-runs
        assert out["confidence_distribution"]["t1"] == 3

    def test_missing_provenance_exit_2(self, tmp_path):
        res = _run([str(tmp_path / "nope.json")], stdin="{}")
        assert res.returncode == 2

    def test_malformed_stdin_exit_2(self, tmp_path):
        prov = _write_json(tmp_path / "provenance-map.json", {"entries": _entries(1)})
        res = _run([str(prov)], stdin="{not json")
        assert res.returncode == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
