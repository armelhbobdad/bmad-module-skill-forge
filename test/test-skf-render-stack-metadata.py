#!/usr/bin/env python3
"""Tests for src/shared/scripts/skf-render-stack-metadata.py.

The helper create-stack-skill runs for a stack's labels, tiers, metadata.json
and provenance map (parallel-extract section 3a, detect-integrations
section 3, generate-output sections 6 and 7):
  - `relabel` runs skf-render-metadata-stats.py's label check on the export
    records and sets each mislabeled field to the value the check expects
    (an unknown method to source_reading, a known one to its canonical
    spelling, an ast-grep record with no kind to ast_bridge, a missing
    signature_source to its method's label) until the check passes, so a
    second run changes nothing; it rewrites the file only when a label
    changed, prints each relabeled export and the label counts, exits 1
    when a violation no rule fixes is left, and exits 2 with nothing
    written when the stats helper is not beside it or the records are
    malformed
  - `provenance` writes the map in the bundle's mode, its entries from the
    records and its integrations from the extraction bundle's pairs (a, b,
    type and tier renamed to the schema's fields, and the detection_method
    the mode's table gives the pair's qualifier, whatever detection_method
    the pair still holds; a missing qualifier, an unknown one or one of the
    other mode exits 2), in the schema's place,
    atomically, and writes nothing on a bad input, a bad bundle or a target
    it cannot create; in code mode each pair's co-import files come from the
    pair-intersect result (--pairs), matched on the two libraries in either
    order, and a pair it lacks is refused; in compose mode each entry takes
    its constituent's tier from the bundle (an entry of no constituent is
    refused), the co-import files are [] and the constituents come from the
    bundle's entries and step 4's inventory, each hash copied and each
    skill_path relative to the project root; a flag of the other mode, or a
    missing one, is refused
  - `library-tiers` makes a code-mode library T1 only when it has export
    records and an ast-grep rule matched every one, T1-low otherwise (a
    library with no record included), in the order --libraries gives; a
    record naming a library --libraries does not list exits 2
  - combine_pair_tier gives a pair the weaker of its two tiers, the same
    rule in code mode and compose mode, for the six cases of the old compose
    matrix and every pair with a T3 member
  - dominant_tier picks the largest bin, a tie going to the weaker tier,
    T1-low with no positive bin; a copy of skf-enumerate-stack-skills.py's
  - `metadata` counts each library once, so confidence_distribution sums to
    library_count, and takes the lowest source_authority (internal lowest, a
    library that records none counting as community); its library_order
    ranks by distinct partners, then file_count (code mode) or tier
    (compose mode), then name, and its hubs are the libraries of 3 partners
    or more in that order, each with its partners by name
  - `pair-tiers` and `metadata` read a file or stdin, stdin as UTF-8 even
    where the console's code page is cp1252; a malformed input exits 2 with
    one line on stderr and no JSON; with --bundle (a file, never stdin) they
    read the extraction bundle and print what --input prints for the same
    data, a code-mode pair-tiers taking its pairs from --pairs, and a flag
    used with the wrong source or mode exits 2
  - `references` prints the Library Reference Index rows in library_order,
    the first five export names then `+N more`, a `|` escaped, and with
    --out writes each library file (every record in records order, a
    Migration & Deprecation section only for a library with a temporal
    item) and each pair file (the pair helper's count, matched in either
    order; in compose mode the evidence, reference and VS lines and the
    label's suffixes), with a marker line per part the step writes; the
    files have the template's headings and header labels and, filled in,
    pass the validator's structure pass, a scoped name included; a mode
    mismatch, a record of no library, a compose call with --records or
    --pairs, a code --out without --pairs, a name that escapes --out and
    two files on one path exit 2 with nothing written, and a failed write
    removes what the call wrote
  - `evidence-report` lists every section, bins the map as
    skf-render-metadata-stats.py --shape stack does, reads the sink by the
    emitter's rules (none for no file, an unreadable line named), writes
    "not computed" with the reason when the stats helper is missing or the
    map cannot be read, counts the temporal items without listing them,
    and exits 2 with nothing written on a bad input or a target it cannot
    write

test-skf-stack-step-rules.py runs the calls the step files make.
"""

from __future__ import annotations

import ast
import importlib.util
import itertools
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "src" / "shared" / "scripts"
SCRIPT = SCRIPTS / "skf-render-stack-metadata.py"
ENUMERATE = SCRIPTS / "skf-enumerate-stack-skills.py"
STATS = SCRIPTS / "skf-render-metadata-stats.py"
EMITTER = SCRIPTS / "skf-emit-result-envelope.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load(SCRIPT, "skf_render_stack_metadata")
enumerate_mod = _load(ENUMERATE, "skf_enumerate_stack_skills_for_stack_metadata")
stats_mod = _load(STATS, "skf_render_metadata_stats_for_stack_metadata")

MODES = ("code", "compose")

# The six cases of the compose matrix the one rule replaced, and the tier each
# gives: the weaker of the two. A T2 member lowers the pair like any other.
SIX_CASES = [
    ("T1", "T1", "T1"),
    ("T1", "T1-low", "T1-low"),
    ("T1-low", "T1-low", "T1-low"),
    ("T1", "T2", "T2"),
    ("T1-low", "T2", "T2"),
    ("T2", "T2", "T2"),
]


def run(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True, text=True,
    )


def stack(libraries, integrations=(), mode="compose") -> dict:
    return {
        "mode": mode,
        "libraries": [
            dict({"name": name, "confidence": tier}, **({"source_authority": auth} if auth else {}))
            for name, tier, auth in libraries
        ],
        "integrations": [{"a": a, "b": b} for a, b in integrations],
    }


# --------------------------------------------------------------------------
# library_tier and library-tiers
# --------------------------------------------------------------------------


def records(*pairs) -> dict:
    """An export records file: one {source_library, extraction_method} record per pair."""
    return {"entries": [{"export_name": f"e{i}", "source_library": library, "extraction_method": method}
                        for i, (library, method) in enumerate(pairs)]}


@pytest.mark.parametrize("methods, tier", [
    (["ast_bridge"], "T1"),
    (["ast_bridge", "ast_bridge"], "T1"),
    (["ast_bridge", "source_reading"], "T1-low"),
    (["source_reading"], "T1-low"),
    ([], "T1-low"),
    (["ast-grep"], "T1-low"),
], ids=["one-ast", "all-ast", "one-read-by-eye", "all-read-by-eye", "no-record", "create-skill-method"])
def test_a_library_is_t1_only_when_ast_grep_matched_every_export(methods, tier):
    assert mod.library_tier(methods) == tier


def test_library_tiers_follow_the_libraries_given():
    out = mod.library_tiers(records(("libb", "source_reading"), ("liba", "ast_bridge"), ("libb", "ast_bridge")),
                            ["liba", "libb", "libc"])
    assert out == [
        {"name": "liba", "tier": "T1", "export_count": 1, "ast_bridge_count": 1},
        {"name": "libb", "tier": "T1-low", "export_count": 2, "ast_bridge_count": 1},
        {"name": "libc", "tier": "T1-low", "export_count": 0, "ast_bridge_count": 0},
    ]


def test_a_method_compares_case_insensitively():
    out = mod.library_tiers(records(("liba", " AST_Bridge "), ("liba", None)), ["liba"])
    assert out[0]["tier"] == "T1-low" and out[0]["ast_bridge_count"] == 1  # a record with no method is no match
    assert mod.library_tiers(records(("liba", "AST_BRIDGE")), ["liba"])[0]["tier"] == "T1"


@pytest.mark.parametrize("data, names, needle", [
    ([], ["liba"], "`entries` array"),
    ({"entries": {}}, ["liba"], "`entries` array"),
    ({"entries": ["liba"]}, ["liba"], "entries[0] must be an object"),
    (records(("libz", "ast_bridge")), ["liba"], "entries[0].source_library 'libz' is not one of --libraries"),
    ({"entries": [{"extraction_method": "ast_bridge"}]}, ["liba"], "entries[0].source_library None"),
], ids=["not-an-object", "entries-not-a-list", "record-not-an-object", "unknown-library", "no-library"])
def test_a_malformed_records_file_is_refused(data, names, needle):
    with pytest.raises(ValueError) as caught:
        mod.library_tiers(data, names)
    assert needle in str(caught.value)


@pytest.mark.parametrize("value, needle", [
    ("", "at least one library"),
    (" , ", "at least one library"),
    ("liba,libb,liba", "listed twice"),
], ids=["empty", "only-commas", "duplicate"])
def test_a_malformed_library_list_is_refused(value, needle):
    with pytest.raises(ValueError) as caught:
        mod.parse_library_names(value)
    assert needle in str(caught.value)


def test_library_names_are_split_on_commas_and_trimmed():
    assert mod.parse_library_names(" react, react-dom ,@scope/pkg ") == ["react", "react-dom", "@scope/pkg"]


def test_library_tiers_reads_a_file(tmp_path):
    path = tmp_path / "export-records.json"
    path.write_bytes(json.dumps(records(("café", "ast_bridge")), ensure_ascii=False).encode("utf-8"))
    result = run("library-tiers", "--records", str(path), "--libraries", "café,zod")
    assert result.returncode == 0, result.stderr
    assert [(e["name"], e["tier"]) for e in json.loads(result.stdout)["libraries"]] == [("café", "T1"), ("zod", "T1-low")]
    assert result.stdout.isascii(), "non-ASCII names are escaped for a Windows console"


def test_library_tiers_reads_stdin():
    result = run("library-tiers", "--records", "-", "--libraries", "liba",
                 stdin=json.dumps(records(("liba", "source_reading"))))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "libraries": [{"name": "liba", "tier": "T1-low", "export_count": 1, "ast_bridge_count": 0}]}


# --------------------------------------------------------------------------
# relabel
# --------------------------------------------------------------------------


def record(name, method, confidence=None, signature=None, library="liba", **extra) -> dict:
    """One export record as parallel-extract section 3a writes it; None leaves a label out."""
    out = {"export_name": name, "source_library": library, "extraction_method": method, "params": []}
    if confidence is not None:
        out["confidence"] = confidence
    if signature is not None:
        out["signature_source"] = signature
    out.update(extra)
    return out


# One record per rule: the label each one ends with.
RELABEL_CASES = [
    (record("Client", "source_reading", "T1", "T1"),
     {"extraction_method": "source_reading", "confidence": "T1-low", "signature_source": "T1-low"}),
    (record("magic", "regex", "T1", "T1"),
     {"extraction_method": "source_reading", "confidence": "T1-low", "signature_source": "T1-low"}),
    (record("nomethod", None, "T1", "T1"),
     {"extraction_method": "source_reading", "confidence": "T1-low", "signature_source": "T1-low"}),
    (record("spelled", " AST_Bridge ", "T1", "T1"),
     {"extraction_method": "ast_bridge", "confidence": "T1", "signature_source": "T1"}),
    (record("nokind", "ast-grep", "T1", "T1"),
     {"extraction_method": "ast_bridge", "confidence": "T1", "signature_source": "T1"}),
    (record("kind", "source-read", "T1-low", "T1-low", ast_node_type="function_definition"),
     {"extraction_method": "source-read", "confidence": "T1-low", "signature_source": "T1-low"}),
    (record("unsigned", "ast_bridge", "T1"),
     {"extraction_method": "ast_bridge", "confidence": "T1", "signature_source": "T1"}),
    (record("unsigned-eye", "source_reading", "T1-low", "Deep"),
     {"extraction_method": "source_reading", "confidence": "T1-low", "signature_source": "T1-low"}),
    (record("matched-low", "ast_bridge", "T1-low", "T1-low"),
     {"extraction_method": "ast_bridge", "confidence": "T1", "signature_source": "T1-low"}),
]


@pytest.mark.parametrize("before, after", RELABEL_CASES, ids=[case[0]["export_name"] for case in RELABEL_CASES])
def test_relabel_sets_the_label_the_method_implies(before, after):
    entries = [dict(before)]
    relabeled, _distribution, coherence = mod.relabel(stats_mod, entries)
    assert coherence == {"ok": True, "violations": []}
    assert {key: entries[0].get(key) for key in after} == after
    assert "ast_node_type" not in entries[0] or before["extraction_method"] == "ast-grep"
    assert relabeled and relabeled[0]["entry_index"] == 0 and relabeled[0]["export_name"] == before["export_name"]
    # The labels it set pass the check it ran: a second run changes nothing.
    assert mod.relabel(stats_mod, entries)[0] == []


def test_relabel_keeps_a_record_the_check_passes():
    entries = [record("connect", "ast_bridge", "T1", "T1"), record("Client", "source_reading", "T1-low", "T1-low")]
    before = json.loads(json.dumps(entries))
    relabeled, distribution, coherence = mod.relabel(stats_mod, entries)
    assert (relabeled, entries, coherence["ok"]) == ([], before, True)
    assert distribution == {"t1": 1, "t1_low": 1, "t2": 0, "t3": 0}


def test_relabel_lists_each_export_once_with_its_changes():
    entries = [record("connect", "ast_bridge", "T1", "T1"), record("magic", "regex", "T1", "T1", library="libb")]
    relabeled, distribution, _coherence = mod.relabel(stats_mod, entries)
    assert relabeled == [{
        "entry_index": 1, "export_name": "magic", "source_library": "libb",
        "changes": [{"field": "extraction_method", "from": "regex", "to": "source_reading"},
                    {"field": "confidence", "from": "T1", "to": "T1-low"},
                    {"field": "signature_source", "from": "T1", "to": "T1-low"}],
    }]
    # The label counts bin every record once, by its signature_source.
    assert distribution == {"t1": 1, "t1_low": 1, "t2": 0, "t3": 0}
    assert sum(distribution.values()) == len(entries)


