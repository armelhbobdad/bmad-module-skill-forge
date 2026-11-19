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

#1264: the banner gave every empty collection the same advice, since the
classifier never read its folder. It now runs `qmd collection show` for
each empty name (and for no other registered name), and the emitter folds
the folder check into one cause per name: `folder missing` (removal
alone), `folder present` (re-index or removal), `folder in another
project` (no advice: QMD's index is shared) or `folder unknown` (today's
two lines). Each warning ends with its cause; setup still removes none.

#1265: setup read only each registry entry's `name`, so a collection Brief
Skill registered with `status: "pending"` (its embed check failed) counted
as healthy, nothing named it, and the mark stayed after the user fixed it.
The classifier now splits the marked names by the counts of its one
`qmd collection list`: `pending_cleared` (a count above 0: healthy, and
clean-stale --clear-pending-from drops the mark) and `pending` (a count of
0 or none: not healthy). The banner names both, and each pending name that
is not empty is a `qmd_collection_pending: <name>` warning.
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
    assert (out["empty_paths"], out["empty_folder_missing"], out["empty_outside_project"]) == ({}, [], [])


@pytest.mark.parametrize("folder,make,missing,outside", [
    pytest.param("project/forge-data/demo", None, True, False, id="folder-missing"),
    pytest.param("project/forge-data/demo", "file", True, False, id="path-is-a-file"),
    pytest.param("project/forge-data/demo", "dir", False, False, id="folder-present"),
    pytest.param("other/forge-data/demo", "dir", False, True, id="another-project-folder"),
    pytest.param("other/forge-data/demo", None, True, True, id="another-project-no-folder"),
    pytest.param(None, None, False, False, id="no-path"),
])
def test_an_empty_collection_s_folder_is_checked(tmp_path, folder, make, missing, outside):
    project = tmp_path / "project"
    project.mkdir()
    path = tmp_path / folder if folder else None
    if make == "dir":
        path.mkdir(parents=True)
    elif make == "file":
        path.parent.mkdir(parents=True)
        path.write_text("", encoding="utf-8")
    names = ["demo-brief", "demo-extraction"]
    paths = {"demo-brief": str(path) if path else None, "demo-extraction": str(tmp_path / "gone")}
    out = classify.classify(names, names, project, paths, files={"demo-brief": 0, "demo-extraction": 9})
    assert (out["empty"], out["healthy"]) == (["demo-brief"], ["demo-extraction"])
    assert out["empty_paths"] == ({"demo-brief": str(path)} if path else {})
    assert out["empty_folder_missing"] == (["demo-brief"] if missing else [])
    assert out["empty_outside_project"] == (["demo-brief"] if outside else [])
    # Reported, never orphaned: the removal gate never sees an empty name.
    assert out["orphaned"] == [] and out["orphaned_paths"] == {}
    keys = list(out)
    start = keys.index("empty") + 1
    assert keys[start:start + 3] == ["empty_paths", "empty_folder_missing", "empty_outside_project"]


def test_the_folder_lists_keep_the_empty_order_and_need_a_project_root(tmp_path):
    present = tmp_path / "project" / "skills" / "c"
    present.mkdir(parents=True)
    names = ["a-docs", "b-temporal", "c-brief", "d-extraction"]
    paths = {"a-docs": str(tmp_path / "elsewhere" / "a"), "b-temporal": str(tmp_path / "project" / "b"),
             "c-brief": str(present)}
    files = dict.fromkeys(names, 0)
    out = classify.classify(names, names, tmp_path / "project", paths, files)
    assert out["empty"] == names
    assert list(out["empty_paths"]) == ["a-docs", "b-temporal", "c-brief"]
    assert out["empty_folder_missing"] == ["a-docs", "b-temporal"]
    assert out["empty_outside_project"] == ["a-docs"]
    # With no project root nothing counts as outside it.
    assert classify.classify(names, names, None, paths, files)["empty_outside_project"] == []


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


