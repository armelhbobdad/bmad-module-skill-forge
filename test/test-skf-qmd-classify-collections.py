#!/usr/bin/env python3
"""Tests for skf-qmd-classify-collections.py.

Classification rules under test (per step 3 §2 and PR #244):

  Healthy   = forge-suffix-matched live ∩ registry
  Orphaned  = forge-suffix-matched live − registry, whose Path lies
              inside --project-root
  Stale     = registry − ALL live (includes foreign-suffix names)
  Foreign   = live − forge-suffix-matched, plus the suffix-matched names
              outside the registry whose Path lies elsewhere (silently
              excluded from every classification, reported as count +
              capped sample)

The PR #244 incident — a fresh-setup user with 48 unrelated Hindsight
memory-bank collections in their QMD daemon — is reproduced as
test_pr244_incident_reproduction below.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-qmd-classify-collections.py"
)

spec = importlib.util.spec_from_file_location("skf_qmd_classify", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


# ─── Forge-namespace recognition ────────────────────────────────────────────


@pytest.mark.parametrize("name,expected", [
    ("foo-brief",          True),
    ("foo-temporal",       True),
    ("foo-docs",           True),
    ("foo-extraction",     True),
    ("multi-word-skill-name-extraction", True),
    ("memory-root-1",      False),
    ("sessions-2",         False),
    ("foo",                False),
    ("foo-other",          False),
    ("brief",              False),  # exact match without prefix dash → not forge
    ("foo-brief-extra",    False),  # suffix must be terminal
    ("",                   False),
])
def test_is_forge_owned(name, expected):
    assert mod.is_forge_owned(name) is expected


# ─── parse_live_names ───────────────────────────────────────────────────────


def test_parse_live_names_handles_empty():
    assert mod.parse_live_names("") == []
    assert mod.parse_live_names("   ") == []


def test_parse_live_names_strips_whitespace():
    assert mod.parse_live_names(" foo , bar ,  baz ") == ["foo", "bar", "baz"]


def test_parse_live_names_dedups_preserving_order():
    assert mod.parse_live_names("a,b,a,c,b,a") == ["a", "b", "c"]


def test_parse_live_names_skips_empty_segments():
    assert mod.parse_live_names("a,,b,,,c,") == ["a", "b", "c"]


# ─── parse_collection_list_output (qmd CLI stdout) ───────────────────────────


def test_parse_collection_list_modern_format():
    """Newer qmd: header, blank lines, `name (qmd://name/)`, indented metadata.

    Regression for the silent no-op where suffixed entries failed the
    is_forge_owned check and every forge collection was mis-classified foreign.
    """
    raw = (
        "Collections (3):\n"
        "\n"
        "oms-cognee-brief (qmd://oms-cognee-brief/)\n"
        "  Pattern:  skill-brief.yaml\n"
        "  Files:    0\n"
        "\n"
        "livekit-extraction (qmd://livekit-extraction/)\n"
        "  Pattern:  *.rs\n"
        "  Files:    42\n"
        "\n"
        "memory-root-1 (qmd://memory-root-1/)\n"
        "  Files:    7\n"
    )
    assert mod.parse_collection_list_output(raw) == [
        "oms-cognee-brief",
        "livekit-extraction",
        "memory-root-1",
    ]


def test_parse_collection_list_legacy_bare_names():
    """Older qmd printed one bare name per line — still supported."""
    raw = "foo-brief\nbar-extraction\nmemory-root-1\n"
    assert mod.parse_collection_list_output(raw) == [
        "foo-brief",
        "bar-extraction",
        "memory-root-1",
    ]


def test_parse_collection_list_empty():
    assert mod.parse_collection_list_output("") == []
    assert mod.parse_collection_list_output("Collections (0):\n\n") == []


def test_parse_collection_list_empty_state_message():
    """The empty-state message must not be parsed as a collection named 'No'."""
    raw = "No collections found. Run 'qmd collection add .' to create one.\n"
    assert mod.parse_collection_list_output(raw) == []


def test_parse_collection_list_name_resembling_header_not_skipped():
    """A collection named `Collections-*` must not be mistaken for the header."""
    raw = (
        "Collections (1):\n"
        "\n"
        "Collections-brief (qmd://Collections-brief/)\n"
        "  Files:    1\n"
    )
    assert mod.parse_collection_list_output(raw) == ["Collections-brief"]


def test_parse_collection_list_feeds_classify_correctly():
    """End-to-end: modern stdout → parse → classify yields real classifications,
    not an all-foreign no-op."""
    raw = (
        "Collections (2):\n"
        "\n"
        "foo-brief (qmd://foo-brief/)\n"
        "  Files:    3\n"
        "\n"
        "lost-extraction (qmd://lost-extraction/)\n"
        "  Files:    9\n"
    )
    live = mod.parse_collection_list_output(raw)
    out = mod.classify(live, ["foo-brief"])
    assert out["healthy"] == ["foo-brief"]
    assert out["orphaned"] == ["lost-extraction"]
    assert out["foreign_filtered_count"] == 0


# ─── fetch_live_names_from_qmd (executable resolution) ──────────────────────


def test_fetch_qmd_missing_from_path_errors_without_spawning(monkeypatch):
    """shutil.which → None must short-circuit with an accurate message —
    no subprocess spawn, no misattribution to a daemon error."""
    monkeypatch.setattr(shutil, "which", lambda name: None)

    def forbid_spawn(*args, **kwargs):
        raise AssertionError("subprocess.run must not be called when qmd is absent")

    monkeypatch.setattr(subprocess, "run", forbid_spawn)
    names, error = mod.fetch_live_names_from_qmd()
    assert names == []
    assert "qmd" in error and "PATH" in error


def test_fetch_passes_resolved_path_to_subprocess(monkeypatch):
    """Regression for WinError 2: qmd ships from npm as a .CMD shim on
    Windows, so subprocess.run must receive the shutil.which-resolved path."""
    resolved = str(Path("fake-bin") / "qmd.CMD")
    monkeypatch.setattr(shutil, "which", lambda name: resolved)

    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv

        class Result:
            returncode = 0
            stdout = "foo-brief\nbar-extraction\n"
            stderr = ""

        return Result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    names, error = mod.fetch_live_names_from_qmd()
    assert error is None
    assert names == ["foo-brief", "bar-extraction"]
    assert captured["argv"] == [resolved, "collection", "list"]


def test_fetch_passes_utf8_decode_to_subprocess(monkeypatch):
    """qmd emits UTF-8; without encoding= Windows decodes stdout as cp1252 —
    non-ASCII names mojibake and unmapped bytes raise UnicodeDecodeError."""
    resolved = str(Path("fake-bin") / "qmd.CMD")
    monkeypatch.setattr(shutil, "which", lambda name: resolved)

    captured = {}

    def fake_run(argv, **kwargs):
        captured["kwargs"] = kwargs

        class Result:
            returncode = 0
            stdout = "café-brief\n"
            stderr = ""

        return Result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    names, error = mod.fetch_live_names_from_qmd()
    assert error is None
    assert names == ["café-brief"]
    assert captured["kwargs"].get("encoding") == "utf-8"
    assert captured["kwargs"].get("errors") == "replace"


def test_fetch_rejects_cwd_planted_shim_without_spawning(monkeypatch):
    """shutil.which on Windows searches CWD ahead of PATH — a repo-planted
    qmd.CMD must read as absent and never spawn."""
    planted = os.path.join(os.getcwd(), "qmd.CMD")
    monkeypatch.setattr(shutil, "which", lambda name: planted)

    def forbid_spawn(*args, **kwargs):
        raise AssertionError("subprocess.run must not execute a CWD-planted shim")

    monkeypatch.setattr(subprocess, "run", forbid_spawn)
    names, error = mod.fetch_live_names_from_qmd()
    assert names == []
    assert error is not None


def test_fetch_accepts_which_result_outside_cwd(tmp_path, monkeypatch):
    """A which() hit in a real (non-CWD) PATH directory is still executed."""
    resolved = str(tmp_path / "qmd.CMD")
    monkeypatch.setattr(shutil, "which", lambda name: resolved)

    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv

        class Result:
            returncode = 0
            stdout = "foo-brief\n"
            stderr = ""

        return Result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    names, error = mod.fetch_live_names_from_qmd()
    assert error is None
    assert names == ["foo-brief"]
    assert captured["argv"][0] == resolved


# ─── load_registry_names ─────────────────────────────────────────────────────


@pytest.fixture
def tmp_yaml():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td) / "forge-tier.yaml"


def test_load_registry_missing_file_returns_empty(tmp_yaml):
    assert mod.load_registry_names(tmp_yaml) == []


def test_load_registry_extracts_names_from_qmd_collections(tmp_yaml):
    tmp_yaml.write_text(
        "qmd_collections:\n"
        "  - name: foo-brief\n"
        "    type: brief\n"
        "  - name: foo-extraction\n"
        "    type: extraction\n",
        encoding="utf-8",
    )
    assert mod.load_registry_names(tmp_yaml) == ["foo-brief", "foo-extraction"]


def test_load_registry_skips_entries_without_name(tmp_yaml):
    tmp_yaml.write_text(
        "qmd_collections:\n"
        "  - name: foo-brief\n"
        "  - type: extraction\n"  # no name
        "  - name: bar-docs\n",
        encoding="utf-8",
    )
    assert mod.load_registry_names(tmp_yaml) == ["foo-brief", "bar-docs"]


def test_load_registry_empty_array(tmp_yaml):
    tmp_yaml.write_text("qmd_collections: []\n", encoding="utf-8")
    assert mod.load_registry_names(tmp_yaml) == []


def test_load_registry_missing_array_key(tmp_yaml):
    tmp_yaml.write_text("tier: Deep\n", encoding="utf-8")
    assert mod.load_registry_names(tmp_yaml) == []


def test_load_registry_malformed_yaml_dies(tmp_yaml):
    tmp_yaml.write_text("qmd_collections: [unclosed\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        mod.load_registry_names(tmp_yaml)
    assert exc.value.code == 1


def test_load_registry_non_list_dies(tmp_yaml):
    tmp_yaml.write_text("qmd_collections: 42\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        mod.load_registry_names(tmp_yaml)
    assert exc.value.code == 1


# ─── classify() — the core set arithmetic ────────────────────────────────────


def test_classify_first_run_no_collections():
    """Empty live, empty registry — everything is empty."""
    out = mod.classify([], [])
    assert out == {
        "live_names": [],
        "healthy": [],
        "orphaned": [],
        "orphaned_paths": {},
        "stale": [],
        "foreign_filtered_count": 0,
        "foreign_filtered_sample": [],
    }


def test_classify_returns_live_names_sorted_unique():
    """live_names mirrors the input (sorted, deduplicated) so downstream callers don't re-fetch."""
    out = mod.classify(["foo-brief", "memory-root-1", "foo-brief"], [])
    assert out["live_names"] == ["foo-brief", "memory-root-1"]