def test_the_relabeled_records_pass_the_stats_helper():
    """The check relabel runs is the stats helper's own, so its CLI agrees."""
    entries = [dict(before) for before, _ in RELABEL_CASES]
    mod.relabel(stats_mod, entries)
    assert stats_mod.check_label_agreement({"entries": entries}) == []
    derived = stats_mod.derive_stats({"entries": entries}, {}, "stack")
    assert stats_mod.coherence_compute(derived, {"entries": entries})["ok"] is True


class _StubStats:
    """A label check that reports a violation no relabel rule fixes."""

    _SIG_MAP = stats_mod._SIG_MAP
    _KNOWN_METHODS = stats_mod._KNOWN_METHODS

    @staticmethod
    def derive_stats(prov, judgment, shape):
        return {"confidence_distribution": {"t1": 0, "t1_low": 0, "t2": 0, "t3": 0}}

    @staticmethod
    def coherence_compute(derived, prov):
        return {"ok": False, "violations": [{"field": "stats.scripts_count", "expected": 1, "actual": 0}]}


def test_a_violation_no_rule_fixes_is_left_and_exits_1(tmp_path, monkeypatch, capsys):
    relabeled, _distribution, coherence = mod.relabel(_StubStats, [record("connect", "ast_bridge", "T1", "T1")])
    assert relabeled == [] and coherence["ok"] is False
    path = tmp_path / "export-records.json"
    path.write_bytes(json.dumps({"entries": [record("connect", "ast_bridge", "T1", "T1")]}).encode("utf-8"))
    monkeypatch.setattr(mod, "_load_stats_rules", lambda: _StubStats)
    assert mod.main(["relabel", "--records", str(path)]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["coherence"]["violations"] == [{"field": "stats.scripts_count", "expected": 1, "actual": 0}]


def test_relabel_rewrites_the_file_only_when_a_label_changed(tmp_path):
    path = tmp_path / "run" / "export-records.json"
    path.parent.mkdir()
    clean = json.dumps({"entries": [record("café", "ast_bridge", "T1", "T1")]}, ensure_ascii=False)
    path.write_bytes(clean.encode("utf-8"))
    result = run("relabel", "--records", str(path))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["relabeled"] == []
    assert path.read_bytes() == clean.encode("utf-8"), "a file with nothing to relabel was rewritten"
    path.write_bytes(json.dumps({"entries": [record("café", "source_reading", "T1", "T1")]},
                                ensure_ascii=False).encode("utf-8"))
    result = run("relabel", "--records", str(path))
    assert result.returncode == 0, result.stderr
    assert result.stdout.isascii(), "non-ASCII names are escaped for a Windows console"
    out = json.loads(result.stdout)
    assert [r["export_name"] for r in out["relabeled"]] == ["café"]
    stored = json.loads(path.read_bytes().decode("utf-8"))["entries"][0]
    assert (stored["export_name"], stored["confidence"], stored["signature_source"]) == ("café", "T1-low", "T1-low")
    assert stored["params"] == [], "a field the check does not read is kept"
    assert sorted(p.name for p in path.parent.iterdir()) == ["export-records.json"], "a temp file was left"


def test_relabel_needs_the_stats_helper_beside_it(tmp_path):
    """Installed without skf-render-metadata-stats.py, relabel runs no check and writes nothing."""
    alone = tmp_path / "scripts" / SCRIPT.name
    alone.parent.mkdir()
    alone.write_bytes(SCRIPT.read_bytes())
    path = tmp_path / "export-records.json"
    data = json.dumps({"entries": [record("Client", "source_reading", "T1", "T1")]}).encode("utf-8")
    path.write_bytes(data)
    result = subprocess.run([sys.executable, str(alone), "relabel", "--records", str(path)],
                            capture_output=True, text=True)
    assert (result.returncode, result.stdout) == (2, "")
    assert "skf-render-metadata-stats.py not found" in result.stderr
    assert path.read_bytes() == data


@pytest.mark.parametrize("args, content, needle", [
    (("relabel", "--records", "-"), None, "not stdin"),
    (("relabel", "--records", "export-records.json"), '{"entries": ["connect"]}', "entries[0] must be an object"),
    (("relabel", "--records", "export-records.json"), '{"rows": []}', "`entries` array"),
    (("relabel", "--records", "export-records.json"), "{not json", "not valid JSON"),
], ids=["stdin", "record-not-an-object", "no-entries", "bad-json"])
def test_relabel_refuses_a_bad_records_file(args, content, needle, tmp_path):
    if content is not None:
        (tmp_path / "export-records.json").write_bytes(content.encode("utf-8"))
    result = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, cwd=tmp_path)
    assert (result.returncode, result.stdout) == (2, "")
    assert needle in result.stderr and len(result.stderr.strip().splitlines()) == 1
    if content is not None:
        assert (tmp_path / "export-records.json").read_bytes() == content.encode("utf-8")


# --------------------------------------------------------------------------
# provenance
# --------------------------------------------------------------------------

MAP_FIELDS = {"provenance_version": "2.0", "skill_name": "demo-stack", "skill_type": "stack",
              "source_repo": ["https://github.com/acme/app"], "source_commit": {"app": "abc123"},
              "generated_at": "2026-10-02T08:00:00Z", "integrations": []}
# The extraction bundle's pairs, as detect-integrations section 4 writes them: no co-import file and no
# detection_method, which the helper derives from the qualifier.
BUNDLE_PAIR = {"a": "liba", "b": "libb", "type": "adapter", "tier": "t1-LOW", "qualifier": "grep-co-import",
               "key_files": ["src/app.py:9"], "description": "liba feeds libb"}
CO_IMPORT_FILES = [{"path": "src/app.py", "line_a": 1, "line_b": 2}, {"path": "src/db.py", "line_a": 4, "line_b": 3}]
# The skf-pair-intersect.py result detect-integrations section 1 saves.
PAIR_INTERSECT = {"pairs": [{"a": "liba", "b": "libb", "intersection_count": 2, "files": CO_IMPORT_FILES}],
                  "truncated": False, "total_pairs": 1}
MAP_PAIR = {"libraries": ["liba", "libb"], "pattern_type": "adapter", "detection_method": "co-import grep",
            "co_import_files": CO_IMPORT_FILES, "confidence": "T1-low"}


def _bundle(tmp_path, *pairs, mode="code", **fields):
    path = tmp_path / "extraction-bundle.json"
    bundle = {"mode": mode, "per_library_extractions": [], "integrations": list(pairs), **fields}
    path.write_bytes(json.dumps(bundle).encode("utf-8"))
    return path


def _pairs(tmp_path, data=None):
    path = tmp_path / "pair-intersect.json"
    path.write_bytes(json.dumps(PAIR_INTERSECT if data is None else data).encode("utf-8"))
    return path


def test_provenance_writes_the_records_as_the_map_entries(tmp_path):
    records = tmp_path / "export-records.json"
    entries = [record("connect", "ast_bridge", "T1", "T1", source_file="libs/liba/api.py", source_line=6)]
    records.write_bytes(json.dumps({"entries": entries}).encode("utf-8"))
    target = tmp_path / "forge" / "demo-stack" / "1.0.0" / "provenance-map.json"
    result = run("provenance", "--records", str(records), "--bundle", str(_bundle(tmp_path, BUNDLE_PAIR)),
                 "--pairs", str(_pairs(tmp_path)), "--input", "-", "--target", str(target),
                 stdin=json.dumps(dict(MAP_FIELDS, entries=[{"export_name": "typed by hand"}])))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"target": str(target), "entry_count": 1, "integration_count": 1}
    written = json.loads(target.read_bytes().decode("utf-8"))
    assert written["entries"] == entries, "the records replace the entries the input held"
    assert written["integrations"] == [MAP_PAIR], "the bundle's pairs replace the integrations the input held"
    assert list(written) == [*MAP_FIELDS, "entries"], "the entries keep the place the input gave them"
    assert sorted(p.name for p in target.parent.iterdir()) == ["provenance-map.json"]


def test_the_map_integrations_are_the_bundle_pairs():
    """w3 determinism-5: no step types a second list of pairs; the bundle's is projected."""
    pairs = mod.pair_files({"pairs": [*PAIR_INTERSECT["pairs"], {"a": "libb", "b": "libc", "files": []}]})
    assert mod.bundle_integrations(
        {"mode": "code", "integrations": [BUNDLE_PAIR, dict(BUNDLE_PAIR, a="libc", tier="T2")]}, pairs) == [
        MAP_PAIR, dict(MAP_PAIR, libraries=["libc", "libb"], confidence="T2", co_import_files=[])]
    assert mod.bundle_integrations({"mode": "code", "integrations": []}, pairs) == []
    # Compose mode: no pair-intersect result, so no co-import file.
    compose = dict(BUNDLE_PAIR, qualifier="architecture-co-mention")
    assert mod.bundle_integrations({"mode": "compose", "integrations": [compose]}) == [
        dict(MAP_PAIR, detection_method="architecture_co_mention", co_import_files=[])]


@pytest.mark.parametrize("mode, qualifier, method", [
    ("code", "grep-co-import", "co-import grep"),
    ("compose", "architecture-co-mention", "architecture_co_mention"),
    ("compose", "constituent-documented-contract", "constituent_documented_contract"),
    ("compose", "inferred-shared-domain", "inferred_from_shared_domain"),
    ("compose", "Inferred-Shared-Domain", "inferred_from_shared_domain"),
    ("code", " GREP-co-import ", "co-import grep"),
], ids=["code", "architecture", "documented-contract", "shared-domain", "shared-domain-case", "code-case"])
def test_the_detection_method_comes_from_the_qualifier(mode, qualifier, method):
    """#1154 determinism-3: the helper derives each pair's detection_method from the mode's table; a
    detection_method still in a bundle entry is ignored, so no hand-typed method reaches the map."""
    pairs = mod.pair_files(PAIR_INTERSECT) if mode == "code" else None
    for pair in (dict(BUNDLE_PAIR, qualifier=qualifier), dict(BUNDLE_PAIR, qualifier=qualifier, detection_method="x")):
        [out] = mod.bundle_integrations({"mode": mode, "integrations": [pair]}, pairs)
        assert out["detection_method"] == method
    assert mod.detection_method(mode, qualifier, "pair") == method


def test_the_detection_table_holds_the_schema_values():
    assert mod.DETECTION_METHODS == {
        "code": {"grep-co-import": "co-import grep"},
        "compose": {"architecture-co-mention": "architecture_co_mention",
                    "constituent-documented-contract": "constituent_documented_contract",
                    "inferred-shared-domain": "inferred_from_shared_domain"}}


@pytest.mark.parametrize("mode, qualifier", [
    ("code", "architecture-co-mention"),
    ("compose", "grep-co-import"),
    ("code", "typed-by-hand"),
    ("compose", "typed-by-hand"),
    ("code", None),
    ("compose", None),
    ("compose", ""),
], ids=["code-takes-compose", "compose-takes-code", "code-unknown", "compose-unknown", "code-none",
        "compose-none", "compose-empty"])
def test_provenance_refuses_a_qualifier_outside_its_modes_table(mode, qualifier, tmp_path):
    """#1154 determinism-3: a run can no longer write a detection method outside the schema."""
    pair = {key: value for key, value in BUNDLE_PAIR.items() if key != "qualifier"}
    if qualifier is not None:
        pair["qualifier"] = qualifier
    if mode == "code":
        records = tmp_path / "export-records.json"
        records.write_bytes(b'{"entries": []}')
        target = tmp_path / "provenance-map.json"
        result = run("provenance", "--records", str(records), "--bundle", str(_bundle(tmp_path, pair)),
                     "--pairs", str(_pairs(tmp_path)), "--input", "-", "--target", str(target),
                     stdin=json.dumps(MAP_FIELDS))
    else:
        result, target = _compose_run(tmp_path, pair=dict(pair, a="react", b="express"))
    assert (result.returncode, result.stdout) == (2, "")
    assert len(result.stderr.strip().splitlines()) == 1, result.stderr
    assert "integrations[0].qualifier" in result.stderr, result.stderr
    for allowed in mod.DETECTION_METHODS[mode]:
        assert allowed in result.stderr, allowed
    assert not target.exists()


def test_the_co_import_files_are_the_pair_helpers():
    """Step 5b determinism-2: the files come from the saved pair-intersect result, never the bundle."""
    stale = dict(BUNDLE_PAIR, co_import_files=[{"path": "typed/by/hand.py", "line_a": 9, "line_b": 9}])
    [pair] = mod.bundle_integrations({"mode": "code", "integrations": [stale]}, mod.pair_files(PAIR_INTERSECT))
    assert pair["co_import_files"] == CO_IMPORT_FILES


def test_a_pair_named_the_other_way_round_swaps_its_lines():
    [pair] = mod.bundle_integrations({"mode": "code", "integrations": [dict(BUNDLE_PAIR, a="libb", b="liba")]},
                                     mod.pair_files(PAIR_INTERSECT))
    assert pair["libraries"] == ["libb", "liba"]
    assert pair["co_import_files"] == [{"path": "src/app.py", "line_a": 2, "line_b": 1},
                                       {"path": "src/db.py", "line_a": 3, "line_b": 4}]