def _show(name: str, path) -> str:
    """`qmd collection show <name>` as qmd 2.8.3 prints it."""
    return f"Collection: {name}\n  Path:     {path}\n  Pattern:  skill-brief.yaml\n  Include:  yes (default)\n"


def test_the_classifier_shows_each_empty_collection_once(tmp_path, monkeypatch, capsys, registry):
    calls = []
    folder = tmp_path / "forge-data" / "demo"

    def fake_qmd(*args):
        calls.append(args)
        if args == ("collection", "list"):
            return 0, LISTING, ""
        if args == ("collection", "show", "demo-brief"):
            return 0, _show("demo-brief", folder), ""
        # Any other call (a show of the healthy name, or a remove) fails the run.
        raise AssertionError(f"unexpected qmd call {args}")

    monkeypatch.setattr(classify, "_run_qmd", fake_qmd)
    out = _classify_cli(monkeypatch, capsys, registry, tmp_path)
    assert out["empty"] == ["demo-brief"]
    assert out["healthy"] == ["demo-extraction"]
    assert out["live_names"] == ["demo-brief", "demo-extraction"]
    assert out["empty_paths"] == {"demo-brief": str(folder)}
    assert (out["empty_folder_missing"], out["empty_outside_project"]) == (["demo-brief"], [])
    assert out["orphaned"] == [] and out["orphaned_paths"] == {}
    assert calls == [("collection", "list"), ("collection", "show", "demo-brief")]


@pytest.mark.parametrize("shown", [
    pytest.param((1, "", "Collection not found: demo-brief"), id="show-exits-non-zero"),
    pytest.param((0, "Collection: demo-brief\n  Pattern:  skill-brief.yaml\n", ""), id="no-path-line"),
    pytest.param((None, "", "qmd not found on PATH"), id="qmd-gone"),
])
def test_an_empty_collection_qmd_cannot_show_has_no_folder(tmp_path, monkeypatch, capsys, registry, shown):
    calls = []

    def fake_qmd(*args):
        calls.append(args)
        if args == ("collection", "list"):
            return 0, LISTING, ""
        if args == ("collection", "show", "demo-brief"):
            return shown
        raise AssertionError(f"unexpected qmd call {args}")

    monkeypatch.setattr(classify, "_run_qmd", fake_qmd)
    # A failed show is no classifier failure: main() returns, so the CLI exits 0.
    out = _classify_cli(monkeypatch, capsys, registry, tmp_path)
    assert out["status"] == "ok"
    assert out["empty"] == ["demo-brief"]
    assert (out["empty_paths"], out["empty_folder_missing"], out["empty_outside_project"]) == ({}, [], [])
    assert calls == [("collection", "list"), ("collection", "show", "demo-brief")]


def test_live_names_carry_no_counts(tmp_path, monkeypatch, capsys, registry):
    monkeypatch.setattr(classify, "_run_qmd", lambda *args: pytest.fail(f"unexpected qmd call {args}"))
    out = _classify_cli(monkeypatch, capsys, registry, tmp_path, "--live-names", "demo-brief,demo-extraction")
    assert out["empty"] == []
    assert out["healthy"] == ["demo-brief", "demo-extraction"]
    assert (out["empty_paths"], out["empty_folder_missing"], out["empty_outside_project"]) == ({}, [], [])


@pytest.mark.parametrize("listing", [
    "demo-brief\ndemo-extraction\n",
    LISTING.replace("  Files:    0\n", ""),
], ids=["bare-names", "block-without-a-count"])
def test_a_listing_without_a_count_leaves_the_collection_healthy(tmp_path, monkeypatch, capsys, registry, listing):
    calls = []

    def fake_qmd(*args):
        calls.append(args)
        return 0, listing, ""

    monkeypatch.setattr(classify, "_run_qmd", fake_qmd)
    out = _classify_cli(monkeypatch, capsys, registry, tmp_path)
    assert out["empty"] == []
    assert out["healthy"] == ["demo-brief", "demo-extraction"]
    assert (out["empty_paths"], out["empty_folder_missing"], out["empty_outside_project"]) == ({}, [], [])
    assert calls == [("collection", "list")]