def test_classify_all_healthy():
    live = ["foo-brief", "foo-extraction"]
    registry = ["foo-brief", "foo-extraction"]
    out = mod.classify(live, registry)
    assert out["healthy"] == ["foo-brief", "foo-extraction"]
    assert out["orphaned"] == []
    assert out["stale"] == []


def test_classify_orphan_in_qmd_only():
    """Live collection with forge suffix but not in registry → orphaned."""
    live = ["foo-brief", "lost-extraction"]
    registry = ["foo-brief"]
    out = mod.classify(live, registry)
    assert out["healthy"] == ["foo-brief"]
    assert out["orphaned"] == ["lost-extraction"]
    assert out["stale"] == []


def test_classify_stale_in_registry_only():
    """Registry entry not in QMD → stale."""
    live = ["foo-brief"]
    registry = ["foo-brief", "deleted-temporal"]
    out = mod.classify(live, registry)
    assert out["healthy"] == ["foo-brief"]
    assert out["orphaned"] == []
    assert out["stale"] == ["deleted-temporal"]


def test_classify_foreign_silently_excluded():
    """Live collections without forge suffix are foreign — never displayed."""
    live = ["foo-brief", "memory-root-1", "sessions-2", "bar-extraction"]
    registry = ["foo-brief", "bar-extraction"]
    out = mod.classify(live, registry)
    assert out["healthy"] == ["bar-extraction", "foo-brief"]
    assert out["orphaned"] == []
    assert out["stale"] == []
    assert out["foreign_filtered_count"] == 2
    assert out["foreign_filtered_sample"] == ["memory-root-1", "sessions-2"]