@pytest.mark.parametrize("data, needle", [
    pytest.param([], "`pairs` array", id="not-an-object"),
    pytest.param({"pairs": None}, "`pairs` array", id="no-pairs"),
    pytest.param({"pairs": ["liba+libb"]}, "pairs[0] must be an object", id="pair-not-object"),
    pytest.param({"pairs": [{"a": "liba", "files": []}]}, "pairs[0].b", id="no-b"),
    pytest.param({"pairs": [{"a": "liba", "b": "libb", "files": ["src/app.py"]}]}, "pairs[0].files",
                 id="libraries-shape-files"),
])
def test_a_malformed_pair_intersect_result_is_refused(data, needle, tmp_path):
    records = tmp_path / "export-records.json"
    records.write_bytes(b'{"entries": []}')
    target = tmp_path / "provenance-map.json"
    result = run("provenance", "--records", str(records), "--bundle", str(_bundle(tmp_path, BUNDLE_PAIR)),
                 "--pairs", str(_pairs(tmp_path, data)), "--input", "-", "--target", str(target),
                 stdin=json.dumps(MAP_FIELDS))
    assert (result.returncode, result.stdout) == (2, "")
    assert needle in result.stderr and len(result.stderr.strip().splitlines()) == 1
    assert not target.exists()


def test_a_code_mode_pair_with_no_pair_intersect_entry_is_refused(tmp_path):
    records = tmp_path / "export-records.json"
    records.write_bytes(b'{"entries": []}')
    target = tmp_path / "provenance-map.json"
    result = run("provenance", "--records", str(records),
                 "--bundle", str(_bundle(tmp_path, BUNDLE_PAIR, dict(BUNDLE_PAIR, b="libc"))),
                 "--pairs", str(_pairs(tmp_path)), "--input", "-", "--target", str(target),
                 stdin=json.dumps(MAP_FIELDS))
    assert (result.returncode, result.stdout) == (2, "")
    assert "integrations[1] (liba + libc) has no entry in the pair-intersect result" in result.stderr
    assert not target.exists()


def test_the_entries_go_before_the_integrations():
    assert list(mod.provenance_map(MAP_FIELDS, [])) == [*[*MAP_FIELDS][:6], "entries", "integrations"]
    assert list(mod.provenance_map({"skill_name": "s"}, [])) == ["skill_name", "entries"]
    assert list(mod.provenance_map({"entries": None, "skill_name": "s"}, [1])) == ["entries", "skill_name"]
    # The piped fields hold no integrations: the bundle's go after the entries.
    fields = {key: value for key, value in MAP_FIELDS.items() if key != "integrations"}
    assert list(mod.provenance_map(fields, [], [MAP_PAIR])) == [*fields, "entries", "integrations"]


@pytest.mark.parametrize("bundle, needle", [
    pytest.param({"integrations": None}, "`integrations` array", id="no-integrations"),
    pytest.param({"integrations": ["liba+libb"]}, "integrations[0] must be an object", id="pair-not-object"),
    pytest.param({"integrations": [dict(BUNDLE_PAIR, type="")]}, "integrations[0].type", id="no-type"),
    pytest.param({"integrations": [dict(BUNDLE_PAIR, tier="T9")]}, "integrations[0].tier", id="bad-tier"),
    pytest.param({"mode": None, "integrations": []}, "the bundle's mode", id="no-mode"),
    pytest.param({"mode": "both", "integrations": []}, "the bundle's mode", id="bad-mode"),
])
def test_provenance_writes_nothing_on_a_bad_bundle(bundle, needle, tmp_path):
    records = tmp_path / "export-records.json"
    records.write_bytes(b'{"entries": []}')
    path = tmp_path / "extraction-bundle.json"
    path.write_bytes(json.dumps({"mode": "code", **bundle}).encode("utf-8"))
    target = tmp_path / "provenance-map.json"
    result = run("provenance", "--records", str(records), "--bundle", str(path), "--pairs", str(_pairs(tmp_path)),
                 "--input", "-", "--target", str(target), stdin=json.dumps(MAP_FIELDS))
    assert (result.returncode, result.stdout) == (2, "")
    assert needle in result.stderr and len(result.stderr.strip().splitlines()) == 1
    assert not target.exists()


@pytest.mark.parametrize("args_input, stdin, needle", [
    ("-", "[]", "must be a JSON object"),
    ("-", "{not json", "not valid JSON"),
    ("missing.json", None, "cannot read the input"),
], ids=["not-an-object", "bad-json", "missing-input"])
def test_provenance_writes_nothing_on_a_bad_input(args_input, stdin, needle, tmp_path):
    records = tmp_path / "export-records.json"
    records.write_bytes(b'{"entries": []}')
    target = tmp_path / "provenance-map.json"
    result = subprocess.run([sys.executable, str(SCRIPT), "provenance", "--records", str(records),
                             "--bundle", str(_bundle(tmp_path)), "--pairs", str(_pairs(tmp_path)),
                             "--input", args_input, "--target", str(target)],
                            input=stdin, capture_output=True, text=True, cwd=tmp_path)
    assert (result.returncode, result.stdout) == (2, "")
    assert needle in result.stderr
    assert not target.exists()


def test_provenance_reports_a_target_it_cannot_write(tmp_path):
    records = tmp_path / "export-records.json"
    records.write_bytes(b'{"entries": []}')
    blocker = tmp_path / "forge"
    blocker.write_bytes(b"a file where the version folder should be")
    target = blocker / "provenance-map.json"
    result = run("provenance", "--records", str(records), "--bundle", str(_bundle(tmp_path)),
                 "--pairs", str(_pairs(tmp_path)), "--input", "-", "--target", str(target), stdin=json.dumps(MAP_FIELDS))
    assert (result.returncode, result.stdout) == (2, "")
    assert "cannot write" in result.stderr and len(result.stderr.strip().splitlines()) == 1


def test_provenance_reads_the_records_and_the_bundle_from_files(tmp_path):
    result = run("provenance", "--records", "-", "--bundle", "b.json", "--input", "-",
                 "--target", "provenance-map.json", stdin="{}")
    assert result.returncode == 2 and "--records from a file, not stdin" in result.stderr
    records = tmp_path / "export-records.json"
    records.write_bytes(b'{"entries": []}')
    result = run("provenance", "--records", str(records), "--bundle", "-", "--input", "-",
                 "--target", str(tmp_path / "provenance-map.json"), stdin="{}")
    assert result.returncode == 2 and "--bundle from a file, not stdin" in result.stderr
    result = run("provenance", "--records", str(records), "--bundle", str(_bundle(tmp_path)), "--pairs", "-",
                 "--input", "-", "--target", str(tmp_path / "provenance-map.json"), stdin="{}")
    assert result.returncode == 2 and "--pairs from a file, not stdin" in result.stderr


# The compose-mode map: step 4's inventory and the bundle's constituent entries.
COMPOSE_FIELDS = {"provenance_version": "2.0", "skill_name": "demo-stack", "skill_type": "stack",
                  "source_repo": None, "source_commit": None, "source_ref": None,
                  "generated_at": "2026-10-03T08:00:00Z"}
CONSTITUENTS = (("react", "18.2.0", "sha256:" + "a" * 64), ("express", "4.19.0", "sha256:" + "b" * 64))
COMPOSE_PAIR = dict(BUNDLE_PAIR, a="react", b="express", tier="T1", qualifier="architecture-co-mention")


def _compose_run(tmp_path, *, skills_dir="skills", constituents=CONSTITUENTS, inventory=None, fields=COMPOSE_FIELDS,
                 extra=(), outside=False, entries=({"export_name": "render", "source_library": "react"},),
                 pair=COMPOSE_PAIR):
    """Lay out a project with a skills folder (beside the project when `outside`) and run the
    compose-mode provenance call."""
    project = tmp_path / "project"
    skills_root = (tmp_path if outside else project) / skills_dir
    for name, _version, _hash in constituents:
        (skills_root / name).mkdir(parents=True, exist_ok=True)
    records = tmp_path / "compose-entries.json"
    records.write_bytes(json.dumps({"entries": list(entries)}).encode())
    bundle = _bundle(tmp_path, pair, mode="compose", per_library_extractions=[
        {"library": name, "skill_dir": name, "version": version, "confidence": "T1"}
        for name, version, _hash in constituents])
    inventory_file = tmp_path / "stack-inventory.json"
    if inventory is None:
        inventory = {"skills": [{"name": name, "path": f"{name}/active/{name}", "metadata_hash": digest}
                                for name, _version, digest in constituents]}
    inventory_file.write_bytes(json.dumps(inventory).encode("utf-8"))
    target = tmp_path / "forge" / "provenance-map.json"
    result = run("provenance", "--records", str(records), "--bundle", str(bundle), "--inventory", str(inventory_file),
                 "--skills-root", str(skills_root), "--project-root", str(project), *extra,
                 "--input", "-", "--target", str(target), stdin=json.dumps(fields))
    return result, target


def test_compose_mode_writes_the_constituents_from_the_inventory(tmp_path):
    """Step 5b determinism-3: the helper, not the model, builds integrations[] and constituents[], each
    metadata_hash copied from step 4's inventory and each skill_path relative to the project root."""
    result, target = _compose_run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"target": str(target), "entry_count": 1, "integration_count": 1,
                                         "constituent_count": 2}
    written = json.loads(target.read_bytes().decode("utf-8"))
    assert list(written) == [*COMPOSE_FIELDS, "entries", "integrations", "constituents"]
    # The model writes the cited fields; the helper adds the constituent's tier and the method.
    assert written["entries"] == [{"export_name": "render", "source_library": "react", "confidence": "T1",
                                   "extraction_method": "compose-from-skill", "signature_source": "T1"}]
    assert written["integrations"] == [{"libraries": ["react", "express"], "pattern_type": "adapter",
                                        "detection_method": "architecture_co_mention", "co_import_files": [],
                                        "confidence": "T1"}]
    assert written["constituents"] == [
        {"skill_name": name, "skill_path": f"skills/{name}/", "version": version,
         "composed_at": "2026-10-03T08:00:00Z", "metadata_hash": digest}
        for name, version, digest in CONSTITUENTS]


def test_each_compose_entry_takes_its_constituents_tier():
    """Step 5b review: the helper reads the tiers from the bundle, so no step copies a constituent's
    tier into each entry by hand, and a label the model wrote is replaced, in its place."""
    bundle = {"per_library_extractions": [{"library": "react", "confidence": "t1-low"},
                                          {"library": "zod", "confidence": "T3"}]}
    entries = [{"export_name": "render", "source_library": "react", "confidence": "T1",
                "extraction_method": "ast_bridge", "signature_source": "T1", "source_line": 4},
               {"export_name": "parse", "source_library": "zod"}]
    assert mod.compose_entries(bundle, entries) == [
        {"export_name": "render", "source_library": "react", "confidence": "T1-low",
         "extraction_method": "compose-from-skill", "signature_source": "T1-low", "source_line": 4},
        {"export_name": "parse", "source_library": "zod", "confidence": "T3",
         "extraction_method": "compose-from-skill", "signature_source": "T3"}]
    assert entries[1] == {"export_name": "parse", "source_library": "zod"}, "the records are not changed in place"


@pytest.mark.parametrize("entries, bundle, needle", [
    pytest.param([{"export_name": "x", "source_library": "vue"}], [{"library": "react", "confidence": "T1"}],
                 "entries[0].source_library 'vue' is not a library", id="unknown-library"),
    pytest.param([{"export_name": "x"}], [{"library": "react", "confidence": "T1"}],
                 "entries[0].source_library None", id="no-library"),
    pytest.param([{"export_name": "x", "source_library": "react"}], [{"library": "react", "confidence": "Deep"}],
                 "per_library_extractions[0].confidence", id="constituent-without-a-tier"),
])
def test_a_compose_entry_without_a_constituent_tier_is_refused(entries, bundle, needle):
    with pytest.raises(mod.InputError, match=re.escape(needle)):
        mod.compose_entries({"per_library_extractions": bundle}, entries)


def test_a_skill_path_follows_a_non_default_skills_folder(tmp_path):
    result, target = _compose_run(tmp_path, skills_dir="agent-skills/generated")
    assert result.returncode == 0, result.stderr
    paths = [c["skill_path"] for c in json.loads(target.read_bytes().decode("utf-8"))["constituents"]]
    assert paths == ["agent-skills/generated/react/", "agent-skills/generated/express/"]


def test_a_skills_folder_outside_the_project_root_stays_relative(tmp_path):
    result, target = _compose_run(tmp_path, skills_dir="shared-skills", outside=True)
    assert result.returncode == 0, result.stderr
    paths = [c["skill_path"] for c in json.loads(target.read_bytes().decode("utf-8"))["constituents"]]
    assert paths == ["../shared-skills/react/", "../shared-skills/express/"]


def test_a_compose_bundle_ignores_its_pairs_co_import_files(tmp_path):
    stale = [{"path": "typed/by/hand.py", "line_a": 1, "line_b": 2}]
    [pair] = mod.bundle_integrations({"mode": "compose", "integrations": [dict(COMPOSE_PAIR, co_import_files=stale)]})
    assert pair["co_import_files"] == []


def test_the_constituents_keep_the_place_the_input_gives_them():
    fields = dict(COMPOSE_FIELDS, constituents=None, integrations=None)
    assert list(mod.provenance_map(fields, [], [], [])) == [*COMPOSE_FIELDS, "constituents", "entries",
                                                           "integrations"]