def test_a_listing_with_no_empty_collection_shows_none(tmp_path, monkeypatch, capsys, registry):
    calls = []

    def fake_qmd(*args):
        calls.append(args)
        if args == ("collection", "list"):
            return 0, LISTING.replace("  Files:    0\n", "  Files:    9\n"), ""
        # A show of a collection that holds files fails the run.
        raise AssertionError(f"unexpected qmd call {args}")

    monkeypatch.setattr(classify, "_run_qmd", fake_qmd)
    out = _classify_cli(monkeypatch, capsys, registry, tmp_path)
    assert (out["empty"], out["healthy"]) == ([], ["demo-brief", "demo-extraction"])
    assert (out["empty_paths"], out["empty_folder_missing"], out["empty_outside_project"]) == ({}, [], [])
    assert calls == [("collection", "list")]


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

# One empty collection of each cause, and e-docs, outside the project and
# with no folder: another project's, so never "folder missing".
CAUSED = {**CLASSIFIED, "live_names": ["a-docs", "b-temporal", "c-brief", "d-extraction", "e-docs"],
          "healthy": [], "empty": ["a-docs", "b-temporal", "c-brief", "d-extraction", "e-docs"],
          "empty_paths": {"a-docs": "/p/forge-data/a", "b-temporal": "/p/_bmad-output/b-temporal",
                          "c-brief": "/q/forge-data/c", "e-docs": "/moved/forge-data/e"},
          "empty_folder_missing": ["a-docs", "e-docs"], "empty_outside_project": ["c-brief", "e-docs"]}
CAUSES = {"a-docs": "folder missing", "b-temporal": "folder present", "c-brief": "folder in another project",
          "d-extraction": "folder unknown", "e-docs": "folder in another project"}


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
    # A classification with no folder check (an older classifier's) gives every name no folder.
    assert folded["hygiene_empty_causes"] == {"a-docs": "folder unknown", "b-temporal": "folder unknown"}
    failed = emit.fold_staged({}, {emit.STAGED_CLASSIFY: None})
    assert failed["hygiene_result"] == "qmd_unavailable"
    assert (failed["hygiene_empty"], failed["hygiene_empty_collections"]) == (0, [])
    assert failed["hygiene_empty_causes"] == {}
    # A classification an older classifier staged, with no `empty` list, names none.
    older = {key: value for key, value in CLASSIFIED.items() if key != "empty"}
    assert emit.fold_staged({}, {emit.STAGED_CLASSIFY: older})["hygiene_empty_collections"] == []


def test_fold_staged_gives_each_empty_collection_one_cause():
    folded = emit.fold_staged({}, {emit.STAGED_CLASSIFY: CAUSED})
    assert folded["hygiene_empty_causes"] == CAUSES
    assert list(folded["hygiene_empty_causes"]) == CAUSED["empty"]
    # An empty name is never an orphan: nothing is kept, so nothing is offered for removal.
    assert (folded["hygiene_orphaned_kept"], folded["hygiene_orphaned_removed"]) == (0, 0)