def test_classify_pr244_incident_reproduction():
    """The exact data-loss footgun PR #244 closed, in test form.

    User runs setup for the first time on a host that has 48 Hindsight
    memory-bank collections in QMD. Registry is empty. Without the
    forge-namespace filter, all 48 Hindsight collections would have
    been classified as orphaned and offered for removal. With the
    filter, they are silently excluded and never enter the orphan
    classification.
    """
    hindsight = [f"{prefix}-{i}" for prefix in
                 ("memory-root", "memory-alt", "memory-dir", "sessions") for i in range(12)]
    assert len(hindsight) == 48

    out = mod.classify(hindsight, [])
    assert out["orphaned"] == [], "PR #244 regression — Hindsight banks would be deleted"
    assert out["stale"] == []
    assert out["foreign_filtered_count"] == 48
    assert len(out["foreign_filtered_sample"]) == mod.FOREIGN_SAMPLE_CAP  # capped


def test_classify_mixed_realistic_scenario():
    """A real-world Deep host with some forge skills + some foreign collections + drift."""
    live = [
        # Forge-managed, in registry — healthy
        "lib1-brief", "lib1-extraction", "lib2-brief",
        # Forge-managed, NOT in registry — orphaned (manual ccc test maybe)
        "experimental-extraction",
        # Foreign collections from other tools — silently excluded
        "memory-root-1", "memory-alt-2",
    ]
    registry = [
        "lib1-brief", "lib1-extraction", "lib2-brief",
        "deleted-skill-extraction",  # was deleted from QMD — stale
    ]
    out = mod.classify(live, registry)
    assert out["healthy"] == ["lib1-brief", "lib1-extraction", "lib2-brief"]
    assert out["orphaned"] == ["experimental-extraction"]
    assert out["stale"] == ["deleted-skill-extraction"]
    assert out["foreign_filtered_count"] == 2