@pytest.mark.parametrize("change, needle", [
    pytest.param({"fields": dict(COMPOSE_FIELDS, generated_at=None)}, "generated_at", id="no-generated-at"),
    pytest.param({"inventory": {"skills": [{"name": "react", "metadata_hash": "sha256:" + "a" * 64}]}},
                 "holds no metadata_hash for 'express'", id="skill-not-in-inventory"),
    pytest.param({"inventory": {"skills": [{"name": "react", "metadata_hash": None},
                                           {"name": "express", "metadata_hash": "sha256:" + "b" * 64}]}},
                 "holds no metadata_hash for 'react'", id="null-hash"),
    pytest.param({"inventory": []}, "`skills` array", id="inventory-not-an-object"),
    pytest.param({"constituents": (("react", 18, "sha256:a"),)}, "version must be a string or null",
                 id="version-not-a-string"),
    pytest.param({"extra": ("--pairs", "pair-intersect.json")}, "--pairs is for a code-mode bundle",
                 id="pairs-in-compose-mode"),
    pytest.param({"entries": ({"export_name": "render", "source_library": "vue"},)},
                 "entries[0].source_library 'vue' is not a library", id="entry-of-no-constituent"),
])
def test_compose_mode_writes_nothing_on_a_bad_input(change, needle, tmp_path):
    result, target = _compose_run(tmp_path, **change)
    assert (result.returncode, result.stdout) == (2, "")
    assert needle in result.stderr and len(result.stderr.strip().splitlines()) == 1, result.stderr
    assert not target.exists()


def test_a_constituent_folder_missing_under_the_skills_root_is_refused(tmp_path):
    """A wrongly bound --skills-root fails before a skill_path the audit cannot resolve is written."""
    bundle = {"per_library_extractions": [{"library": "react", "skill_dir": "react", "version": "18.2.0"}]}
    with pytest.raises(mod.InputError, match="no skill folder 'react' under --skills-root"):
        mod.compose_constituents(bundle, {"react": "sha256:a"}, str(tmp_path / "skills"), str(tmp_path),
                                 "2026-10-03T08:00:00Z")


@pytest.mark.parametrize("skill_dir", ["..", "nested/react", "nested\\react"], ids=["parent", "slash", "backslash"])
def test_a_skill_dir_that_is_not_a_folder_name_is_refused(skill_dir, tmp_path):
    bundle = {"per_library_extractions": [{"library": "react", "skill_dir": skill_dir, "version": "1.0.0"}]}
    with pytest.raises(mod.InputError, match="must be a folder name"):
        mod.compose_constituents(bundle, {skill_dir: "sha256:a"}, str(tmp_path), str(tmp_path), "2026-10-03")


@pytest.mark.parametrize("missing", ["--inventory", "--skills-root", "--project-root"])
def test_a_compose_bundle_needs_its_three_flags(missing, tmp_path):
    records = tmp_path / "compose-entries.json"
    records.write_bytes(b'{"entries": []}')
    flags = {"--inventory": "stack-inventory.json", "--skills-root": "skills", "--project-root": "."}
    del flags[missing]
    target = tmp_path / "provenance-map.json"
    result = run("provenance", "--records", str(records), "--bundle", str(_bundle(tmp_path, mode="compose")),
                 *[item for pair in flags.items() for item in pair], "--input", "-", "--target", str(target),
                 stdin=json.dumps(COMPOSE_FIELDS))
    assert (result.returncode, result.stdout) == (2, "")
    assert f"a compose-mode bundle needs {missing}" in result.stderr
    assert not target.exists()


def test_a_code_bundle_needs_pairs_and_refuses_the_compose_flags(tmp_path):
    records = tmp_path / "export-records.json"
    records.write_bytes(b'{"entries": []}')
    target = tmp_path / "provenance-map.json"
    base = ("provenance", "--records", str(records), "--bundle", str(_bundle(tmp_path)))
    tail = ("--input", "-", "--target", str(target))
    result = run(*base, *tail, stdin=json.dumps(MAP_FIELDS))
    assert result.returncode == 2 and "a code-mode bundle needs --pairs" in result.stderr
    result = run(*base, "--pairs", str(_pairs(tmp_path)), "--inventory", "inv.json", *tail,
                 stdin=json.dumps(MAP_FIELDS))
    assert result.returncode == 2 and "--inventory is for a compose-mode bundle" in result.stderr
    assert not target.exists()


# --------------------------------------------------------------------------
# combine_pair_tier
# --------------------------------------------------------------------------


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("a, b, tier", SIX_CASES, ids=[f"{a}+{b}" for a, b, _ in SIX_CASES])
def test_a_pair_takes_the_weaker_tier_in_both_modes(a, b, tier, mode):
    assert mod.combine_pair_tier(a, b, mode) == tier
    assert mod.combine_pair_tier(b, a, mode) == tier


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("other", ["T1", "T1-low", "T2", "T3"])
def test_a_t3_member_makes_the_pair_t3(other, mode):
    assert mod.combine_pair_tier(other, "T3", mode) == "T3"
    assert mod.combine_pair_tier("T3", other, mode) == "T3"


def test_both_modes_take_one_rule():
    for a, b in itertools.product(mod.TIERS, repeat=2):
        assert mod.combine_pair_tier(a, b, "code") == mod.combine_pair_tier(a, b, "compose")


def test_the_pair_tier_never_outranks_either_member():
    for a, b in itertools.product(mod.TIERS, repeat=2):
        tier = mod.combine_pair_tier(a, b, "code")
        assert tier in (a, b)
        assert mod.TIERS.index(tier) >= max(mod.TIERS.index(a), mod.TIERS.index(b))


def test_tokens_compare_case_insensitively():
    assert mod.combine_pair_tier("t1", "T1-LOW", "Compose") == "T1-low"


@pytest.mark.parametrize("a, b, mode", [
    ("T4", "T1", "code"),
    ("T1", None, "code"),
    ("Deep", "T1", "compose"),
    ("T1", "T1", "stack"),
    ("T1", "T1", None),
])
def test_an_unknown_tier_or_mode_is_an_input_error(a, b, mode):
    with pytest.raises(ValueError):
        mod.combine_pair_tier(a, b, mode)


# --------------------------------------------------------------------------
# dominant_tier
# --------------------------------------------------------------------------


@pytest.mark.parametrize("distribution, tier", [
    ({"t1": 3, "t1_low": 1, "t2": 0, "t3": 0}, "T1"),
    ({"t1": 1, "t1_low": 3, "t2": 0, "t3": 0}, "T1-low"),
    ({"t1": 0, "t1_low": 0, "t2": 2, "t3": 1}, "T2"),
    ({"t1": 0, "t1_low": 0, "t2": 0, "t3": 5}, "T3"),
])
def test_the_largest_bin_is_the_dominant_tier(distribution, tier):
    assert mod.dominant_tier(distribution) == tier


@pytest.mark.parametrize("distribution, tier", [
    ({"t1": 2, "t1_low": 2, "t2": 0, "t3": 0}, "T1-low"),
    ({"t1": 0, "t1_low": 2, "t2": 2, "t3": 0}, "T2"),
    ({"t1": 1, "t1_low": 0, "t2": 0, "t3": 1}, "T3"),
    ({"t1": 1, "t1_low": 1, "t2": 1, "t3": 0}, "T2"),
])
def test_a_tie_goes_to_the_weaker_tier(distribution, tier):
    assert mod.dominant_tier(distribution) == tier


@pytest.mark.parametrize("distribution", [None, {}, [], "T1", {"t1": 0, "t1_low": 0, "t2": 0, "t3": 0}],
                         ids=["none", "empty", "list", "string", "all-zero"])
def test_no_library_reads_t1_low(distribution):
    assert mod.dominant_tier(distribution) == "T1-low"


def _top_level_node(path: Path, name: str) -> str:
    """ast.dump of the top-level def or assignment named `name` (comments ignored)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.dump(node)
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.dump(node)
    raise AssertionError(f"{name} not found at the top level of {path.name}")


@pytest.mark.parametrize("name", ["_bin_count", "dominant_tier", "_DISTRIBUTION_BINS", "_NO_EVIDENCE_TIER"])
def test_the_dominant_tier_is_a_copy_of_the_enumerate_helper(name):
    """A constituent's evidence_tier and a stack's confidence_tier follow one rule."""
    assert _top_level_node(SCRIPT, name) == _top_level_node(ENUMERATE, name), (
        f"{name} in skf-render-stack-metadata.py differs from skf-enumerate-stack-skills.py; keep the copies identical")
    text = SCRIPT.read_text(encoding="utf-8")
    assert "Keep identical to _bin_count and dominant_tier in skf-enumerate-stack-skills.py" in text
    assert "test/test-skf-render-stack-metadata.py pins the copies" in text


def test_the_enumerate_helper_keeps_the_same_authorities():
    """A constituent's source_authority outside these enumerates as null (community): the two lists stay one."""
    assert enumerate_mod._AUTHORITIES == mod.AUTHORITIES


def test_the_copies_agree_on_every_small_distribution():
    odd = [True, "9", -1, None, float("nan"), float("inf"), 2.5]
    for values in itertools.product([0, 1, 2, 3], repeat=4):
        distribution = dict(zip(("t1", "t1_low", "t2", "t3"), values))
        assert mod.dominant_tier(distribution) == enumerate_mod.dominant_tier(distribution), distribution
    for value in odd:
        distribution = {"t1": value, "t1_low": 1}
        assert mod.dominant_tier(distribution) == enumerate_mod.dominant_tier(distribution), distribution


# --------------------------------------------------------------------------
# metadata
# --------------------------------------------------------------------------


def _metadata(data: dict) -> dict:
    return mod.stack_metadata(*mod.parse_stack(data))


@pytest.mark.parametrize("tiers", [
    ["T1"],
    ["T1", "T1-low", "T2"],
    ["T3", "T3", "T1-low", "T1", "T2", "T2"],
    [],
], ids=["one", "three", "six", "none"])
def test_the_distribution_counts_each_library_once(tiers):
    """#528: the bins sum to library_count, whatever the stack holds."""
    out = _metadata(stack([(f"lib{i}", tier, None) for i, tier in enumerate(tiers)]))
    assert out["library_count"] == len(tiers)
    assert sum(out["confidence_distribution"].values()) == out["library_count"]
    assert list(out["confidence_distribution"]) == ["t1", "t1_low", "t2", "t3"]
    assert out["confidence_tier"] == mod.dominant_tier(out["confidence_distribution"])


def test_the_projection_keeps_the_order_given():
    data = stack(
        [("react", "T1", "community"), ("express", "T1-low", "official"), ("zod", "T2", None)],
        [("react", "express"), ("zod", "react")],
    )
    out = _metadata(data)
    assert out == {
        "mode": "compose",
        "library_count": 3,
        "integration_count": 2,
        "libraries": ["react", "express", "zod"],
        "integration_pairs": [["react", "express"], ["zod", "react"]],
        "confidence_distribution": {"t1": 1, "t1_low": 1, "t2": 1, "t3": 0},
        "confidence_tier": "T2",
        "source_authority": "community",
        "integrations": [
            {"a": "react", "b": "express", "tier": "T1-low"},
            {"a": "zod", "b": "react", "tier": "T2"},
        ],
        "hubs": [],
        "library_order": ["react", "express", "zod"],
    }


def _code_stack(libraries, pairs) -> dict:
    """A code-mode --input stack: (name, tier, file_count) libraries, a None count left out."""
    return {"mode": "code",
            "libraries": [dict({"name": name, "confidence": tier}, **({} if count is None else {"file_count": count}))
                          for name, tier, count in libraries],
            "integrations": [{"a": a, "b": b} for a, b in pairs]}


# The matrix's code-mode stack: react has three partners, express and zod two each.
HUB_LIBRARIES = [("react", "T1", 12), ("express", "T1-low", 9), ("zod", "T1", 3), ("axios", "T1-low", 5),
                 ("prisma", "T1", 1)]
HUB_PAIRS = [("react", "express"), ("react", "zod"), ("react", "axios"), ("express", "zod")]


def test_the_hubs_and_the_library_order_come_from_the_pairs():
    """#1154 determinism-2: no step counts partners or sorts libraries by hand."""
    out = _metadata(_code_stack(HUB_LIBRARIES, HUB_PAIRS))
    # Degree first (react 3; express and zod 2, express importing more files; axios 1; prisma 0).
    assert out["library_order"] == ["react", "express", "zod", "axios", "prisma"]
    assert out["hubs"] == [{"library": "react", "partners": ["axios", "express", "zod"]}]


def test_every_library_of_three_partners_is_a_hub_in_library_order():
    pairs = [*HUB_PAIRS, ("express", "axios"), ("zod", "prisma")]
    out = _metadata(_code_stack(HUB_LIBRARIES, pairs))
    # react, express and zod have three partners: the file count orders them.
    assert out["library_order"] == ["react", "express", "zod", "axios", "prisma"]
    assert out["hubs"] == [{"library": "react", "partners": ["axios", "express", "zod"]},
                           {"library": "express", "partners": ["axios", "react", "zod"]},
                           {"library": "zod", "partners": ["express", "prisma", "react"]}]


def test_a_compose_degree_tie_goes_to_the_stronger_tier_then_the_name():
    data = stack([("b", "T1-low", None), ("a", "T2", None), ("c", "T1-low", None)])
    assert _metadata(data)["library_order"] == ["b", "c", "a"]
    # A file_count never orders a compose-mode stack.
    data["libraries"][1]["file_count"] = 99
    assert _metadata(data)["library_order"] == ["b", "c", "a"]