def test_each_empty_collection_is_a_warning_and_the_envelope_validates():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    plain = emit.assemble_envelope(emit.fold_staged(_payload(), {emit.STAGED_CLASSIFY: {**CLASSIFIED, "empty": []}}))
    env = emit.assemble_envelope(emit.fold_staged(_payload(qmd_status="daemon_stopped"),
                                                  {emit.STAGED_CLASSIFY: CLASSIFIED}))
    warnings = env["skf_setup"]["warnings"]
    assert [w for w in warnings if w.startswith("qmd_collection_empty")] == [
        "qmd_collection_empty: a-docs (folder unknown)", "qmd_collection_empty: b-temporal (folder unknown)"]
    assert warnings.index("qmd_daemon_stopped") < warnings.index("qmd_collection_empty: a-docs (folder unknown)")
    assert env["skf_setup"]["status"] == plain["skf_setup"]["status"] == "success"
    assert plain["skf_setup"]["warnings"] == []
    assert emit._validate_against_schema(env, schema) == []
    description = schema["properties"]["skf_setup"]["properties"]["warnings"]["description"]
    assert "qmd_collection_empty" in description and "'<name> (<cause>)'" in description
    for cause in ("folder missing", "folder present", "folder in another project", "folder unknown"):
        assert f"'{cause}'" in description


def test_each_warning_ends_with_its_cause():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    env = emit.assemble_envelope(emit.fold_staged(_payload(), {emit.STAGED_CLASSIFY: CAUSED}))
    assert env["skf_setup"]["warnings"] == [
        "qmd_collection_empty: a-docs (folder missing)",
        "qmd_collection_empty: b-temporal (folder present)",
        "qmd_collection_empty: c-brief (folder in another project)",
        "qmd_collection_empty: d-extraction (folder unknown)",
        "qmd_collection_empty: e-docs (folder in another project)"]
    assert env["skf_setup"]["status"] == "success"
    assert emit._validate_against_schema(env, schema) == []
    # A cause the emitter does not know, or none, reads as an unknown folder.
    odd = emit.assemble_envelope(_payload(hygiene_empty=2, hygiene_empty_collections=["a-docs", "b-temporal"],
                                          hygiene_empty_causes={"a-docs": "folder gone"}))
    assert odd["skf_setup"]["warnings"] == ["qmd_collection_empty: a-docs (folder unknown)",
                                            "qmd_collection_empty: b-temporal (folder unknown)"]


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
    # With no folder check every name's folder is unknown: today's two advice lines.
    assert lines[healthy + 1:healthy + 5] == [
        "  3 registered collection(s) hold no indexed files, so Deep-tier searches find nothing in them: "
        "a-docs, b-temporal, c-brief",
        "  Folder unknown: a-docs, b-temporal, c-brief. `qmd collection show <name>` gives each one's folder. "
        "When that folder is gone or holds no file its pattern matches, re-indexing cannot refill it: run "
        "`qmd collection remove <name>`, and the next Deep-tier setup drops its registry entry",
        "  When the folder does hold such files, run `qmd update` (it re-indexes every collection on this "
        "machine and empties any whose folder is gone), then `qmd embed -c <name>`",
        ""]
    # A bare `qmd update` or unscoped `qmd embed` is never the first advice: it
    # re-indexes the whole shared index.
    assert not [line for line in lines if "Run `qmd update`" in line or line.endswith("`qmd embed`")]
    assert not [line for line in lines if line.startswith("  QMD Registry: empty.")]
    assert "  Forge ready. Deep tier active." in lines
    # With no registered collection at all, the registry still reads empty.
    none = _report({**CLASSIFIED, "live_names": [], "healthy": [], "empty": []})
    assert "  QMD Registry: empty. Collections are created automatically when you run /skf-create-skill." in none
    assert not [line for line in none if "hold no indexed files" in line]


