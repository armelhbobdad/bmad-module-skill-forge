#!/usr/bin/env python3
"""#1245: setup's QMD hygiene counted a registered collection that holds no
indexed files as healthy.

`skf-qmd-classify-collections.py` called a collection healthy when its name
was live and registered, and read no `Files:` line of `qmd collection list`,
so a collection qmd 2.8.3 lists with `Files:    0` (it answers no Deep-tier
search) counted as healthy in the FORGE STATUS banner and the envelope
warned nothing. The classifier now lists it under `empty`, the emitter
names it on its own banner line and as a `qmd_collection_empty: <name>`
warning, and one `Files:` parser serves the classifier and
`skf-qmd-portfolio-similarity.py`. No check here runs the qmd a developer
has installed: every qmd call goes to a stand-in.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "src" / "shared" / "scripts"
SCHEMA_PATH = SCRIPTS / "schemas" / "skf-setup-result-envelope.v1.json"
TIER_RULES = ROOT / "src" / "skf-setup" / "references" / "tier-rules.md"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


classify = _load("skf_qmd_classify_empty", "skf-qmd-classify-collections.py")
emit = _load("skf_emit_result_envelope_empty", "skf-emit-result-envelope.py")
portfolio = _load("skf_qmd_portfolio_similarity_empty", "skf-qmd-portfolio-similarity.py")

# `qmd collection list` as qmd 2.8.3 prints it: a collection whose folder holds
# no file its pattern matches reads `Files:    0` and, holding none, `0s ago`.
LISTING = """Collections (2):