def test_a_code_library_without_a_file_count_counts_0():
    out = _metadata(_code_stack([("b", "T1", None), ("a", "T3", 0), ("c", "T1", 2)], []))
    # Tier never orders a code-mode stack; a missing count ties with 0 and the name breaks it.
    assert out["library_order"] == ["c", "a", "b"]


def test_the_name_breaks_a_tie_case_folded_then_as_written():
    out = _metadata(stack([("b", "T1", None), ("B", "T1", None), ("a", "T1", None), ("A", "T1", None)],
                          [("b", "B"), ("b", "a"), ("b", "A"), ("B", "a"), ("B", "A"), ("a", "A")]))
    assert out["library_order"] == ["A", "a", "B", "b"]
    assert [hub["library"] for hub in out["hubs"]] == ["A", "a", "B", "b"]
    assert out["hubs"][0]["partners"] == ["a", "B", "b"]


@pytest.mark.parametrize("count", [-1, 1.5, "3", True, None, [3]],
                         ids=["negative", "fraction", "string", "bool", "null", "list"])
def test_a_file_count_that_is_not_a_whole_number_is_refused(count):
    data = {"mode": "code", "libraries": [{"name": "react", "confidence": "T1", "file_count": count}]}
    with pytest.raises(mod.InputError, match=re.escape("libraries[0].file_count must be a whole number")):
        mod.parse_stack(data)


@pytest.mark.parametrize("authorities, expected", [
    (["community", "internal"], "internal"),
    (["internal", "community"], "internal"),
    (["official", "community"], "community"),
    (["official", "official"], "official"),
    (["official", "internal", "community"], "internal"),
    (["official", None], "community"),
    (["internal", None], "internal"),
    ([None, None], "community"),
], ids=["community-internal", "internal-community", "official-community", "official", "all-three",
        "official-unrecorded", "internal-unrecorded", "none-recorded"])
def test_source_authority_is_the_lowest(authorities, expected):
    """internal ranks lowest: a community and an internal library give internal.

    A library that records no authority counts as community, so a constituent
    without one never lifts a stack to official.
    """
    libraries = [(f"lib{i}", "T1", authority) for i, authority in enumerate(authorities)]
    assert _metadata(stack(libraries))["source_authority"] == expected


def test_a_stack_with_no_library_records_community():
    assert mod.lowest_authority([]) == "community"


def test_a_code_mode_stack_records_community():
    out = _metadata(stack([("react", "T1", None), ("express", "T1-low", None)], mode="code"))
    assert out["source_authority"] == "community"
    assert out["mode"] == "code"


def test_the_metadata_pairs_have_the_pair_tiers():
    data = stack([("a", "T1", None), ("b", "T3", None), ("c", "T1", None)], [("a", "b"), ("a", "c")], mode="code")
    mode, libraries, pairs = mod.parse_stack(data)
    assert _metadata(data)["integrations"] == mod.pair_tiers(mode, libraries, pairs) == [
        {"a": "a", "b": "b", "tier": "T3"},
        {"a": "a", "b": "c", "tier": "T1"},
    ]


def test_tokens_are_printed_in_their_canonical_spelling():
    out = _metadata({"mode": "CODE", "libraries": [
        {"name": "a", "confidence": "t1-low", "source_authority": "Internal"},
        {"name": "b", "confidence": " T1 "},
    ]})
    assert (out["mode"], out["confidence_tier"], out["source_authority"]) == ("code", "T1-low", "internal")


@pytest.mark.parametrize("data, needle", [
    ([], "must be a JSON object"),
    ({"libraries": []}, "mode"),
    ({"mode": "compose"}, "`libraries`"),
    ({"mode": "compose", "libraries": ["react"]}, "libraries[0] must be an object"),
    ({"mode": "compose", "libraries": [{"name": "", "confidence": "T1"}]}, "libraries[0].name"),
    ({"mode": "compose", "libraries": [{"name": "a", "confidence": "Deep"}]}, "libraries[0].confidence"),
    ({"mode": "compose", "libraries": [{"name": "a", "confidence": "T1", "source_authority": "vendor"}]},
     "libraries[0].source_authority"),
    ({"mode": "compose", "libraries": [{"name": "a", "confidence": "T1"}, {"name": "a", "confidence": "T2"}]},
     "listed twice"),
    ({"mode": "compose", "libraries": [{"name": "a", "confidence": "T1"}], "integrations": {"a": "a"}},
     "`integrations`"),
    ({"mode": "compose", "libraries": [{"name": "a", "confidence": "T1"}], "integrations": [["a", "b"]]},
     "integrations[0] must be an object"),
    ({"mode": "compose", "libraries": [{"name": "a", "confidence": "T1"}], "integrations": [{"a": "a", "b": "z"}]},
     "integrations[0].b 'z' is not one of the libraries"),
    ({"mode": "compose", "libraries": [{"name": "a", "confidence": "T1"}], "integrations": [{"a": ["a"], "b": "a"}]},
     "integrations[0].a ['a'] is not one of the libraries"),
    ({"mode": "compose", "libraries": [{"name": "a", "confidence": "T1"}], "integrations": [{"a": "a", "b": "a"}]},
     "with itself"),
    ({"mode": "compose", "libraries": [{"name": "a", "confidence": "T1"}, {"name": "b", "confidence": "T1"}],
      "integrations": [{"a": "a", "b": "b"}, {"a": "b", "b": "a"}]}, "listed twice"),
], ids=["not-an-object", "no-mode", "no-libraries", "library-not-an-object", "empty-name", "forge-tier",
        "unknown-authority", "duplicate-library", "integrations-not-a-list", "pair-not-an-object",
        "unknown-pair-member", "unhashable-pair-member", "self-pair", "duplicate-pair"])
def test_a_malformed_input_is_refused(data, needle):
    with pytest.raises(ValueError) as caught:
        mod.parse_stack(data)
    assert needle in str(caught.value)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_pair_tiers_reads_stdin():
    data = stack([("react", "T1", None), ("express", "T2", None)], [("react", "express")])
    result = run("pair-tiers", "--input", "-", stdin=json.dumps(data))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "mode": "compose", "integrations": [{"a": "react", "b": "express", "tier": "T2"}],
    }


def _stack_bundle(tmp_path, mode: str, *, pairs_in_bundle: bool = True) -> tuple[Path, dict, list[dict]]:
    """An extraction bundle and the --input stack that holds the same data, with the pairs."""
    libraries = [("react", "T1", "official", 12), ("express", "T1-low", "internal", 9), ("zod", "T1", None, 3),
                 ("axios", "T2", "community", 5), ("prisma", "T3", None, None)]
    pairs = [{"a": a, "b": b} for a, b in HUB_PAIRS]
    entries = []
    for name, tier, authority, count in libraries:
        entry = {"library": name, "status": "success", "version": "1.0.0", "confidence": tier,
                 "usage_patterns": ["src/app.ts:1"], "warnings": []}
        if authority is not None:
            entry["source_authority"] = authority
        if count is not None:
            entry["file_count"] = count
        entries.append(entry)
    # The bundle's pairs hold what step 5 writes beside a and b, which the stack form leaves out.
    integrations = [dict(pair, type="adapter", tier="T1", qualifier="q") for pair in pairs] if pairs_in_bundle else []
    path = tmp_path / "extraction-bundle.json"
    path.write_bytes(json.dumps({"mode": mode, "scope": [name for name, *_ in libraries],
                                 "per_library_extractions": entries, "failed": [], "integrations": integrations,
                                 "cross_cutting": []}).encode("utf-8"))
    stack_input = {"mode": mode, "libraries": [
        dict({"name": name, "confidence": tier}, **({"source_authority": authority} if authority else {}),
             **({"file_count": count} if count is not None else {}))
        for name, tier, authority, count in libraries], "integrations": pairs}
    return path, stack_input, pairs


@pytest.mark.parametrize("mode", MODES)
def test_the_bundle_form_prints_what_the_input_form_prints(mode, tmp_path):
    """#1154 determinism-8: the stages pass {bundleFile} instead of re-typing it into a payload."""
    bundle, stack_input, pairs = _stack_bundle(tmp_path, mode)
    from_input = run("metadata", "--input", "-", stdin=json.dumps(stack_input))
    from_bundle = run("metadata", "--bundle", str(bundle))
    assert from_input.returncode == from_bundle.returncode == 0, from_input.stderr + from_bundle.stderr
    assert from_bundle.stdout == from_input.stdout
    out = json.loads(from_bundle.stdout)
    assert out["source_authority"] == "internal" and out["hubs"] == [
        {"library": "react", "partners": ["axios", "express", "zod"]}]
    expected = run("pair-tiers", "--input", "-", stdin=json.dumps(stack_input))
    assert expected.returncode == 0, expected.stderr
    if mode == "code":
        # Step 5 tiers a code-mode pair before it writes it: the pairs come from --pairs.
        bundle, _stack, _pairs = _stack_bundle(tmp_path, mode, pairs_in_bundle=False)
        tiers = run("pair-tiers", "--bundle", str(bundle), "--pairs", "-", stdin=json.dumps(pairs))
    else:
        tiers = run("pair-tiers", "--bundle", str(bundle))
    assert tiers.returncode == 0, tiers.stderr
    assert tiers.stdout == expected.stdout


def test_a_code_bundle_reads_its_pairs_from_a_file(tmp_path):
    bundle, stack_input, pairs = _stack_bundle(tmp_path, "code", pairs_in_bundle=False)
    pairs_file = tmp_path / "pairs.json"
    pairs_file.write_bytes(json.dumps([dict(pair, intersection_count=2) for pair in pairs]).encode("utf-8"))
    result = run("pair-tiers", "--bundle", str(bundle), "--pairs", str(pairs_file))
    assert result.returncode == 0, result.stderr
    assert result.stdout == run("pair-tiers", "--input", "-", stdin=json.dumps(stack_input)).stdout


@pytest.mark.parametrize("mode, args, stdin, needle", [
    ("code", ("pair-tiers", "--bundle", "{bundle}"), None, "a code-mode bundle needs --pairs"),
    ("compose", ("pair-tiers", "--bundle", "{bundle}", "--pairs", "-"), "[]", "--pairs is for a code-mode bundle"),
    ("code", ("pair-tiers", "--input", "-", "--pairs", "-"), "{}", "--pairs goes with --bundle"),
    ("code", ("pair-tiers", "--input", "-", "--bundle", "{bundle}"), "{}", "not allowed with argument"),
    ("code", ("metadata", "--input", "-", "--bundle", "{bundle}"), "{}", "not allowed with argument"),
    ("code", ("metadata", "--bundle", "-"), "{}", "metadata reads --bundle from a file, not stdin"),
    ("code", ("pair-tiers", "--bundle", "-", "--pairs", "{pairs}"), "{}", "pair-tiers reads --bundle from a file"),
    ("code", ("metadata", "--bundle", "{bundle}", "--pairs", "-"), "[]", "unrecognized arguments: --pairs"),
], ids=["code-without-pairs", "compose-with-pairs", "pairs-with-input", "pair-tiers-bundle-and-input",
        "metadata-bundle-and-input", "metadata-bundle-stdin", "pair-tiers-bundle-stdin", "metadata-pairs"])
def test_a_flag_used_with_the_wrong_source_exits_2(mode, args, stdin, needle, tmp_path):
    bundle, _stack, pairs = _stack_bundle(tmp_path, mode, pairs_in_bundle=False)
    pairs_file = tmp_path / "pairs.json"
    pairs_file.write_bytes(json.dumps(pairs).encode("utf-8"))
    argv = [arg.replace("{bundle}", str(bundle)).replace("{pairs}", str(pairs_file)) for arg in args]
    result = subprocess.run([sys.executable, str(SCRIPT), *argv], input=stdin, capture_output=True, text=True,
                            cwd=tmp_path)
    assert (result.returncode, result.stdout) == (2, ""), result.stderr
    assert needle in result.stderr, result.stderr


@pytest.mark.parametrize("change, pairs, needle", [
    ({"per_library_extractions": None}, None, "the bundle's `per_library_extractions` must be an array"),
    ({"per_library_extractions": [{"library": "react", "confidence": "Deep"}]}, None,
     "the bundle's per_library_extractions[0].confidence"),
    ({"per_library_extractions": [{"name": "react", "confidence": "T1"}]}, None,
     "the bundle's per_library_extractions[0].library must be a non-empty string"),
    ({"per_library_extractions": [{"library": "react", "confidence": "T1", "file_count": "12"}]}, None,
     "the bundle's per_library_extractions[0].file_count must be a whole number"),
    ({"per_library_extractions": [{"library": "react", "confidence": "T1", "source_authority": "vendor"}]}, None,
     "the bundle's per_library_extractions[0].source_authority"),
    ({"integrations": [{"a": "react", "b": "vue"}]}, None, "the bundle's integrations[0].b 'vue' is not one of"),
    ({"integrations": {"a": "react"}}, None, "the bundle's `integrations` must be an array"),
    ({"mode": "both"}, None, "the bundle's mode"),
    ({}, [{"a": "react", "b": "vue"}], "--pairs[0].b 'vue' is not one of the libraries"),
    ({}, {"a": "react"}, "`--pairs` must be an array of {a, b} objects"),
    ({"per_library_extractions": [{"library": "react", "confidence": "T1"}] * 2}, None,
     "the bundle's per_library_extractions[1].library: library 'react' is listed twice"),
    ({"per_library_extractions": [{"library": "react", "confidence": "T1"}, {"library": "zod", "confidence": "T1"}],
      "integrations": [{"a": "react", "b": "zod"}, {"a": "zod", "b": "react"}]}, None,
     "the bundle's integrations[1]: the pair 'zod' + 'react' is listed twice"),
    ({"per_library_extractions": [{"library": "react", "confidence": "T1"}, {"library": "zod", "confidence": "T1"}]},
     [{"a": "react", "b": "zod"}, {"a": "zod", "b": "react"}],
     "--pairs[1]: the pair 'zod' + 'react' is listed twice"),
], ids=["no-entries", "bad-tier", "no-library", "bad-file-count", "bad-authority", "unknown-pair-member",
        "integrations-not-a-list", "bad-mode", "unknown-pairs-member", "pairs-not-a-list", "library-twice",
        "pair-twice", "pairs-pair-twice"])