def test_the_banner_gives_each_cause_its_own_advice():
    lines = _report(CAUSED)
    healthy = lines.index("  0 collection(s) healthy")
    assert lines[healthy + 1:healthy + 8] == [
        "  5 registered collection(s) hold no indexed files, so Deep-tier searches find nothing in them: "
        "a-docs, b-temporal, c-brief, d-extraction, e-docs",
        "  Folder missing: a-docs. Re-indexing cannot refill a collection whose folder is gone: run "
        "`qmd collection remove <name>` for each, and the next Deep-tier setup drops its registry entry",
        "  Folder present: b-temporal. When the folder holds files its pattern matches (as after a reset index), "
        "run `qmd update` (it re-indexes every collection on this machine and empties any whose folder is gone), "
        "then `qmd embed -c <name>`; when it holds none, run `qmd collection remove <name>`",
        "  Folder in another project: c-brief, e-docs. QMD's index is shared by every project on this machine, "
        "so setup leaves them to the project that owns the folder",
        "  Folder unknown: d-extraction. `qmd collection show <name>` gives each one's folder. When that folder "
        "is gone or holds no file its pattern matches, re-indexing cannot refill it: run "
        "`qmd collection remove <name>`, and the next Deep-tier setup drops its registry entry",
        "  When the folder does hold such files, run `qmd update` (it re-indexes every collection on this "
        "machine and empties any whose folder is gone), then `qmd embed -c <name>`",
        ""]
    # Another project's collection is named on its own line only, with no
    # removal or re-index advice: QMD's index is shared by every project.
    elsewhere = [line for line in lines if "e-docs" in line]
    assert len(elsewhere) == 2 and elsewhere[1].startswith("  Folder in another project:")
    assert not [line for line in lines if line.startswith("  Folder missing:") and "e-docs" in line]
    assert "qmd collection remove" not in elsewhere[1] and "qmd update" not in elsewhere[1]
    # A cause line shows only when a name has that cause.
    missing_only = _report({**CAUSED, "empty": ["a-docs"]})
    assert [line.split(":")[0] for line in missing_only if line.startswith("  Folder ")] == ["  Folder missing"]


def test_the_emitter_keeps_the_qmd_update_note_on_one_line():
    """#1271's test reads this phrase from the emitter's source: no re-wrap may split it."""
    source = (SCRIPTS / "skf-emit-result-envelope.py").read_text(encoding="utf-8")
    assert "collection on this machine and empties any whose folder is gone" in source


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


# --------------------------------------------------------------------------
# (f) Brief Skill's pending mark (#1265)
# --------------------------------------------------------------------------


# p-brief is marked and QMD lists files for it, q-brief is marked and holds
# none, r-brief is marked and its block gives no count, s-brief is unmarked.
PENDING_LISTING = """Collections (4):

p-brief (qmd://p-brief/)
  Pattern:  skill-brief.yaml
  Files:    3
  Updated:  1d ago

q-brief (qmd://q-brief/)
  Pattern:  skill-brief.yaml
  Files:    0
  Updated:  0s ago

r-brief (qmd://r-brief/)
  Pattern:  skill-brief.yaml

s-brief (qmd://s-brief/)
  Pattern:  skill-brief.yaml
  Files:    2
  Updated:  2d ago

"""

PENDING_REGISTRY = """qmd_collections:
  - name: p-brief
    type: brief
    status: pending
  - name: q-brief
    type: brief
    status: pending
  - name: r-brief
    type: brief
    status: pending
  - name: s-brief
    type: brief
"""


@pytest.fixture
def marked_registry(tmp_path) -> Path:
    path = tmp_path / "forge-tier.yaml"
    path.write_text(PENDING_REGISTRY, encoding="utf-8")
    return path


def test_the_classifier_splits_the_marks_by_the_counts_it_already_has(tmp_path, monkeypatch, capsys,
                                                                      marked_registry):
    calls = []

    def fake_qmd(*args):
        calls.append(args)
        if args == ("collection", "list"):
            return 0, PENDING_LISTING, ""
        if args == ("collection", "show", "q-brief"):
            return 0, _show("q-brief", tmp_path / "forge-data" / "q"), ""
        # The split reads the counts of the one listing: any other call fails the run.
        raise AssertionError(f"unexpected qmd call {args}")

    monkeypatch.setattr(classify, "_run_qmd", fake_qmd)
    out = _classify_cli(monkeypatch, capsys, marked_registry, tmp_path)
    assert out["pending"] == ["q-brief", "r-brief"]
    assert out["pending_cleared"] == ["p-brief"]
    assert out["healthy"] == ["p-brief", "s-brief"]
    assert out["empty"] == ["q-brief"]
    assert calls == [("collection", "list"), ("collection", "show", "q-brief")]