demo-brief (qmd://demo-brief/)
  Pattern:  skill-brief.yaml
  Files:    0
  Updated:  0s ago

demo-extraction (qmd://demo-extraction/)
  Pattern:  **/*
  Files:    9
  Updated:  43d ago

"""


# --------------------------------------------------------------------------
# (a) The `Files:` count of each block
# --------------------------------------------------------------------------


@pytest.mark.parametrize("listing,counts", [
    pytest.param(LISTING, {"demo-brief": 0, "demo-extraction": 9}, id="qmd-2.8.3"),
    pytest.param(LISTING.replace("\n", "\r\n"), {"demo-brief": 0, "demo-extraction": 9}, id="crlf"),
    pytest.param(LISTING.replace("  Files:    0\n", "  Files:    0 (updated never)\n"),
                 {"demo-brief": 0, "demo-extraction": 9}, id="count-with-a-note"),
    pytest.param(LISTING.replace("  Files:    0\n", ""), {"demo-brief": None, "demo-extraction": 9},
                 id="block-without-a-count"),
    pytest.param("demo-brief\ndemo-extraction\n", {"demo-brief": None, "demo-extraction": None},
                 id="bare-names"),
    pytest.param("No collections found. Run 'qmd collection add .' to create one.\n", {}, id="none"),
])
def test_each_block_gives_its_own_file_count(listing, counts):
    assert classify.parse_collection_file_counts(listing) == counts
    # The counts name the same collections the name parser reads.
    assert list(counts) == classify.parse_collection_list_output(listing)


# --------------------------------------------------------------------------
# (b) classify() with the counts
# --------------------------------------------------------------------------


def test_a_registered_collection_with_no_file_is_empty_and_stays_live():
    names = ["demo-brief", "demo-docs", "demo-extraction"]
    out = classify.classify(names, names, files={"demo-brief": 0, "demo-docs": None, "demo-extraction": 9})
    assert out["healthy"] == ["demo-docs", "demo-extraction"]
    assert out["empty"] == ["demo-brief"]
    assert out["live_names"] == names
    assert out["stale"] == [] and out["orphaned"] == []
    # `empty` comes right after `healthy`.
    keys = list(out)
    assert keys[keys.index("healthy") + 1] == "empty"


def test_every_registered_collection_empty_leaves_none_healthy():
    names = ["demo-brief", "demo-extraction"]
    out = classify.classify(names, names, files={"demo-brief": 0, "demo-extraction": 0})
    assert (out["healthy"], out["empty"]) == ([], names)


def test_an_unknown_count_stays_healthy():
    names = ["demo-brief", "demo-extraction"]
    assert classify.classify(names, names, files={"demo-brief": None})["healthy"] == names
    assert classify.classify(names, names)["empty"] == []


def test_an_orphan_with_no_file_stays_orphaned(tmp_path):
    path = str(tmp_path / "skills" / "stray-temporal")
    out = classify.classify(["stray-temporal"], [], tmp_path, {"stray-temporal": path}, files={"stray-temporal": 0})
    assert out["orphaned"] == ["stray-temporal"]
    assert out["empty"] == [] and out["healthy"] == []


# --------------------------------------------------------------------------
# (c) The CLI reads the counts from its one `qmd collection list` call
# --------------------------------------------------------------------------


@pytest.fixture
def registry(tmp_path) -> Path:
    path = tmp_path / "forge-tier.yaml"
    path.write_text("qmd_collections:\n  - name: demo-brief\n  - name: demo-extraction\n", encoding="utf-8")
    return path


def _classify_cli(monkeypatch, capsys, registry: Path, project: Path, *extra: str) -> dict:
    monkeypatch.setattr(sys, "argv", ["classify", "classify", "--registry-from-yaml", str(registry),
                                      "--project-root", str(project), *extra])
    classify.main()
    return json.loads(capsys.readouterr().out)


def test_the_classifier_lists_an_empty_collection_with_no_other_qmd_call(tmp_path, monkeypatch, capsys, registry):
    calls = []

    def fake_qmd(*args):
        calls.append(args)
        if args == ("collection", "list"):
            return 0, LISTING, ""
        raise AssertionError(f"unexpected qmd call {args}")

    monkeypatch.setattr(classify, "_run_qmd", fake_qmd)
    out = _classify_cli(monkeypatch, capsys, registry, tmp_path)
    assert out["empty"] == ["demo-brief"]
    assert out["healthy"] == ["demo-extraction"]
    assert out["live_names"] == ["demo-brief", "demo-extraction"]
    assert calls == [("collection", "list")]


def test_live_names_carry_no_counts(tmp_path, monkeypatch, capsys, registry):
    monkeypatch.setattr(classify, "_run_qmd", lambda *args: pytest.fail(f"unexpected qmd call {args}"))
    out = _classify_cli(monkeypatch, capsys, registry, tmp_path, "--live-names", "demo-brief,demo-extraction")
    assert out["empty"] == []
    assert out["healthy"] == ["demo-brief", "demo-extraction"]


@pytest.mark.parametrize("listing", [
    "demo-brief\ndemo-extraction\n",
    LISTING.replace("  Files:    0\n", ""),
], ids=["bare-names", "block-without-a-count"])
def test_a_listing_without_a_count_leaves_the_collection_healthy(tmp_path, monkeypatch, capsys, registry, listing):
    monkeypatch.setattr(classify, "_run_qmd", lambda *args: (0, listing, ""))
    out = _classify_cli(monkeypatch, capsys, registry, tmp_path)
    assert out["empty"] == []
    assert out["healthy"] == ["demo-brief", "demo-extraction"]


def test_the_names_helper_still_returns_two_values(monkeypatch):
    monkeypatch.setattr(classify, "_run_qmd", lambda *args: (0, LISTING, ""))
    assert classify.fetch_live_names_from_qmd() == (["demo-brief", "demo-extraction"], None)
    assert classify.fetch_live_collections_from_qmd() == (
        ["demo-brief", "demo-extraction"], {"demo-brief": 0, "demo-extraction": 9}, None)


def test_qmd_down_still_exits_2(tmp_path, monkeypatch, capsys, registry):
    monkeypatch.setattr(classify, "_run_qmd", lambda *args: (1, "", "daemon down"))
    with pytest.raises(SystemExit) as exc:
        _classify_cli(monkeypatch, capsys, registry, tmp_path)
    assert exc.value.code == 2


# --------------------------------------------------------------------------
# (d) The emitter: the staged classification, the warnings and the banner
# --------------------------------------------------------------------------


CLASSIFIED = {"status": "ok", "version": "v1", "live_names": ["a-docs", "b-temporal", "c-brief"],
              "healthy": ["c-brief"], "empty": ["a-docs", "b-temporal"], "orphaned": [], "orphaned_paths": {},
              "stale": [], "foreign_filtered_count": 0, "foreign_filtered_sample": []}


def _payload(**over) -> dict:
    """A Deep re-run with nothing else to report."""
    payload = {
        "tier": "Deep", "previous_tier": "Deep",
        "tools": {"ast_grep": True, "gh_cli": True, "qmd": True, "ccc": False},
        "previous_tools": {"ast_grep": True, "gh_cli": True, "qmd": True, "ccc": False},
        "config_path": "/p/_bmad/_memory/forger-sidecar/forge-tier.yaml",
        "ccc_index": {"status": "none", "indexed_path": None, "file_count": None},
        "tier_override_active": False, "tier_override_invalid": False, "require_tier_satisfied": None,
        "qmd_status": "healthy", "error": None,
    }
    payload.update(over)
    return payload


def test_fold_staged_reads_the_empty_collections():
    folded = emit.fold_staged({}, {emit.STAGED_CLASSIFY: CLASSIFIED})
    assert (folded["hygiene_healthy"], folded["hygiene_empty"], folded["hygiene_empty_collections"]) == (
        1, 2, ["a-docs", "b-temporal"])
    failed = emit.fold_staged({}, {emit.STAGED_CLASSIFY: None})
    assert failed["hygiene_result"] == "qmd_unavailable"
    assert (failed["hygiene_empty"], failed["hygiene_empty_collections"]) == (0, [])
    # A classification an older classifier staged, with no `empty` list, names none.
    older = {key: value for key, value in CLASSIFIED.items() if key != "empty"}
    assert emit.fold_staged({}, {emit.STAGED_CLASSIFY: older})["hygiene_empty_collections"] == []


def test_each_empty_collection_is_a_warning_and_the_envelope_validates():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    plain = emit.assemble_envelope(emit.fold_staged(_payload(), {emit.STAGED_CLASSIFY: {**CLASSIFIED, "empty": []}}))
    env = emit.assemble_envelope(emit.fold_staged(_payload(qmd_status="daemon_stopped"),
                                                  {emit.STAGED_CLASSIFY: CLASSIFIED}))
    warnings = env["skf_setup"]["warnings"]
    assert [w for w in warnings if w.startswith("qmd_collection_empty")] == [
        "qmd_collection_empty: a-docs", "qmd_collection_empty: b-temporal"]
    assert warnings.index("qmd_daemon_stopped") < warnings.index("qmd_collection_empty: a-docs")
    assert env["skf_setup"]["status"] == plain["skf_setup"]["status"] == "success"
    assert plain["skf_setup"]["warnings"] == []
    assert emit._validate_against_schema(env, schema) == []
    assert "qmd_collection_empty" in schema["properties"]["skf_setup"]["properties"]["warnings"]["description"]


def test_a_failed_classifier_warns_of_no_empty_collection():
    env = emit.assemble_envelope(emit.fold_staged(_payload(), {emit.STAGED_CLASSIFY: None}))
    assert not [w for w in env["skf_setup"]["warnings"] if w.startswith("qmd_collection_empty")]


def _report(classified) -> list[str]:
    payload = emit.fold_staged(_payload(project_root="/p", forge_data_folder="/p/forge-data",
                                        orphan_auto_resolution=None),
                               {emit.STAGED_CLASSIFY: classified})
    return emit.render_report(payload, emit.load_tier_rules(TIER_RULES))


def test_the_banner_names_the_empty_collections_and_keeps_the_tier():
    every_empty = {**CLASSIFIED, "healthy": [], "empty": ["a-docs", "b-temporal", "c-brief"]}
    lines = _report(every_empty)
    healthy = lines.index("  0 collection(s) healthy")
    assert lines[healthy + 1:healthy + 4] == [
        "  3 registered collection(s) hold no indexed files, so Deep-tier searches find nothing in them: "
        "a-docs, b-temporal, c-brief",
        "  `qmd collection show <name>` gives each one's folder. When that folder is gone or holds no file its "
        "pattern matches, re-indexing cannot refill it: run `qmd collection remove <name>`, and the next "
        "Deep-tier setup drops its registry entry",
        "  When the folder does hold such files, run `qmd update` (it re-indexes every collection on this "
        "machine and empties any whose folder is gone), then `qmd embed -c <name>`"]
    # A bare `qmd update` or unscoped `qmd embed` is never the first advice: it
    # re-indexes the whole shared index.
    assert not [line for line in lines if "Run `qmd update`" in line or line.endswith("`qmd embed`")]
    assert not [line for line in lines if line.startswith("  QMD Registry: empty.")]
    assert "  Forge ready. Deep tier active." in lines
    # With no registered collection at all, the registry still reads empty.
    none = _report({**CLASSIFIED, "live_names": [], "healthy": [], "empty": []})
    assert "  QMD Registry: empty. Collections are created automatically when you run /skf-create-skill." in none
    assert not [line for line in none if "hold no indexed files" in line]


def test_a_failed_classifier_shows_no_empty_line():
    lines = _report(None)
    assert not [line for line in lines if "hold no indexed files" in line]
    assert "  QMD Registry: skipped (qmd unavailable; if the daemon is stopped, `qmd start` restores it)." in lines


# --------------------------------------------------------------------------
# (e) One `Files:` parser
# --------------------------------------------------------------------------


@pytest.mark.parametrize("listing", [
    LISTING, LISTING.replace("\n", "\r\n"), LISTING.replace("  Files:    0\n", "  Files:    0 (updated never)\n"),
    "demo-brief\n", "No collections found. Run 'qmd collection add .' to create one.\n",
], ids=["qmd-2.8.3", "crlf", "count-with-a-note", "bare-names", "none"])
def test_portfolio_reads_the_counts_with_the_classifier_parser(listing):
    assert portfolio.file_counts(listing) == classify.parse_collection_file_counts(listing)
    assert not hasattr(portfolio, "_FILES_RE")
