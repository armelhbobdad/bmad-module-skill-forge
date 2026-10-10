#!/usr/bin/env python3
"""Tests for skf-compare-file-hashes.py.

Covers:
  - compare: added (new file in source tree, not in provenance),
             removed (provenance row, file missing on disk),
             changed (hash mismatch),
             unchanged (hash match, counted only)
  - hash-prefix normalization: bare-hex stored vs sha256: stored both
    correctly equal a freshly computed prefixed hash
  - inverse walk: respects SCRIPT_DIRS / ASSET_DIRS / DOC_DIR_PREFIXES;
    prunes EXCLUDED_DIR_NAMES; skips binary extensions; ignores files
    outside the tracked directory taxonomy; leaves a Python package's
    modules out (the detector's is_package_module, #696)
  - added with --brief only (#696): the brief's scope (the shared
    load_scope), its intents and the map's entries[] keep `added` to new
    scripts, assets and docs; without a brief it can read, `added` is
    empty and `added_not_checked` says why, while removed and changed are
    compared as before
  - load_file_entries: accepts both top-level object and bare-array shapes;
    missing `file_entries` key returns []; malformed JSON raises
  - CLI smoke: shape conformance + exit codes
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-compare-file-hashes.py"

spec = importlib.util.spec_from_file_location("skf_compare_file_hashes", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _bare_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    return path


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _brief(path: Path, include=None, exclude=None, language: str = "Python", **intents) -> Path:
    """A skill brief: its scope's patterns as YAML double-quoted strings, then any intent fields."""
    lines = ["name: demo", f"language: {language}", "scope:", "  type: public-api"]
    for key, patterns in (("include", include), ("exclude", exclude)):
        if patterns is None:
            continue
        lines.append(f"  {key}:" + ("" if patterns else " []"))
        lines += [f"  - {json.dumps(pattern)}" for pattern in patterns]
    lines += [f"{field}: {value}" for field, value in intents.items()]
    return _write(path, "\n".join(lines) + "\n")


EVERYTHING = ["**"]  # a brief that takes every path


# --------------------------------------------------------------------------
# normalize_hash
# --------------------------------------------------------------------------


class TestNormalizeHash:
    def test_strips_sha256_prefix(self) -> None:
        assert mod.normalize_hash("sha256:abcdef") == "abcdef"

    def test_idempotent_on_bare_hex(self) -> None:
        # no leading lowercase-alphanumeric prefix-with-colon → unchanged
        assert mod.normalize_hash("abcdef1234567890") == "abcdef1234567890"

    def test_strips_alt_algorithm_prefix(self) -> None:
        assert mod.normalize_hash("sha1:cafebabe") == "cafebabe"
        assert mod.normalize_hash("md5:deadbeef") == "deadbeef"

    def test_none_input_returns_none(self) -> None:
        assert mod.normalize_hash(None) is None

    def test_non_string_returns_none(self) -> None:
        assert mod.normalize_hash(42) is None


# --------------------------------------------------------------------------
# load_file_entries
# --------------------------------------------------------------------------


class TestLoadFileEntries:
    def test_object_with_file_entries(self, tmp_path: Path) -> None:
        prov = _write_json(
            tmp_path / "p.json",
            {"file_entries": [{"source_file": "scripts/a.sh", "content_hash": "sha256:x"}]},
        )
        entries = mod.load_file_entries(prov)
        assert entries == [{"source_file": "scripts/a.sh", "content_hash": "sha256:x"}]

    def test_object_without_file_entries_returns_empty(self, tmp_path: Path) -> None:
        # A single-skill with no scripts/assets/docs may omit the field per
        # skill-sections.md — should not raise.
        prov = _write_json(tmp_path / "p.json", {"entries": []})
        assert mod.load_file_entries(prov) == []

    def test_bare_array(self, tmp_path: Path) -> None:
        prov = _write_json(tmp_path / "p.json", [{"source_file": "x.md"}])
        assert mod.load_file_entries(prov) == [{"source_file": "x.md"}]

    def test_file_entries_not_array_raises(self, tmp_path: Path) -> None:
        prov = _write_json(tmp_path / "p.json", {"file_entries": "nope"})
        import pytest

        with pytest.raises(ValueError, match="not an array"):
            mod.load_file_entries(prov)

    def test_malformed_json_raises(self, tmp_path: Path) -> None:
        prov = tmp_path / "p.json"
        prov.write_text("{not json", encoding="utf-8")
        import pytest

        with pytest.raises(ValueError, match="malformed JSON"):
            mod.load_file_entries(prov)