def test_with_live_names_every_mark_stays_pending(tmp_path, monkeypatch, capsys, marked_registry):
    monkeypatch.setattr(classify, "_run_qmd", lambda *args: pytest.fail(f"unexpected qmd call {args}"))
    out = _classify_cli(monkeypatch, capsys, marked_registry, tmp_path,
                        "--live-names", "p-brief,q-brief,r-brief,s-brief")
    assert (out["pending"], out["pending_cleared"]) == (["p-brief", "q-brief", "r-brief"], [])
    assert (out["healthy"], out["empty"]) == (["s-brief"], [])


def test_a_bare_name_listing_leaves_every_mark_pending(tmp_path, monkeypatch, capsys, marked_registry):
    calls = []

    def fake_qmd(*args):
        calls.append(args)
        return 0, "p-brief\nq-brief\nr-brief\ns-brief\n", ""

    monkeypatch.setattr(classify, "_run_qmd", fake_qmd)
    out = _classify_cli(monkeypatch, capsys, marked_registry, tmp_path)
    assert (out["pending"], out["pending_cleared"]) == (["p-brief", "q-brief", "r-brief"], [])
    assert (out["healthy"], out["empty"]) == (["s-brief"], [])
    assert calls == [("collection", "list")]


PENDING = {**CLASSIFIED, "live_names": ["p-brief", "q-brief", "r-brief", "s-brief"],
           "healthy": ["p-brief", "s-brief"], "empty": ["q-brief"], "empty_paths": {},
           "empty_folder_missing": [], "empty_outside_project": [],
           "pending": ["q-brief", "r-brief"], "pending_cleared": ["p-brief"]}
CLEARED = {"status": "ok", "version": "v1", "qmd_removed": ["gone-brief"], "qmd_pending_cleared": ["p-brief"],
           "ccc_removed": [], "wrote": True}

PENDING_LINE = ("  1 registered collection(s) still marked pending, since Brief Skill could not confirm their files "
                "and QMD's listing gives no file count: r-brief. Re-embed each one with `qmd embed -c <name>`, or "
                "run /skf-brief-skill again for its skill. The mark clears only once QMD's listing gives a file "
                "count, so a qmd that lists bare names keeps it until you upgrade qmd")
CLEARED_LINE = "  1 collection(s) no longer marked pending, since QMD now lists files for them: p-brief"


def test_fold_staged_reads_the_pending_marks():
    folded = emit.fold_staged({}, {emit.STAGED_CLASSIFY: PENDING, emit.STAGED_CLEAN_STALE: CLEARED})
    # A marked empty name is reported as empty alone.
    assert (folded["hygiene_pending"], folded["hygiene_pending_collections"]) == (1, ["r-brief"])
    assert (folded["hygiene_pending_cleared"], folded["hygiene_pending_cleared_collections"]) == (1, ["p-brief"])
    assert (folded["hygiene_healthy"], folded["hygiene_empty_collections"]) == (2, ["q-brief"])


@pytest.mark.parametrize("classified,cleaned", [
    pytest.param(None, None, id="both-failed"),
    pytest.param({key: value for key, value in PENDING.items() if key not in ("pending", "pending_cleared")},
                 {key: value for key, value in CLEARED.items() if key != "qmd_pending_cleared"}, id="older-outputs"),
])
def test_fold_staged_gives_no_pending_mark_from_a_failed_or_older_helper(classified, cleaned):
    folded = emit.fold_staged({}, {emit.STAGED_CLASSIFY: classified, emit.STAGED_CLEAN_STALE: cleaned})
    assert (folded["hygiene_pending"], folded["hygiene_pending_collections"]) == (0, [])
    assert (folded["hygiene_pending_cleared"], folded["hygiene_pending_cleared_collections"]) == (0, [])