def test_classify_results_are_sorted_for_determinism():
    """Same input — byte-identical output. Set ops are unordered; sorted() makes them stable."""
    live = ["zoo-brief", "alpha-brief", "mid-extraction"]
    registry = ["zoo-brief", "alpha-brief", "mid-extraction"]
    out = mod.classify(live, registry)
    assert out["healthy"] == ["alpha-brief", "mid-extraction", "zoo-brief"]


def test_classify_foreign_sample_capped_but_count_accurate():
    live = [f"foreign-{i}" for i in range(20)]  # all foreign (no forge suffix)
    out = mod.classify(live, [])
    assert out["foreign_filtered_count"] == 20
    assert len(out["foreign_filtered_sample"]) == mod.FOREIGN_SAMPLE_CAP


def test_classify_registry_entries_with_non_forge_names_still_classified():
    """Hand-edited registry could contain a non-forge name — still tracked correctly."""
    live = ["foo-brief"]  # no foreign-name in live
    registry = ["foo-brief", "weird-no-suffix"]  # registry has a non-forge name
    out = mod.classify(live, registry)
    # weird-no-suffix is not in live, so it's stale (registry−live).
    assert "weird-no-suffix" in out["stale"]


# ─── Collection paths: whose orphan is it? ──────────────────────────────────


def test_is_inside_takes_the_root_and_folders_below_it(tmp_path):
    root = tmp_path / "project"
    (root / "forge-data" / "lib").mkdir(parents=True)
    assert mod.is_inside(str(root), root)
    assert mod.is_inside(str(root / "forge-data" / "lib"), root)
    # A path that is not there yet still resolves below the root.
    assert mod.is_inside(str(root / "skills" / "lib" / "1.0.0"), root)
    assert not mod.is_inside(str(tmp_path / "project-other" / "forge-data"), root)
    assert not mod.is_inside(str(tmp_path), root)
    assert not mod.is_inside(None, root)
    assert not mod.is_inside("", root)


def test_is_inside_follows_a_symlinked_root(tmp_path):
    real = tmp_path / "real"
    (real / "forge-data").mkdir(parents=True)
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available here")
    assert mod.is_inside(str(real / "forge-data"), link)
    assert mod.is_inside(str(link / "forge-data"), real)


def test_parse_collection_path_reads_the_path_line():
    raw = ("Collection: lib-brief\n"
           "  Path:     /home/u/proj/forge-data/lib\n"
           "  Pattern:  skill-brief.yaml\n"
           "  Include:  yes (default)\n")
    assert mod.parse_collection_path(raw) == "/home/u/proj/forge-data/lib"
    assert mod.parse_collection_path("Collection not found: x\n") is None
    assert mod.parse_collection_path("") is None