def test_a_bundle_error_names_the_bundle_field(change, pairs, needle, tmp_path):
    bundle = tmp_path / "extraction-bundle.json"
    data = {"mode": "code" if pairs is not None else "compose",
            "per_library_extractions": [{"library": "react", "confidence": "T1"}], "integrations": [], **change}
    bundle.write_bytes(json.dumps(data).encode("utf-8"))
    args = ("pair-tiers", "--bundle", str(bundle), *(("--pairs", "-") if pairs is not None else ()))
    result = run(*args, stdin=json.dumps(pairs))
    assert (result.returncode, result.stdout) == (2, ""), result.stderr
    assert needle in result.stderr and len(result.stderr.strip().splitlines()) == 1, result.stderr
    if pairs is None:
        assert run("metadata", "--bundle", str(bundle)).stderr == result.stderr


def test_a_bundle_that_is_not_json_is_named(tmp_path):
    """pair-tiers reads two inputs on a code bundle: a JSON error names the one it could not parse."""
    bundle = tmp_path / "extraction-bundle.json"
    bundle.write_bytes(b"{not json")
    result = run("pair-tiers", "--bundle", str(bundle), "--pairs", "-", stdin="[]")
    assert (result.returncode, result.stdout) == (2, ""), result.stderr
    assert f"the input {bundle} is not valid JSON" in result.stderr, result.stderr
    bundle.write_bytes(json.dumps({"mode": "code", "per_library_extractions": []}).encode("utf-8"))
    result = run("pair-tiers", "--bundle", str(bundle), "--pairs", "-", stdin="{not json")
    assert (result.returncode, result.stdout) == (2, ""), result.stderr
    assert "the input - is not valid JSON" in result.stderr, result.stderr


def test_metadata_reads_a_file(tmp_path):
    path = tmp_path / "stack.json"
    path.write_bytes(json.dumps(stack([("café", "T3", "internal")]), ensure_ascii=False).encode("utf-8"))
    result = run("metadata", "--input", str(path))
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["libraries"] == ["café"]
    assert (out["confidence_tier"], out["source_authority"]) == ("T3", "internal")
    assert result.stdout.isascii(), "non-ASCII names are escaped for a Windows console"


def test_stdin_is_read_as_utf8_under_a_cp1252_console():
    """A Windows pipe hands stdin over as cp1252: `--input -` still reads the UTF-8 a step pipes."""
    data = stack([("café", "T1", None), ("ŝkf", "T2", None)], [("café", "ŝkf")])
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    result = subprocess.run([sys.executable, str(SCRIPT), "metadata", "--input", "-"],
                            input=json.dumps(data, ensure_ascii=False).encode("utf-8"),
                            capture_output=True, env=env)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    out = json.loads(result.stdout.decode("ascii"))
    assert out["libraries"] == ["café", "ŝkf"]  # U+015D is C5 9D in UTF-8; cp1252 has no 0x9D
    assert out["integration_pairs"] == [["café", "ŝkf"]]


@pytest.mark.parametrize("args, stdin, needle", [
    (("metadata", "--input", "-"), "{not json", "not valid JSON"),
    (("metadata", "--input", "-"), '{"mode": "compose", "libraries": [{"name": "a", "confidence": "T9"}]}',
     "libraries[0].confidence"),
    (("pair-tiers", "--input", "missing.json"), None, "cannot read the input"),
    (("library-tiers", "--records", "-", "--libraries", "a"),
     '{"entries": [{"source_library": "b", "extraction_method": "ast_bridge"}]}', "is not one of --libraries"),
    (("library-tiers", "--records", "missing.json", "--libraries", "a"), None, "cannot read the input"),
], ids=["bad-json", "bad-tier", "missing-file", "records-unknown-library", "records-missing-file"])
def test_an_input_error_exits_2_with_one_line(args, stdin, needle, tmp_path):
    result = subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True, text=True,
                            cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == ""
    assert needle in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1


@pytest.mark.parametrize("args", [(), ("metadata",), ("pair-tiers", "--input"), ("render", "--input", "-"),
                                  ("library-tiers", "--records", "-"), ("library-tiers", "--libraries", "a"),
                                  ("relabel",), ("provenance", "--records", "r.json", "--input", "-"),
                                  ("provenance", "--records", "r.json", "--input", "-", "--target", "p.json"),
                                  ("references", "--bundle", "b.json"),
                                  ("references", "--mode", "mixed", "--bundle", "b.json"),
                                  ("evidence-report", "--bundle", "b.json", "--run-dir", ".", "--provenance", "p.json"),
                                  ("evidence-report", "--bundle", "b.json", "--provenance", "p.json",
                                   "--target", "e.md")],
                         ids=["no-command", "no-input", "input-without-value", "unknown-command",
                              "records-without-libraries", "libraries-without-records", "relabel-without-records",
                              "provenance-without-target", "provenance-without-bundle", "references-without-mode",
                              "references-unknown-mode", "evidence-report-without-target",
                              "evidence-report-without-run-dir"])
def test_a_usage_error_exits_2(args):
    result = run(*args, stdin="")
    assert result.returncode == 2
    assert result.stdout == ""


def test_help_names_every_command():
    result = run("--help")
    assert result.returncode == 0
    for command in ("relabel", "library-tiers", "pair-tiers", "metadata", "provenance", "references",
                    "evidence-report"):
        assert command in result.stdout, command


# --------------------------------------------------------------------------
# references and evidence-report (#1156)
# --------------------------------------------------------------------------

TEMPLATE = SCRIPTS.parent.parent / "skf-create-stack-skill" / "assets" / "stack-skill-template.md"
VALIDATOR = SCRIPTS / "skf-validate-output.py"
T2_FUTURE = "render: replaced by createRoot in 19 (T2-future) [QMD:react-temporal:changelog]"
SCOPE_DECISION = {"gate": "rank-and-confirm.scope", "default_action": "C", "taken_action": "C",
                  "reason": "headless: kept the recommended scope",
                  "evidence": {"scope": ["react", "zod"], "dropped": [{"library": "lodash", "reason": "dev only"}],
                               "prior_kept": ["express"]}}
WARNING = "[step-04/warn] extraction-partial: zod: extraction budget reached"


def _write_json(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(data).encode("utf-8"))
    return path


def _code_run_files(tmp_path, **changes) -> dict[str, Path]:
    """A code-mode run folder as step 7 finds it: the bundle (react with a T2-future item, zod with none,
    left-pad failed, one react + zod pair), the export records and the pair-intersect result, which names
    the pair the other way round."""
    bundle = {
        "mode": "code", "scope": ["react", "zod", "left-pad"],
        "per_library_extractions": [
            {"library": "zod", "status": "partial", "version": "3.22.4", "confidence": "T1-low", "file_count": 3,
             "usage_patterns": [], "warnings": ["extraction budget reached"], "temporal": {}},
            {"library": "react", "status": "success", "version": "18.2.0", "confidence": "T1", "file_count": 12,
             "usage_patterns": ["hooks in function components (src/App.tsx:4)"], "warnings": [],
             "temporal": {"deprecated_exports": [T2_FUTURE], "migration_notes": [], "version_warnings": [],
                          "t2_annotation_count": 1}},
        ],
        "failed": [{"library": "left-pad", "reason": "no usable data"}],
        "integrations": [{"a": "react", "b": "zod", "type": "validation", "tier": "T1-low",
                          "qualifier": "grep-co-import", "key_files": ["src/form.tsx:9", "src/api.ts:3"],
                          "description": "zod validates the form state react holds"}],
        "cross_cutting": [],
    }
    bundle.update(changes)
    records = {"entries": [
        {"export_name": "useState", "export_type": "function", "params": ["initial: S"],
         "return_type": "[S, Dispatch<S>]", "source_file": "src/hooks.ts", "source_line": 4, "source_library": "react",
         "extraction_method": "ast_bridge", "confidence": "T1", "signature_source": "T1"},
        {"export_name": "Component", "export_type": "class", "params": [], "source_file": "src/component.ts",
         "source_line": 2, "source_library": "react", "extraction_method": "ast_bridge", "confidence": "T1",
         "signature_source": "T1"},
        {"export_name": "Fragment", "export_type": "constant", "source_file": "src/fragment.ts", "source_line": 1,
         "source_library": "react", "extraction_method": "source_reading", "confidence": "T1-low",
         "signature_source": "T1-low"},
    ]}
    pairs = {"pairs": [{"a": "zod", "b": "react", "intersection_count": 7,
                        "files": [{"path": "src/form.tsx", "line_a": 1, "line_b": 2}]}],
             "truncated": False, "total_pairs": 1}
    return {"bundle": _write_json(tmp_path / "run" / "extraction-bundle.json", bundle),
            "records": _write_json(tmp_path / "run" / "export-records.json", records),
            "pairs": _write_json(tmp_path / "run" / "pair-intersect.json", pairs)}


def _compose_bundle(tmp_path, **changes) -> Path:
    """A compose-mode bundle: two constituents, one pair the [VS] report rates Blocked."""
    bundle = {
        "mode": "compose", "scope": ["react", "express"],
        "per_library_extractions": [
            {"library": "react", "skill_dir": "react", "version": "18.2.0", "confidence": "T1",
             "exports": ["render", "useState", "Fragment", "createRoot"],
             "signatures": {"render": "render(el)", "useState": "useState(initial)"},
             "usage_patterns": ["render at the root (src/main.tsx:3)"], "description_keywords": ["ui"]},
            {"library": "express", "skill_dir": "express", "version": None, "confidence": "T2",
             "exports": ["Router"], "signatures": {}, "usage_patterns": []},
        ],
        "failed": [],
        "integrations": [{"a": "react", "b": "express", "type": "adapter", "tier": "T2",
                          "qualifier": "architecture-co-mention", "key_files": [],
                          "evidence": ["[from skill: react] render(el)", "[from skill: express] Router()"],
                          "reference": '**Architecture reference:** "react renders what express serves" '
                                       "(architecture doc line 12)",
                          "vs": {"pair": "blocked", "overall": "CONDITIONALLY_FEASIBLE"}}],
        "cross_cutting": [],
    }
    bundle.update(changes)
    return _write_json(tmp_path / "compose run" / "extraction-bundle.json", bundle)


def _references(*args: str) -> dict:
    result = run("references", *args)
    assert result.returncode == 0, result.stderr
    assert result.stdout.isascii()
    return json.loads(result.stdout)


def _text(path: Path) -> str:
    """A written file, its bytes checked for UTF-8 and `\\n` line ends before they are decoded."""
    data = path.read_bytes()
    assert b"\r" not in data, f"{path.name} holds a \\r"
    return data.decode("utf-8")


def _template_structure(heading: str) -> tuple[list[str], list[str]]:
    """The `## ` headings and the `**Label:**` header labels of one of the template's two reference structures."""
    text = TEMPLATE.read_text(encoding="utf-8")
    block = text[text.index(f"## {heading} Structure\n"):]
    block = block[block.index("```markdown\n") + len("```markdown\n"):]
    block = block[:block.index("\n```")]
    return (re.findall(r"^## (.+)$", block, re.MULTILINE),
            re.findall(r"^(\*\*[A-Za-z -]+:\*\*)", block, re.MULTILINE))


def _structure(text: str) -> tuple[list[str], list[str]]:
    return re.findall(r"^## (.+)$", text, re.MULTILINE), re.findall(r"^(\*\*[A-Za-z -]+:\*\*)", text, re.MULTILINE)