def test_each_still_pending_collection_is_one_warning():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    env = emit.assemble_envelope(emit.fold_staged(_payload(), {emit.STAGED_CLASSIFY: PENDING,
                                                               emit.STAGED_CLEAN_STALE: CLEARED}))
    warnings = env["skf_setup"]["warnings"]
    assert [w for w in warnings if w.startswith("qmd_collection_pending")] == ["qmd_collection_pending: r-brief"]
    # Right after the empty warnings; the cleared and the empty marked name get no pending warning.
    assert warnings[warnings.index("qmd_collection_empty: q-brief (folder unknown)") + 1] == (
        "qmd_collection_pending: r-brief")
    assert not [w for w in warnings if "p-brief" in w]
    assert [w for w in warnings if "q-brief" in w] == ["qmd_collection_empty: q-brief (folder unknown)"]
    assert env["skf_setup"]["status"] == "success"
    assert emit._validate_against_schema(env, schema) == []
    description = schema["properties"]["skf_setup"]["properties"]["warnings"]["description"]
    assert "qmd_collection_pending" in description and "`qmd embed -c <name>`" in description
    assert "the mark clears only once QMD's listing gives a file count" in description


def _report_with(classified, cleaned=None) -> list[str]:
    staged = {emit.STAGED_CLASSIFY: classified}
    if cleaned is not None:
        staged[emit.STAGED_CLEAN_STALE] = cleaned
    payload = emit.fold_staged(_payload(project_root="/p", forge_data_folder="/p/forge-data",
                                        orphan_auto_resolution=None), staged)
    return emit.render_report(payload, emit.load_tier_rules(TIER_RULES))


def test_the_banner_names_the_pending_and_the_cleared_marks():
    lines = _report_with(PENDING, CLEARED)
    pending = lines.index(PENDING_LINE)
    # After the empty lines, before the stale count; the cleared line follows that count.
    assert lines[pending - 1].startswith("  When the folder does hold such files")
    assert lines[pending + 1:pending + 3] == ["  1 stale QMD registry entry/entries cleaned", CLEARED_LINE]
    assert "q-brief" not in lines[pending]
    assert "  2 collection(s) healthy" in lines
    # No clean-stale output: no cleared line.
    assert not [line for line in _report_with(PENDING) if "no longer marked pending" in line]


def test_an_all_pending_registry_is_not_empty():
    every_pending = {**PENDING, "live_names": ["r-brief", "u-brief"], "healthy": [], "empty": [],
                     "pending": ["r-brief", "u-brief"], "pending_cleared": []}
    lines = _report_with(every_pending)
    healthy = lines.index("  0 collection(s) healthy")
    assert lines[healthy + 1] == PENDING_LINE.replace("  1 registered", "  2 registered").replace(
        ": r-brief.", ": r-brief, u-brief.")
    assert not [line for line in lines if line.startswith("  QMD Registry: empty.")]


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    ends = [i for i in (text.find("\n### ", start + 1), text.find("\n## ", start + 1)) if i >= 0]
    return text[start:min(ends)] if ends else text[start:]


def test_the_docs_say_what_setup_does_with_the_mark():
    registry = (ROOT / "src" / "knowledge" / "qmd-registry.md").read_text(encoding="utf-8")
    assert "should flag" not in registry
    assert "pending (" in _section(registry, "### Example 3")
    hygiene = (ROOT / "src" / "skf-setup" / "references" / "auto-index.md").read_text(encoding="utf-8")
    assert "`pending_cleared`" in _section(hygiene, "### 2.")
    [call] = [block for block in _section(hygiene, "### 4.").split("```")
              if block.startswith("bash") and "clean-stale" in block]
    assert '--clear-pending-from "{run_dir}/qmd-classify.json"' in call