def test_classify_with_a_project_root_keeps_other_projects_collections_out(tmp_path):
    """The wave-1 re-check defect: QMD's index is shared by every project on
    the machine, so a suffix-matched name another project registered is no
    orphan of this one, and must never reach the removal gate."""
    here, there = tmp_path / "here", tmp_path / "there"
    paths = {
        "mine-extraction": str(here / "skills" / "mine" / "1.0.0" / "mine"),
        "theirs-brief": str(there / "forge-data" / "theirs"),
        "theirs-temporal": str(there / "_bmad-output" / "theirs-temporal"),
        "unshown-docs": None,
    }
    live = ["lib-brief", *paths, "memory-root-1"]
    out = mod.classify(live, ["lib-brief"], here, paths)
    assert out["healthy"] == ["lib-brief"]
    assert out["orphaned"] == ["mine-extraction"]
    assert out["orphaned_paths"] == {"mine-extraction": paths["mine-extraction"]}
    assert out["foreign_filtered_count"] == 4
    assert set(out["foreign_filtered_sample"]) == {"memory-root-1", "theirs-brief", "theirs-temporal",
                                                   "unshown-docs"}


def _fake_qmd(collections: dict, removed: list, refuse=()):
    """A stand-in for _run_qmd over `collections` ({name: Path}); remove deletes from it."""
    def run(*args):
        if args[:2] == ("collection", "list"):
            return 0, "".join(f"{n} (qmd://{n}/)\n" for n in collections), ""
        if args[:2] == ("collection", "show"):
            name = args[2]
            if name not in collections:
                return 1, "", f"Collection not found: {name}"
            return 0, f"Collection: {name}\n  Path:     {collections[name]}\n", ""
        if args[:2] == ("collection", "remove"):
            name = args[2]
            if name in refuse:
                return 1, "", "database is locked"
            removed.append(name)
            collections.pop(name, None)
            return 0, "", ""
        raise AssertionError(f"unexpected qmd call {args}")
    return run


def test_two_projects_registry_and_live_collections_classify_by_path(tmp_path, monkeypatch, capsys):
    """One project's registry, and live collections rooted in another project:
    nothing is offered for removal, and the other project's names count as foreign."""
    project_a, project_b = tmp_path / "a", tmp_path / "b"
    registry = tmp_path / "forge-tier.yaml"
    registry.write_text("qmd_collections:\n  - name: a-lib-brief\n", encoding="utf-8")
    collections = {
        "a-lib-brief": str(project_a / "forge-data" / "a-lib"),
        "b-lib-brief": str(project_b / "forge-data" / "b-lib"),
        "b-lib-extraction": str(project_b / "skills" / "b-lib" / "2.0.0" / "b-lib"),
        "b-lib-temporal": str(project_b / "_bmad-output" / "b-lib-temporal"),
    }
    monkeypatch.setattr(mod, "_run_qmd", _fake_qmd(collections, []))
    monkeypatch.setattr(sys, "argv", ["classify", "classify", "--registry-from-yaml", str(registry),
                                      "--project-root", str(project_a)])
    mod.main()
    out = json.loads(capsys.readouterr().out)
    assert out["healthy"] == ["a-lib-brief"]
    assert out["orphaned"] == [] and out["orphaned_paths"] == {}
    assert out["foreign_filtered_count"] == 3
    # Seen from project b, its own collections outside a registry are its orphans.
    monkeypatch.setattr(sys, "argv", ["classify", "classify", "--registry-from-yaml", str(registry),
                                      "--project-root", str(project_b)])
    mod.main()
    out = json.loads(capsys.readouterr().out)
    assert out["orphaned"] == ["b-lib-brief", "b-lib-extraction", "b-lib-temporal"]
    assert out["foreign_filtered_count"] == 0


def test_remove_orphans_checks_each_path_again_before_it_removes(tmp_path, monkeypatch):
    root = tmp_path / "project"
    collections = {
        "gone-brief": str(root / "forge-data" / "gone"),
        "moved-docs": str(tmp_path / "other" / "_bmad-output" / "moved-docs"),
        "locked-extraction": str(root / "skills" / "locked"),
    }
    removed: list[str] = []
    monkeypatch.setattr(mod, "_run_qmd", _fake_qmd(collections, removed, refuse=("locked-extraction",)))
    out = mod.remove_orphans(["gone-brief", "moved-docs", "locked-extraction", "vanished-temporal"], root)
    assert out["removed"] == ["gone-brief"] and removed == ["gone-brief"]
    assert out["failed"] == ["moved-docs", "locked-extraction", "vanished-temporal"]
    assert out["errors"]["moved-docs"] == "its Path no longer lies inside the project root"
    assert out["errors"]["locked-extraction"] == "qmd collection remove exited 1: database is locked"
    assert out["errors"]["vanished-temporal"].startswith("qmd collection show exited 1")