# --------------------------------------------------------------------------
# candidate_source_files (inverse walk)
# --------------------------------------------------------------------------


class TestCandidateSourceFiles:
    def test_finds_scripts_dir(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "scripts" / "build.sh", "echo")
        _write(source / "scripts" / "deploy.py", "print('x')")
        assert sorted(mod.candidate_source_files(source)) == [
            "scripts/build.sh",
            "scripts/deploy.py",
        ]

    def test_finds_assets_dir(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "assets" / "template.md", "...")
        _write(source / "schemas" / "config.json", "{}")
        assert sorted(mod.candidate_source_files(source)) == [
            "assets/template.md",
            "schemas/config.json",
        ]

    def test_finds_doc_prefix(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "docs" / "authoritative" / "llms.txt", "...")
        assert list(mod.candidate_source_files(source)) == [
            "docs/authoritative/llms.txt"
        ]

    def test_skips_non_tracked_directories(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "src" / "main.ts", "...")  # not tracked
        _write(source / "lib" / "util.py", "...")  # not tracked
        _write(source / "scripts" / "ok.sh", "...")
        assert list(mod.candidate_source_files(source)) == ["scripts/ok.sh"]

    def test_prunes_excluded_dirs(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "scripts" / "real.sh", "...")
        _write(source / "node_modules" / "scripts" / "fake.sh", "...")
        _write(source / "dist" / "scripts" / "fake2.sh", "...")
        _write(source / "__pycache__" / "scripts" / "fake3.sh", "...")
        assert list(mod.candidate_source_files(source)) == ["scripts/real.sh"]

    def test_skips_binary_extensions(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "assets" / "logo.png", "")
        _write(source / "assets" / "doc.md", "")
        assert list(mod.candidate_source_files(source)) == ["assets/doc.md"]

    def test_handles_nested_tracked_dirs(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "packages" / "core" / "scripts" / "build.sh", "...")
        # Any depth — segment-match anywhere in path qualifies
        assert list(mod.candidate_source_files(source)) == [
            "packages/core/scripts/build.sh"
        ]

    def test_a_python_package_s_modules_are_code(self, tmp_path: Path) -> None:
        # #696: the detector's package rule; only a module that runs on its own stays
        source = tmp_path / "src"
        for name, text in {"__init__.py": "", "helper.py": "X = 1\n", "__main__.py": "run()\n",
                           "runme.py": "def main():\n    pass\n\n\nif __name__ == '__main__':\n    main()\n",
                           "run2.py": "#!/usr/bin/env python3\nprint('run')\n"}.items():
            _write(source / "pkg" / "tools" / name, text)
        assert sorted(mod.candidate_source_files(source)) == [
            "pkg/tools/__main__.py", "pkg/tools/run2.py", "pkg/tools/runme.py"]

    def test_a_package_module_an_asset_folder_holds_is_an_asset(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "pkg" / "cli" / "__init__.py", "")
        _write(source / "pkg" / "cli" / "templates" / "page.py", "X = 1\n")
        _write(source / "pkg" / "cli" / "templates" / "__init__.py", "")
        assert sorted(mod._walk(source)) == [("pkg/cli/templates/__init__.py", "asset"),
                                             ("pkg/cli/templates/page.py", "asset")]

    def test_each_walked_file_has_a_kind(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        for rel in ("scripts/a.sh", "scripts/templates/b.sh", "assets/c.json", "docs/authoritative/llms.txt"):
            _write(source / rel, "x")
        assert sorted(mod._walk(source)) == [
            ("assets/c.json", "asset"), ("docs/authoritative/llms.txt", "doc"),
            ("scripts/a.sh", "script"), ("scripts/templates/b.sh", "script")]


# --------------------------------------------------------------------------
# compare end-to-end
# --------------------------------------------------------------------------


class TestCompare:
    def test_mixed_added_removed_changed_unchanged(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        # unchanged: tracked, file present, hash matches
        _write(source / "scripts" / "a.sh", "unchanged\n")
        # changed: tracked, file present, hash differs
        _write(source / "scripts" / "b.sh", "new content\n")
        # added: present on disk, NOT in provenance — must be in a tracked dir
        _write(source / "scripts" / "c.sh", "brand new\n")
        # removed: in provenance but not on disk → no file written for d.sh

        prov = _write_json(
            tmp_path / "p.json",
            {
                "file_entries": [
                    {
                        "source_file": "scripts/a.sh",
                        "content_hash": _sha256(b"unchanged\n"),
                    },
                    {
                        "source_file": "scripts/b.sh",
                        "content_hash": "sha256:stalehashvalue",
                    },
                    {
                        "source_file": "scripts/d.sh",
                        "content_hash": "sha256:was-here",
                    },
                ]
            },
        )
        result = mod.compare(source, prov, _brief(tmp_path / "skill-brief.yaml", include=EVERYTHING))
        assert result["stats"] == {"added": 1, "removed": 1, "changed": 1, "unchanged": 1}
        assert result["added"] == ["scripts/c.sh"] and result["added_not_checked"] is None
        assert result["removed"] == ["scripts/d.sh"]
        assert len(result["changed"]) == 1
        assert result["changed"][0]["path"] == "scripts/b.sh"
        assert result["changed"][0]["stored_hash"] == "sha256:stalehashvalue"
        assert result["changed"][0]["current_hash"] == _sha256(b"new content\n")

    def test_unchanged_with_bare_hex_stored_hash(self, tmp_path: Path) -> None:
        # Writer-vs-reader hash-prefix story: stored hash without sha256:
        # prefix must still compare equal to a freshly computed prefixed hash.
        source = tmp_path / "src"
        _write(source / "scripts" / "a.sh", "content\n")
        prov = _write_json(
            tmp_path / "p.json",
            {"file_entries": [
                {"source_file": "scripts/a.sh", "content_hash": _bare_hex(b"content\n")},
            ]},
        )
        result = mod.compare(source, prov)
        assert result["stats"] == {"added": 0, "removed": 0, "changed": 0, "unchanged": 1}

    def test_empty_provenance_returns_empty_added_if_no_candidates(
        self, tmp_path: Path
    ) -> None:
        source = tmp_path / "src"
        source.mkdir()
        prov = _write_json(tmp_path / "p.json", {"file_entries": []})
        result = mod.compare(source, prov, _brief(tmp_path / "skill-brief.yaml", include=EVERYTHING))
        assert result == {
            "added": [],
            "added_not_checked": None,
            "removed": [],
            "changed": [],
            "stats": {"added": 0, "removed": 0, "changed": 0, "unchanged": 0},
        }

    def test_empty_provenance_with_disk_candidates_yields_added(
        self, tmp_path: Path
    ) -> None:
        source = tmp_path / "src"
        _write(source / "scripts" / "new.sh", "...")
        prov = _write_json(tmp_path / "p.json", {"file_entries": []})
        result = mod.compare(source, prov, _brief(tmp_path / "skill-brief.yaml", include=EVERYTHING))
        assert result["added"] == ["scripts/new.sh"]
        assert result["stats"]["added"] == 1

    def test_provenance_missing_file_entries_field_ok(self, tmp_path: Path) -> None:
        # provenance with no scripts/assets/docs may omit field entirely;
        # candidate walk still produces added[] from disk
        source = tmp_path / "src"
        _write(source / "scripts" / "x.sh", "...")
        prov = _write_json(tmp_path / "p.json", {"entries": []})
        result = mod.compare(source, prov, _brief(tmp_path / "skill-brief.yaml", include=EVERYTHING))
        assert result["added"] == ["scripts/x.sh"]

    def test_paths_are_posix_form(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        # nested dirs to make sure path normalization happens
        _write(source / "packages" / "core" / "scripts" / "build.sh", "x\n")
        prov = _write_json(tmp_path / "p.json", {"file_entries": []})
        result = mod.compare(source, prov, _brief(tmp_path / "skill-brief.yaml", include=EVERYTHING))
        assert result["added"] == ["packages/core/scripts/build.sh"]
        for p in result["added"] + result["removed"]:
            assert "\\" not in p

    def test_provenance_entry_path_backslash_normalized(self, tmp_path: Path) -> None:
        # If a provenance entry was written with backslash separators
        # (legacy Windows writer), we should still find it on disk.
        source = tmp_path / "src"
        _write(source / "scripts" / "a.sh", "x\n")
        prov = _write_json(
            tmp_path / "p.json",
            {"file_entries": [
                {"source_file": "scripts\\a.sh", "content_hash": _sha256(b"x\n")},
            ]},
        )
        result = mod.compare(source, prov)
        assert result["stats"]["unchanged"] == 1


# --------------------------------------------------------------------------
# added: the brief's scope, its intents and the map's entries[] (#696)
# --------------------------------------------------------------------------


class TestBriefScope:
    def _compare(self, tmp_path: Path, files, *, entries=(), file_entries=(), **brief) -> dict:
        source = tmp_path / "src"
        source.mkdir(exist_ok=True)
        for rel in files:
            _write(source / rel, "x\n")
        prov = _write_json(tmp_path / "p.json", {
            "entries": [{"export_name": f"e{i}", "source_file": f} for i, f in enumerate(entries)],
            "file_entries": [{"source_file": f, "content_hash": _sha256(b"x\n")} for f in file_entries]})
        return mod.compare(source, prov, _brief(tmp_path / "skill-brief.yaml", **brief))

    def test_a_path_out_of_scope_is_not_added(self, tmp_path: Path) -> None:
        result = self._compare(tmp_path, ["tools/release.sh", "pkg/scripts/run.sh"], include=["**"],
                               exclude=["tools/**"])
        assert result["added"] == ["pkg/scripts/run.sh"] and result["stats"]["added"] == 1

    def test_the_brief_s_globs_not_fnmatch(self, tmp_path: Path) -> None:
        result = self._compare(tmp_path, ["install/scripts/a.sh", "scripts/a.sh", "scripts/sub/b.sh"],
                               include=["scripts/*"])
        assert result["added"] == ["scripts/a.sh"]  # `*` never crosses a `/`

    def test_an_intent_of_none_drops_its_kind(self, tmp_path: Path) -> None:
        files = ["scripts/a.sh", "assets/x.json", "docs/authoritative/llms.txt"]
        assert self._compare(tmp_path, files, include=["**"], scripts_intent="none")["added"] == [
            "assets/x.json", "docs/authoritative/llms.txt"]
        # no intent filters a document
        assert self._compare(tmp_path, files, include=["**"], scripts_intent="none",
                             assets_intent="none")["added"] == ["docs/authoritative/llms.txt"]
        # a free-text intent detects
        assert self._compare(tmp_path, files, include=["**"], scripts_intent="'the release helpers'")["added"] == [
            "assets/x.json", "docs/authoritative/llms.txt", "scripts/a.sh"]

    def test_code_the_map_cites_is_not_added(self, tmp_path: Path) -> None:
        result = self._compare(tmp_path, ["cli/index.ts", "cli/other.ts"], include=["cli/**"],
                               entries=["./cli/index.ts"])
        assert result["added"] == ["cli/other.ts"]

    def test_a_tracked_file_is_never_added(self, tmp_path: Path) -> None:
        result = self._compare(tmp_path, ["scripts/a.sh", "scripts/b.sh"], include=["**"],
                               file_entries=["./scripts/a.sh"])
        assert result["added"] == ["scripts/b.sh"]

    def test_an_empty_include_takes_the_cited_and_language_extensions(self, tmp_path: Path) -> None:
        files = ["scripts/gen.py", "scripts/run.sh", "scripts/x.rb"]
        assert self._compare(tmp_path, files, include=[], language="Python")["added"] == ["scripts/gen.py"]
        assert self._compare(tmp_path, files, include=[], language="Python", entries=["lib/m.sh"])["added"] == [
            "scripts/gen.py", "scripts/run.sh"]

    def test_package_modules_are_not_added(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        for name, text in {"__init__.py": "", "helper.py": "X = 1\n", "__main__.py": "run()\n",
                           "runme.py": "if __name__ == '__main__':\n    pass\n",
                           "run2.py": "#!/usr/bin/env python3\n"}.items():
            _write(source / "pkg" / "tools" / name, text)
        result = self._compare(tmp_path, [], include=["pkg/**"])
        assert result["added"] == ["pkg/tools/__main__.py", "pkg/tools/run2.py", "pkg/tools/runme.py"]

    def test_removed_and_changed_are_compared_whatever_the_brief(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "scripts" / "b.sh", "new\n")
        _write(source / "scripts" / "c.sh", "new\n")
        prov = _write_json(tmp_path / "p.json", {"file_entries": [
            {"source_file": "scripts/b.sh", "content_hash": "sha256:stale"},
            {"source_file": "scripts/gone.sh", "content_hash": "sha256:x"}]})
        bad = _write(tmp_path / "bad.yaml", "scope: [unclosed\n")
        runs = [mod.compare(source, prov, brief) for brief in
                (None, bad, tmp_path / "nope.yaml", _brief(tmp_path / "skill-brief.yaml", include=EVERYTHING))]
        for result in runs:
            assert result["removed"] == ["scripts/gone.sh"]
            assert [c["path"] for c in result["changed"]] == ["scripts/b.sh"]
            assert (result["stats"]["removed"], result["stats"]["changed"]) == (1, 1)
        assert [r["added"] for r in runs] == [[], [], [], ["scripts/c.sh"]]


class TestNotChecked:
    def test_no_brief(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "scripts" / "new.sh", "...")
        prov = _write_json(tmp_path / "p.json", {"file_entries": []})
        result = mod.compare(source, prov)
        assert (result["added"], result["added_not_checked"]) == ([], "no skill brief")
        assert result["stats"]["added"] == 0

    def test_no_brief_loads_no_sibling(self, tmp_path: Path, monkeypatch) -> None:
        # siblings load lazily: without --brief neither the classifier nor the detector is loaded
        monkeypatch.setattr(mod, "_SIBLINGS", {})
        source = tmp_path / "src"
        _write(source / "scripts" / "a.sh", "x")
        _write(source / "pkg" / "tools" / "__init__.py", "")
        mod.compare(source, _write_json(tmp_path / "p.json", {}))
        assert mod._SIBLINGS == {}

    @pytest.mark.parametrize("case", ["missing", "not-yaml", "not-a-mapping"])
    def test_a_brief_it_cannot_read(self, tmp_path: Path, case: str) -> None:
        source = tmp_path / "src"
        _write(source / "scripts" / "new.sh", "...")
        prov = _write_json(tmp_path / "p.json", {"file_entries": []})
        brief = tmp_path / "skill-brief.yaml"
        if case == "not-yaml":
            _write(brief, "scope: [unclosed\n")
        elif case == "not-a-mapping":
            _write(brief, "- a\n")
        result = _run_cli("compare", str(prov), str(source), "--brief", str(brief))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["added"] == [] and payload["stats"]["added"] == 0
        reason = payload["added_not_checked"]
        needle = {"missing": "brief not found", "not-yaml": "not valid YAML",
                  "not-a-mapping": "must be a YAML mapping"}[case]
        assert needle in reason and "\n" not in reason, reason

    def _alone(self, tmp_path: Path, siblings: dict) -> Path:
        """This script copied alone into a folder, with the given siblings (file name: text, or None for the
        repository's copy) beside it."""
        alone = tmp_path / "alone"
        alone.mkdir()
        (alone / SCRIPT_PATH.name).write_bytes(SCRIPT_PATH.read_bytes())
        for name, text in siblings.items():
            data = (SCRIPT_PATH.parent / name).read_bytes() if text is None else text.encode("utf-8")
            (alone / name).write_bytes(data)
        return alone / SCRIPT_PATH.name

    def _tracked(self, tmp_path: Path) -> tuple[Path, Path]:
        source = tmp_path / "src"
        _write(source / "scripts" / "new.sh", "...")
        _write(source / "scripts" / "b.sh", "new\n")
        prov = _write_json(tmp_path / "p.json", {"file_entries": [
            {"source_file": "scripts/b.sh", "content_hash": "sha256:stale"},
            {"source_file": "scripts/gone.sh", "content_hash": "sha256:x"}]})
        return source, prov

    def test_copied_alone_without_brief(self, tmp_path: Path) -> None:
        # removed and changed need no helper: the script alone compares them
        source, prov = self._tracked(tmp_path)
        script = self._alone(tmp_path, {})
        result = subprocess.run([sys.executable, str(script), "compare", str(prov), str(source)],
                                capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert (payload["added"], payload["added_not_checked"]) == ([], "no skill brief")
        assert payload["removed"] == ["scripts/gone.sh"] and [c["path"] for c in payload["changed"]] == ["scripts/b.sh"]

    @pytest.mark.parametrize("siblings, missing", [
        ({}, "skf-classify-changed-files.py"),
        ({"skf-classify-changed-files.py": "X = 1\n"}, "skf-classify-changed-files.py"),
        ({"skf-classify-changed-files.py": None, "skf-resolve-authoritative-files.py": None},
         "skf-detect-scripts-assets.py"),
    ], ids=["no-classifier", "classifier-without-load-scope", "no-detector"])
    def test_a_helper_it_cannot_load_keeps_the_comparison(self, tmp_path: Path, siblings: dict,
                                                          missing: str) -> None:
        source, prov = self._tracked(tmp_path)
        brief = _brief(tmp_path / "skill-brief.yaml", include=EVERYTHING)
        script = self._alone(tmp_path, siblings)
        result = subprocess.run([sys.executable, str(script), "compare", str(prov), str(source), "--brief",
                                 str(brief)], capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
        assert "Traceback" not in result.stderr
        payload = json.loads(result.stdout)
        reason = payload["added_not_checked"]
        assert payload["added"] == [] and payload["stats"]["added"] == 0
        assert reason.startswith(f"cannot load {missing} beside skf-compare-file-hashes.py: ") and "\n" not in reason
        assert reason.endswith("re-install SKF"), reason
        assert payload["removed"] == ["scripts/gone.sh"] and [c["path"] for c in payload["changed"]] == ["scripts/b.sh"]

    @pytest.mark.parametrize("value", ["", "  "], ids=["empty", "blank"])
    def test_an_empty_brief_is_no_brief(self, tmp_path: Path, value: str) -> None:
        source = tmp_path / "src"
        _write(source / "scripts" / "new.sh", "...")
        prov = _write_json(tmp_path / "p.json", {"file_entries": []})
        result = _run_cli("compare", str(prov), str(source), "--brief", value)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["added_not_checked"] == "no skill brief"


# --------------------------------------------------------------------------
# CLI integration
# --------------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


class TestCli:
    def test_compare_emits_json_shape(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "scripts" / "a.sh", "x\n")
        prov = _write_json(
            tmp_path / "p.json",
            {"file_entries": [
                {"source_file": "scripts/a.sh", "content_hash": _sha256(b"x\n")},
            ]},
        )
        result = _run_cli("compare", str(prov), str(source))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert set(payload.keys()) == {"added", "added_not_checked", "removed", "changed", "stats"}
        assert set(payload["stats"].keys()) == {"added", "removed", "changed", "unchanged"}
        assert payload["stats"]["unchanged"] == 1

    def test_compare_missing_provenance_exits_1(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        source.mkdir()
        result = _run_cli("compare", str(tmp_path / "missing.json"), str(source))
        assert result.returncode == 1
        assert "provenance map" in result.stderr

    def test_compare_missing_source_exits_1(self, tmp_path: Path) -> None:
        prov = _write_json(tmp_path / "p.json", {"file_entries": []})
        result = _run_cli("compare", str(prov), str(tmp_path / "missing"))
        assert result.returncode == 1
        assert "source root" in result.stderr

    def test_compare_malformed_provenance_exits_1(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        source.mkdir()
        prov = tmp_path / "p.json"
        prov.write_text("{not json", encoding="utf-8")
        result = _run_cli("compare", str(prov), str(source))
        assert result.returncode == 1
        assert "malformed JSON" in result.stderr

    def test_compare_with_brief(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        _write(source / "scripts" / "a.sh", "x\n")
        _write(source / "tools" / "b.sh", "x\n")
        prov = _write_json(tmp_path / "p.json", {"file_entries": []})
        brief = _brief(tmp_path / "skill-brief.yaml", include=["scripts/**"])
        result = _run_cli("compare", str(prov), str(source), "--brief", str(brief))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert (payload["added"], payload["added_not_checked"]) == (["scripts/a.sh"], None)


class TestScriptPEP723:
    """--brief loads skf-classify-changed-files.py, whose resolver reads the brief with PyYAML: under `uv run`
    the header must declare it."""

    def test_pyyaml_dependency(self) -> None:
        text = SCRIPT_PATH.read_text(encoding="utf-8")
        header = text[: text.index("# ///", text.index("# /// script") + 1)]
        assert '# requires-python = ">=3.11"' in header and 'dependencies = ["pyyaml"]' in header