def test_references_writes_each_library_and_pair_file(tmp_path):
    files = _code_run_files(tmp_path)
    out = tmp_path / "staging" / "references"
    result = _references("--mode", "code", "--bundle", str(files["bundle"]), "--records", str(files["records"]),
                         "--pairs", str(files["pairs"]), "--out", str(out))
    assert result["written"] == [
        {"path": "zod.md", "placeholders": ["usage-patterns", "common-imports"]},
        {"path": "react.md", "placeholders": ["usage-patterns", "common-imports"]},
        {"path": "integrations/react-zod.md", "placeholders": ["integration-pattern", "usage-convention"]},
    ]
    react = _text(out / "react.md")
    assert react.startswith("# react Reference\n\n**Version:** 18.2.0\n**Import count:** 12 files\n"
                            "**Confidence:** T1\n\n## Key Exports\n\n")
    exports = react.split("## Key Exports\n\n", 1)[1].split("\n\n", 1)[0].splitlines()
    assert exports == ["- `useState(initial: S) -> [S, Dispatch<S>]` *function* (src/hooks.ts:4)",
                       "- `Component()` *class* (src/component.ts:2)",
                       "- `Fragment` *constant* (src/fragment.ts:1)"], "every record, in records order"
    assert f"## Migration & Deprecation\n\n- {T2_FUTURE}\n" in react
    assert "<!-- skf:fill usage-patterns -->" in react and "<!-- skf:fill common-imports -->" in react
    zod = _text(out / "zod.md")
    assert "**Version:** 3.22.4\n**Import count:** 3 files\n**Confidence:** T1-low\n" in zod
    assert "## Key Exports\n\nnone recorded\n" in zod
    assert "Migration & Deprecation" not in zod, "a library with no temporal item has no such section"
    pair = _text(out / "integrations" / "react-zod.md")
    assert pair.startswith("# react + zod Integration\n\n**Type:** validation\n**Co-import files:** 7\n"
                           "**Confidence:** T1-low (grep-co-import)\n\n")
    assert "## Key Files\n\n- src/form.tsx:9\n- src/api.ts:3\n" in pair
    assert "<!-- skf:fill integration-pattern -->" in pair and "<!-- skf:fill usage-convention -->" in pair
    # The rows follow library_order: react has more importing files than zod.
    assert [row["library"] for row in result["index"]["rows"]] == ["react", "zod"]
    assert sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()) == [
        "integrations/react-zod.md", "react.md", "zod.md"], "no temp file is left"


def test_the_index_rows_hold_the_first_five_exports(tmp_path):
    files = _code_run_files(tmp_path)
    records = {"entries": [{"export_name": f"e{i}", "source_library": "react"} for i in range(7)]
               + [{"export_name": "e0", "source_library": "react"}, {"export_name": "a|b", "source_library": "zod"}]}
    _write_json(files["records"], records)
    index = _references("--mode", "code", "--bundle", str(files["bundle"]), "--records", str(files["records"]))["index"]
    assert index["header"] == ["| Library | Imports | Key Exports | Confidence | Reference |",
                               "|---------|---------|-------------|------------|-----------|"]
    template = TEMPLATE.read_text(encoding="utf-8")
    assert template.count("\n".join(index["header"]) + "\n") == 2, "the inline and the catalog index head"
    react, zod = index["rows"]
    assert react["inline"] == ("| react | 12 | `e0`, `e1`, `e2`, `e3`, `e4`, +2 more | T1 | "
                               "[ref](references/react.md) |")
    assert react["catalog"] == react["inline"].replace("[ref](references/react.md)", "[ref](react.md)")
    assert zod["inline"] == "| zod | 3 | `a\\|b` | T1-low | [ref](references/zod.md) |", "a `|` is escaped"


@pytest.mark.parametrize("line, expected", [
    (lambda: mod.export_line({"export_name": "f", "export_type": "function", "params": [],
                              "return_type": "Tpl<`a${string}`>"}),
     "- ``f() -> Tpl<`a${string}`>`` *function*"),
    (lambda: mod.compose_export_line("tag", {"tag": "`tag`"}, "lib"), "- `` `tag` `` [from skill: lib]"),
    (lambda: mod.index_row("lib", 1, "T1", ["a``b"], "lib.md"), "| lib | 1 | ```a``b``` | T1 | [ref](lib.md) |"),
], ids=["inner-run", "edge-backticks", "double-run"])
def test_a_code_span_fences_past_every_backtick_run(line, expected):
    """A fence longer than the longest backtick run inside, padded when the text starts or ends with one."""
    assert line() == expected


def test_a_value_with_a_newline_stays_on_its_line(tmp_path):
    files = _code_run_files(tmp_path)
    bundle = json.loads(files["bundle"].read_bytes())
    bundle["per_library_extractions"][1]["temporal"]["migration_notes"] = ["old thing\n\n## Fake Heading"]
    bundle["integrations"][0]["key_files"] = ["src/form.tsx:9\n## Evil"]
    _write_json(files["bundle"], bundle)
    records = json.loads(files["records"].read_bytes())
    records["entries"][0]["params"] = ["opts: {\n  a: string\n}"]
    _write_json(files["records"], records)
    out = tmp_path / "out"
    _references("--mode", "code", "--bundle", str(files["bundle"]), "--records", str(files["records"]),
                "--pairs", str(files["pairs"]), "--out", str(out))
    react = _text(out / "react.md")
    assert "- `useState(opts: { a: string }) -> [S, Dispatch<S>]` *function* (src/hooks.ts:4)\n" in react
    assert "- old thing ## Fake Heading\n" in react
    assert re.findall(r"^## (.+)$", react, re.MULTILINE) == [
        "Key Exports", "Usage Patterns", "Migration & Deprecation", "Common Imports"]
    pair = _text(out / "integrations" / "react-zod.md")
    assert "- src/form.tsx:9 ## Evil\n" in pair
    assert re.findall(r"^## (.+)$", pair, re.MULTILINE) == ["Integration Pattern", "Key Files", "Usage Convention"]


def test_references_writes_the_compose_files(tmp_path):
    bundle = _compose_bundle(tmp_path)
    out = tmp_path / "references"
    result = _references("--mode", "compose", "--bundle", str(bundle), "--out", str(out))
    react = _text(out / "react.md")
    assert "**Version:** 18.2.0\n**Export count:** 4 exports\n**Confidence:** T1\n" in react
    assert ("## Key Exports\n\n- `render(el)` [from skill: react]\n- `useState(initial)` [from skill: react]\n"
            "- `Fragment` [from skill: react]\n- `createRoot` [from skill: react]\n") in react
    assert "Migration & Deprecation" not in react
    assert "**Version:** unknown\n**Export count:** 1 exports\n**Confidence:** T2\n" in _text(out / "express.md")
    pair = _text(out / "integrations" / "react-express.md")
    assert ("**Co-import files:** 0\n**Confidence:** T2 (architecture-co-mention) [composed] [VS: Blocked]\n"
            in pair)
    assert ("## Key Files\n\n- [from skill: react] render(el)\n- [from skill: express] Router()\n"
            '- **Architecture reference:** "react renders what express serves" (architecture doc line 12)\n'
            "- VS overall: CONDITIONALLY_FEASIBLE\n- VS pair: Blocked\n") in pair
    index = result["index"]
    assert index["header"][0] == "| Library | Export Count | Key Exports | Confidence | Reference |"
    assert index["rows"][0]["inline"] == ("| react | 4 | `render`, `useState`, `Fragment`, `createRoot` | T1 | "
                                          "[ref](references/react.md) |")


@pytest.mark.parametrize("qualifier, vs, label", [
    ("inferred-shared-domain", None, "T2 (inferred-shared-domain) [inferred from shared domain]"),
    ("constituent-documented-contract", None, "T2 (constituent-documented-contract) [composed]"),
    ("architecture-co-mention", {"pair": "Risky", "overall": "FEASIBLE"},
     "T2 (architecture-co-mention) [composed] [VS: Risky]"),
    ("architecture-co-mention", {"pair": "Verified", "overall": "FEASIBLE"},
     "T2 (architecture-co-mention) [composed]"),
], ids=["inferred", "contract", "risky", "verified"])
def test_a_compose_label_takes_its_suffixes(qualifier, vs, label):
    pair = {"a": "a", "b": "b", "type": "t", "tier": "T2", "qualifier": qualifier, "vs": vs}
    (parsed,) = mod.bundle_pairs({"mode": "compose", "integrations": [pair]}, "compose")
    assert mod.pair_label("compose", parsed) == label


def test_without_out_only_the_index_prints(tmp_path):
    files = _code_run_files(tmp_path)
    before = sorted(p.name for p in tmp_path.rglob("*"))
    result = _references("--mode", "code", "--bundle", str(files["bundle"]), "--records", str(files["records"]))
    assert result["written"] == [] and len(result["index"]["rows"]) == 2
    assert sorted(p.name for p in tmp_path.rglob("*")) == before, "an index-only call writes nothing"


def _refused(tmp_path, *args: str, needle: str) -> None:
    out = tmp_path / "out"
    result = run(*args)
    assert (result.returncode, result.stdout) == (2, ""), result.stderr
    assert needle in result.stderr and len(result.stderr.strip().splitlines()) == 1, result.stderr
    assert not out.exists(), "a refused call wrote a file"


@pytest.mark.parametrize("case, needle", [
    ("mode-mismatch", "--mode is compose, but the bundle's mode is code"),
    ("record-of-no-library", "entries[0].source_library 'lodash' is not a library of the bundle"),
    ("out-without-pairs", "--out on a code-mode bundle needs --pairs"),
    ("no-records", "a code-mode bundle needs --records"),
    ("pair-without-count", "has no entry in the pair-intersect result (--pairs)"),
    ("absolute-name", "would write outside --out"),
    ("parent-name", "would write outside --out"),
    ("backslash-name", "would write outside --out"),
    ("two-files-one-path", "two files would be written to one path"),
    ("bad-temporal", "per_library_extractions[1].temporal.migration_notes must be an array of strings"),
])
def test_references_refuses_a_bad_code_input(case, needle, tmp_path):
    files = _code_run_files(tmp_path)
    bundle = json.loads(files["bundle"].read_bytes())
    args = ["--mode", "code", "--bundle", str(files["bundle"]), "--records", str(files["records"]),
            "--pairs", str(files["pairs"]), "--out", str(tmp_path / "out")]
    if case == "mode-mismatch":
        args[1] = "compose"
        args = args[:4] + args[8:]
    elif case == "record-of-no-library":
        _write_json(files["records"], {"entries": [{"export_name": "map", "source_library": "lodash"}]})
    elif case == "out-without-pairs":
        args = args[:6] + args[8:]
    elif case == "no-records":
        args = args[:4]
    elif case == "pair-without-count":
        _write_json(files["pairs"], {"pairs": []})
    elif case == "bad-temporal":
        bundle["per_library_extractions"][1]["temporal"]["migration_notes"] = [{"note": "x"}]
    else:
        # two-files-one-path: REACT.md and react.md are one file on a case-insensitive file system.
        name = {"absolute-name": "/etc/zod", "parent-name": "../zod", "backslash-name": "nested\\zod",
                "two-files-one-path": "REACT"}[case]
        bundle["per_library_extractions"][0]["library"] = name
        bundle["integrations"] = []
        _write_json(files["records"], {"entries": []})
    _write_json(files["bundle"], bundle)
    _refused(tmp_path, "references", *args, needle=needle)


@pytest.mark.parametrize("flags, needle", [
    (("--records", "r.json"), "--records is for a code-mode bundle"),
    (("--pairs", "p.json"), "--pairs is for a code-mode bundle"),
], ids=["records", "pairs"])
def test_references_refuses_the_code_flags_on_a_compose_bundle(flags, needle, tmp_path):
    bundle = _compose_bundle(tmp_path)
    _refused(tmp_path, "references", "--mode", "compose", "--bundle", str(bundle), *flags,
             "--out", str(tmp_path / "out"), needle=needle)


def test_a_scoped_name_lands_where_the_link_and_the_validator_look(tmp_path):
    files = _code_run_files(tmp_path)
    bundle = json.loads(files["bundle"].read_bytes())
    bundle["per_library_extractions"][1]["library"] = "@scope/react"
    bundle["integrations"][0]["a"] = "@scope/react"
    _write_json(files["bundle"], bundle)
    _write_json(files["records"], {"entries": []})
    _write_json(files["pairs"], {"pairs": [{"a": "@scope/react", "b": "zod", "intersection_count": 1, "files": []}]})
    out = tmp_path / "pkg" / "references"
    result = _references("--mode", "code", "--bundle", str(files["bundle"]), "--records", str(files["records"]),
                         "--pairs", str(files["pairs"]), "--out", str(out))
    assert (out / "@scope" / "react.md").is_file() and (out / "integrations" / "@scope" / "react-zod.md").is_file()
    assert [item["path"] for item in result["written"]] == ["zod.md", "@scope/react.md",
                                                            "integrations/@scope/react-zod.md"]
    validator = _load(VALIDATOR, "skf_validate_output_scoped_reference")
    meta = {"libraries": ["@scope/react", "zod"], "integration_pairs": [["@scope/react", "zod"]]}
    issues, _observed = validator.validate_stack_structure(out.parent, meta)
    assert not [issue for issue in issues if issue["check"] == "references"], issues


def test_a_failed_write_leaves_nothing(tmp_path):
    files = _code_run_files(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "integrations").write_bytes(b"a file where the pair folder should be")
    result = run("references", "--mode", "code", "--bundle", str(files["bundle"]), "--records", str(files["records"]),
                 "--pairs", str(files["pairs"]), "--out", str(out))
    assert (result.returncode, result.stdout) == (2, "")
    assert "cannot write" in result.stderr and len(result.stderr.strip().splitlines()) == 1
    assert sorted(p.name for p in out.iterdir()) == ["integrations"], "the library files written first are removed"


def _fill(text: str) -> str:
    """A written file with each marker filled as the step fills it."""
    return re.sub(r"<!-- skf:fill ([a-z-]+) -->", lambda m: f"Filled {m.group(1)} (src/app.ts:1).", text)