def test_remove_orphans_without_qmd_removes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    out = mod.remove_orphans(["x-brief"], tmp_path)
    assert out == {"removed": [], "failed": ["x-brief"], "errors": {"x-brief": "qmd not found on PATH"}}


# ─── End-to-end CLI subprocess tests ────────────────────────────────────────


def _run(*args) -> tuple[int, dict, str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True, text=True, timeout=10,
    )
    payload = json.loads(result.stdout) if result.stdout else None
    return result.returncode, payload, result.stderr


def _classify(registry: Path, live: str, root: Path | None = None) -> tuple[int, dict, str]:
    return _run("classify", "--live-names", live, "--registry-from-yaml", str(registry),
                "--project-root", str(root or registry.parent))


def test_cli_first_run_state(tmp_yaml):
    """No live collections, no registry file → emit empty everything."""
    rc, payload, stderr = _classify(tmp_yaml, "")
    assert rc == 0, f"stderr: {stderr}"
    assert payload["status"] == "ok"
    assert payload["version"] == "v1"
    assert payload["healthy"] == []
    assert payload["orphaned"] == []
    assert payload["stale"] == []


def test_cli_realistic_deep_host(tmp_yaml):
    tmp_yaml.write_text(
        "qmd_collections:\n"
        "  - name: lib1-brief\n"
        "    type: brief\n"
        "  - name: lib1-extraction\n"
        "    type: extraction\n",
        encoding="utf-8",
    )
    rc, payload, _ = _classify(tmp_yaml, "lib1-brief,lib1-extraction,memory-root-1")
    assert rc == 0
    assert payload["healthy"] == ["lib1-brief", "lib1-extraction"]
    assert payload["orphaned"] == []
    assert payload["stale"] == []
    assert payload["foreign_filtered_count"] == 1


def test_cli_pr244_incident(tmp_yaml):
    """End-to-end repro of the PR #244 incident."""
    # Empty registry, 4 Hindsight foreign collections in live
    rc, payload, _ = _classify(tmp_yaml, "memory-root-1,memory-alt-2,memory-dir-3,sessions-4")
    assert rc == 0
    assert payload["orphaned"] == []
    assert payload["foreign_filtered_count"] == 4


@pytest.mark.parametrize("args", [
    ["classify", "--live-names", "foo-brief", "--project-root", "."],
    ["classify", "--live-names", "foo-brief", "--registry-from-yaml", "x.yaml"],
    ["--live-names", "foo-brief", "--registry-from-yaml", "x.yaml"],
    ["remove-orphans", "--classification-from", "x.json"],
], ids=["no-registry", "no-project-root", "no-subcommand", "remove-no-project-root"])
def test_cli_missing_required_arg(args):
    """--registry-from-yaml and --project-root are required, and so is the subcommand."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0


def test_cli_malformed_registry_emits_error(tmp_yaml):
    tmp_yaml.write_text("qmd_collections: [unclosed\n", encoding="utf-8")
    rc, _, stderr = _classify(tmp_yaml, "")
    assert rc == 1
    err = json.loads(stderr)
    assert "failed to parse" in err["message"]


@pytest.mark.parametrize("content", ["", "not json", '{"orphaned": "x-brief"}', '["x-brief"]'],
                         ids=["empty", "not-json", "not-a-list", "not-an-object"])
def test_cli_remove_orphans_refuses_a_classification_without_an_orphan_list(tmp_path, content):
    staged = tmp_path / "qmd-classify.json"
    staged.write_text(content, encoding="utf-8")
    rc, _, stderr = _run("remove-orphans", "--classification-from", str(staged), "--project-root", str(tmp_path))
    assert rc == 1
    assert "remove-orphans:" in json.loads(stderr)["message"]


def test_cli_remove_orphans_with_no_orphans_removes_nothing(tmp_path):
    staged = tmp_path / "qmd-classify.json"
    staged.write_text(json.dumps({"status": "ok", "orphaned": []}), encoding="utf-8")
    rc, payload, stderr = _run("remove-orphans", "--classification-from", str(staged),
                               "--project-root", str(tmp_path))
    assert rc == 0, stderr
    assert payload == {"status": "ok", "version": "v1", "removed": [], "failed": [], "errors": {}}