@pytest.mark.parametrize("mode", MODES)
def test_the_written_files_pass_the_structure_pass(mode, tmp_path):
    """The acceptance check: filled in, the helper's files raise no references or tier_labels issue, and their
    headings and header labels are the template's."""
    if mode == "code":
        files = _code_run_files(tmp_path)
        args = ["--records", str(files["records"]), "--pairs", str(files["pairs"])]
        bundle = files["bundle"]
    else:
        bundle, args = _compose_bundle(tmp_path), []
    package = tmp_path / "demo-stack"
    out = package / "references"
    _references("--mode", mode, "--bundle", str(bundle), *args, "--out", str(out))
    validator = _load(VALIDATOR, f"skf_validate_output_written_{mode}")
    library_headings, library_labels = _template_structure("references/{library}.md")
    pair_headings, pair_labels = _template_structure("references/integrations/{pair}.md")
    if mode == "compose":
        library_labels = [label.replace("Import count", "Export count") for label in library_labels]
    for path in sorted(out.rglob("*.md")):
        text = _fill(_text(path))
        path.write_bytes(text.encode("utf-8"))
        assert "skf:fill" not in text
        headings, labels = _structure(text)
        if path.parent.name == "integrations":
            assert validator._TYPE_LINE_RE.search(text)
            assert (headings, labels) == (pair_headings, pair_labels), path.name
        else:
            assert validator._VERSION_LINE_RE.search(text)
            expected = [h for h in library_headings if h != "Migration & Deprecation" or "react" in path.name
                        and mode == "code"]
            assert (headings, labels) == (expected, library_labels), path.name
        assert validator._TIER_LABEL_RE.search(validator._header_region(text)), path.name
    data = json.loads(bundle.read_bytes())
    meta = {"libraries": [entry["library"] for entry in data["per_library_extractions"]],
            "integration_pairs": [[pair["a"], pair["b"]] for pair in data["integrations"]]}
    issues, observed = validator.validate_stack_structure(package, meta)
    assert not [issue for issue in issues if issue["check"] in ("references", "tier_labels")], issues
    assert (observed["reference_files"], observed["pair_files"]) == (2, 1)


def _sink(run_dir: Path, decisions=(), warnings=(), extra_warning_lines=()) -> None:
    """The run sink as skf-emit-result-envelope.py record writes it: one JSON value per line."""
    run_dir.mkdir(parents=True, exist_ok=True)
    if decisions:
        (run_dir / "headless-decisions.jsonl").write_bytes(
            "".join(json.dumps(d) + "\n" for d in decisions).encode("utf-8"))
    if warnings or extra_warning_lines:
        lines = [json.dumps(w) for w in warnings] + list(extra_warning_lines)
        (run_dir / "warnings.jsonl").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


MAP = {"provenance_version": "2.0", "skill_name": "demo-stack", "skill_type": "stack", "entries": [
    {"export_name": "useState", "source_library": "react", "signature_source": "T1"},
    {"export_name": "Component", "source_library": "react", "signature_source": "T1"},
    {"export_name": "Fragment", "source_library": "react", "signature_source": "T1-low"},
    {"export_name": "z", "source_library": "zod", "signature_source": "T3"},
]}


def _evidence(tmp_path, *extra: str, script: Path = SCRIPT, provenance=MAP, pairs=True, bundle=None):
    files = _code_run_files(tmp_path)
    run_dir = tmp_path / "run"
    prov = tmp_path / "forge" / "provenance-map.json"
    if provenance is not None:
        _write_json(prov, provenance)
    target = tmp_path / "forge" / "evidence-report.md"
    args = ["evidence-report", "--bundle", str(bundle or files["bundle"]), "--run-dir", str(run_dir),
            "--provenance", str(prov), *(["--pairs", str(files["pairs"])] if pairs else []), "--target", str(target),
            *extra]
    result = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True)
    return result, target


def test_the_evidence_report_lists_every_section(tmp_path):
    _sink(tmp_path / "run", decisions=[SCOPE_DECISION], warnings=[WARNING])
    result, target = _evidence(tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "target": str(target), "library_count": 2, "failed_count": 1, "integration_count": 1, "warning_count": 1,
        "decision_count": 1, "confidence_distribution": {"t1": 2, "t1_low": 1, "t2": 0, "t3": 1}}
    report = _text(target)
    assert report.startswith("# demo-stack Evidence Report\n\n**Mode:** code | **Libraries:** 2 extracted, 1 failed | "
                             "**Integration pairs:** 1\n")
    assert ("| Library | Status | Version | Tier | Imports | Map entries | Usage patterns | T2 items | Warnings |"
            in report)
    assert "| react | success | 18.2.0 | T1 | 12 | 3 | 1 | 1 | none |" in report
    assert "| zod | partial | 3.22.4 | T1-low | 3 | 1 | 0 | 0 | extraction budget reached |" in report
    assert T2_FUTURE not in report, "the report counts temporal items, never lists them"
    assert "**Failed:** left-pad: no usable data\n" in report
    assert "| react + zod | validation | T1-low (grep-co-import) | 7 |" in report
    assert f"## Warnings\n\n- {WARNING}\n" in report
    assert ("## Auto-Decisions\n\n- `rank-and-confirm.scope`: C (headless: kept the recommended scope); "
            "dropped: lodash (dev only); prior_kept: express\n") in report
    assert report.endswith("Provenance entries by `signature_source` (`metadata.json` counts libraries): "
                           "T1: 2, T1-low: 1, T2: 0, T3: 1\n")
    assert sorted(p.name for p in target.parent.iterdir()) == ["evidence-report.md", "provenance-map.json"]


def test_the_report_bins_what_the_stats_helper_bins(tmp_path):
    result, _target = _evidence(tmp_path)
    assert result.returncode == 0, result.stderr
    stats = subprocess.run([sys.executable, str(STATS), str(tmp_path / "forge" / "provenance-map.json"),
                            "--shape", "stack"], input="{}", capture_output=True, text=True)
    assert stats.returncode == 0, stats.stderr
    assert json.loads(result.stdout)["confidence_distribution"] == json.loads(stats.stdout)["confidence_distribution"]


def test_no_sink_reads_none_and_a_cut_line_is_named(tmp_path):
    (tmp_path / "run").mkdir()
    result, target = _evidence(tmp_path)
    assert result.returncode == 0, result.stderr
    report = _text(target)
    assert "## Warnings\n\nnone\n" in report and "## Auto-Decisions\n\nnone\n" in report
    _sink(tmp_path / "run", decisions=[SCOPE_DECISION], warnings=[WARNING], extra_warning_lines=['"cut sho', '""'])
    (tmp_path / "run" / "headless-decisions.jsonl").write_bytes(b'{"gate": "compile-stack.review"\n{}\n')
    result, target = _evidence(tmp_path)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert (out["warning_count"], out["decision_count"]) == (1, 0)
    report = _text(target)
    assert (f"## Warnings\n\n- {WARNING}\n- sink_line_unreadable: warnings.jsonl:2\n"
            "- sink_line_unreadable: warnings.jsonl:3\n") in report
    assert ("## Auto-Decisions\n\n- sink_line_unreadable: headless-decisions.jsonl:1\n"
            "- sink_line_unreadable: headless-decisions.jsonl:2\n") in report


def test_the_sink_lines_end_at_a_newline_only(tmp_path):
    """A U+2028 inside a warning is part of its line, as the emitter reads it."""
    warning = "[step-05/info] ccc-files-dropped: react + zod: src/a\u2028b.ts"
    _sink(tmp_path / "run", extra_warning_lines=[json.dumps(warning, ensure_ascii=False)])
    assert "\u2028".encode("utf-8") in (tmp_path / "run" / "warnings.jsonl").read_bytes(), "a raw U+2028"
    result, target = _evidence(tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["warning_count"] == 1
    assert "sink_line_unreadable" not in _text(target)


def test_a_sink_value_with_a_newline_stays_on_its_line(tmp_path):
    _sink(tmp_path / "run", decisions=[dict(SCOPE_DECISION, reason="kept\n## Warnings")],
          warnings=["one\n## Auto-Decisions"])
    result, target = _evidence(tmp_path)
    assert result.returncode == 0, result.stderr
    report = _text(target)
    assert "- one ## Auto-Decisions\n" in report
    assert "(kept ## Warnings)" in report
    assert re.findall(r"^## (.+)$", report, re.MULTILINE) == [
        "Libraries", "Integrations", "Warnings", "Auto-Decisions", "Confidence Distribution"]


def test_the_sink_reader_counts_what_the_emitter_counts(tmp_path):
    """read_sink keeps skf-emit-result-envelope.py's rules, so the report lists what the envelope carries."""
    emitter = _load(EMITTER, "skf_emit_result_envelope_for_stack_metadata")
    run_dir = tmp_path / "run"
    _sink(run_dir, decisions=[SCOPE_DECISION], warnings=[WARNING, " padded "],
          extra_warning_lines=['"cut sho', '""', '{"not": "a string"}', json.dumps("a\u2028b", ensure_ascii=False)])
    with open(run_dir / "headless-decisions.jsonl", "ab") as fh:
        fh.write(b'{}\n["a list"]\n{"gate": "cut\n')
    decisions, warnings, problems = mod.read_sink(run_dir)
    emitted_decisions, emitted_warnings, emitted_problems = emitter.read_sink(run_dir)
    assert decisions == [value for _where, value in emitted_decisions]
    assert warnings == emitted_warnings
    assert problems[mod.SINK_DECISIONS] + problems[mod.SINK_WARNINGS] == emitted_problems
    assert (len(decisions), len(warnings), len(emitted_problems)) == (1, 3, 6)


@pytest.mark.parametrize("case", ["no-stats-helper", "no-map", "bad-map"])
def test_no_binning_reads_not_computed(case, tmp_path):
    (tmp_path / "run").mkdir()
    script, provenance = SCRIPT, MAP
    if case == "no-stats-helper":
        script = tmp_path / "scripts" / SCRIPT.name
        script.parent.mkdir()
        script.write_bytes(SCRIPT.read_bytes())
    elif case == "no-map":
        provenance = None
    else:
        provenance = ["not", "an", "object"]
    result, target = _evidence(tmp_path, script=script, provenance=provenance)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["confidence_distribution"] is None
    report = _text(target)
    reason = {"no-stats-helper": "skf-render-metadata-stats.py not found", "no-map": "cannot read the provenance map",
              "bad-map": "is not a JSON object"}[case]
    (line,) = [line for line in report.splitlines() if line.startswith("Provenance entries")]
    assert ": not computed: " in line and reason in line, line
    if case == "no-stats-helper":
        assert "| react | success | 18.2.0 | T1 | 12 | 3 |" in report, "the map was read"
    else:
        assert "| react | success | 18.2.0 | T1 | 12 | n/a |" in report
        assert report.startswith("# Stack Evidence Report\n"), "no map, no skill name"


def test_a_compose_report_shows_exports_and_the_pair_label(tmp_path):
    bundle = _compose_bundle(tmp_path)
    (tmp_path / "run").mkdir(exist_ok=True)
    entries = {"entries": [{"export_name": "render", "source_library": "react", "signature_source": "T1"}]}
    result, target = _evidence(tmp_path, provenance=entries, pairs=False, bundle=bundle)
    assert result.returncode == 0, result.stderr
    report = _text(target)
    assert "**Mode:** compose | **Libraries:** 2 extracted, 0 failed | **Integration pairs:** 1" in report
    assert "| Library | Status | Version | Tier | Exports | Map entries |" in report
    assert "| react | n/a | 18.2.0 | T1 | 4 | 1 | 1 | 0 | none |" in report
    assert "| express | n/a | unknown | T2 | 1 | 0 | 0 | 0 | none |" in report
    assert "**Failed:** none" in report
    assert "| react + express | adapter | T2 (architecture-co-mention) [composed] [VS: Blocked] | 0 |" in report


@pytest.mark.parametrize("case, needle", [
    ("code-without-pairs", "a code-mode bundle needs --pairs"),
    ("compose-with-pairs", "--pairs is for a code-mode bundle"),
    ("no-run-dir", "is not a folder"),
    ("bad-failed", "the bundle's failed[0] must be an object"),
])
def test_the_evidence_report_refuses_a_bad_input(case, needle, tmp_path):
    files = _code_run_files(tmp_path)
    if case != "no-run-dir":
        (tmp_path / "run").mkdir(exist_ok=True)
    target = tmp_path / "forge" / "evidence-report.md"
    bundle, pairs = files["bundle"], ["--pairs", str(files["pairs"])]
    if case == "code-without-pairs":
        pairs = []
    elif case == "compose-with-pairs":
        bundle = _compose_bundle(tmp_path)
    elif case == "bad-failed":
        _write_json(bundle, dict(json.loads(bundle.read_bytes()), failed=["left-pad"]))
    run_dir = tmp_path / ("missing" if case == "no-run-dir" else "run")
    result = run("evidence-report", "--bundle", str(bundle), "--run-dir", str(run_dir),
                 "--provenance", str(tmp_path / "map.json"), *pairs, "--target", str(target))
    assert (result.returncode, result.stdout) == (2, "")
    assert needle in result.stderr and len(result.stderr.strip().splitlines()) == 1, result.stderr
    assert not target.parent.exists()


def test_a_report_target_it_cannot_write_leaves_nothing(tmp_path):
    (tmp_path / "run").mkdir()
    files = _code_run_files(tmp_path)
    blocker = tmp_path / "forge-file"
    blocker.write_bytes(b"a file where the version folder should be")
    result = run("evidence-report", "--bundle", str(files["bundle"]), "--run-dir", str(tmp_path / "run"),
                 "--provenance", str(tmp_path / "map.json"), "--pairs", str(files["pairs"]),
                 "--target", str(blocker / "evidence-report.md"))
    assert (result.returncode, result.stdout) == (2, "")
    assert "cannot write" in result.stderr and len(result.stderr.strip().splitlines()) == 1
    assert blocker.read_bytes() == b"a file where the version folder should be"
