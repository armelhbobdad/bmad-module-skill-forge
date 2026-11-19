#!/usr/bin/env python3
"""Tests for the description skf-build-change-manifest.py's `metadata` call writes (#1252).

Update Skill's write step writes metadata.json through the `metadata` call. The call takes the frontmatter
description of the merged SKILL.md (`--skill-md`), read with skf-description-guard.py's read_description as
Create Skill's metadata call reads the staged SKILL.md, so metadata.json never keeps the description of the
version before. A SKILL.md with no readable description refuses the write, and metadata.json stays as it was.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
SCRIPTS = REPO_ROOT / "src" / "shared" / "scripts"
SCRIPT_PATH = SCRIPTS / "skf-build-change-manifest.py"
GUARD_PATH = SCRIPTS / "skf-description-guard.py"
QUICK_METADATA_PATH = SCRIPTS / "skf-render-quick-metadata.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mod = _load(SCRIPT_PATH, "skf_build_change_manifest_description")
guard = _load(GUARD_PATH, "skf_description_guard_description")

LISTS = {"exports": ["search"], "scripts": [], "assets": []}
STATS = {"stats": {"exports_documented": 1, "exports_public_api": 1, "exports_internal": 0, "exports_total": 1,
                   "public_api_coverage": 1.0, "total_coverage": 1.0, "scripts_count": 0, "assets_count": 0},
         "confidence_distribution": {"t1": 1, "t1_low": 0, "t2": 0, "t3": 0}}
# metadata.json as version 2.0.0 left it: its description names that release
METADATA = {"name": "lib", "version": "2.0.0", "description": "Lib, as of its 2.0 release.",
            "scope_type": "full-library", "generation_date": "2026-01-01T00:00:00Z", "exports": ["search"],
            "stats": STATS["stats"], "confidence_distribution": STATS["confidence_distribution"],
            "tool_versions": {"ast_grep": None, "qmd": None, "skf": "4.0.0"}}
NEW = "Lib, as of its 2.1 release."
GENERATION_DATE = "2026-11-19T10:00:00Z"


def _update(metadata: dict, description: str | None) -> dict:
    out, _summary = mod.update_metadata(metadata, LISTS, STATS, version="2.1.0", generation_date=GENERATION_DATE,
                                        skf_version="4.0.0", description=description)
    return out


class TestUpdateMetadata:
    def test_it_sets_the_description_where_metadata_json_holds_it(self):
        out = _update(METADATA, NEW)
        assert out["description"] == NEW and list(out) == list(METADATA)
        assert out == {**METADATA, "version": "2.1.0", "generation_date": GENERATION_DATE, "description": NEW}

    def test_it_appends_a_description_metadata_json_lacks(self):
        old = {key: value for key, value in METADATA.items() if key != "description"}
        out = _update(old, NEW)
        assert list(out) == [*old, "description"] and out["description"] == NEW

    @pytest.mark.parametrize("has_one", [True, False], ids=["held", "absent"])
    def test_none_keeps_what_metadata_json_holds(self, has_one):
        old = METADATA if has_one else {key: value for key, value in METADATA.items() if key != "description"}
        out = _update(old, None)
        assert out.get("description") == old.get("description") and list(out) == list(old)


# --------------------------------------------------------------------------
# The CLI, as write-metadata.md's documented call runs it
# --------------------------------------------------------------------------


def _staged(tmp_path: Path, skill_md: bytes | None) -> tuple[Path, Path]:
    """metadata.json, the lists, the stats and (unless None) the merged SKILL.md a `metadata` call reads."""
    target = tmp_path / "metadata.json"
    target.write_bytes((json.dumps(METADATA, indent=2) + "\n").encode("utf-8"))
    (tmp_path / "lists.json").write_bytes(json.dumps(LISTS).encode("utf-8"))
    (tmp_path / "stats.json").write_bytes(json.dumps(STATS).encode("utf-8"))
    skill = tmp_path / "SKILL.md"
    if skill_md is not None:
        skill.write_bytes(skill_md)
    return target, skill


def _run(tmp_path: Path, skill: Path, script: Path = SCRIPT_PATH, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), "metadata", "--metadata", str(tmp_path / "metadata.json"),
         "--lists", str(tmp_path / "lists.json"), "--stats", str(tmp_path / "stats.json"), "--skill-md", str(skill),
         "--version", "2.1.0", "--generation-date", GENERATION_DATE, *extra],
        capture_output=True, encoding="utf-8", check=False)


SKILL_MD = f"---\nname: lib\ndescription: {NEW}\n---\n\n# lib\n\nThe body.\n"


class TestTheCli:
    @pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["lf", "crlf"])
    def test_it_writes_the_merged_skill_md_description(self, tmp_path, newline):
        target, skill = _staged(tmp_path, SKILL_MD.replace("\n", newline).encode("utf-8"))
        result = _run(tmp_path, skill)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["status"] == "written"
        written = json.loads(target.read_bytes())
        assert written["description"] == NEW and list(written) == list(METADATA)
        assert written["version"] == "2.1.0"

    def test_a_folded_description_is_stored_as_the_guard_reads_it(self, tmp_path):
        # a folded `>` value with a key after it keeps its trailing newline, as create-skill stores it
        target, skill = _staged(tmp_path, b"---\nname: lib\ndescription: >\n  Lib, as of\n  its 2.1 release.\n"
                                          b"version: 2.1.0\n---\n")
        result = _run(tmp_path, skill)
        assert result.returncode == 0, result.stderr
        description, _hash = guard.read_description(skill)
        assert description == NEW + "\n"
        assert json.loads(target.read_bytes())["description"] == description

    @pytest.mark.parametrize("skill_md, needle", [
        (None, "cannot read the description of"),
        (b"# lib\n\nNo frontmatter.\n", "no frontmatter found"),
        (b"---\nname: lib\n---\n", "has no `description` field"),
        (b'---\nname: lib\ndescription: "  "\n---\n', "is empty"),
        # an unquoted `: ` inside the value: a YAML error whose message spans lines
        (b"---\nname: lib\ndescription: Lib: as of its 2.1 release\n---\n", "is not valid YAML"),
    ], ids=["missing", "no-frontmatter", "no-description", "blank", "yaml-error"])
    def test_a_skill_md_with_no_readable_description_writes_nothing(self, tmp_path, skill_md, needle):
        target, skill = _staged(tmp_path, skill_md)
        before = target.read_bytes()
        result = _run(tmp_path, skill)
        assert result.returncode == 1 and result.stdout == ""
        lines = result.stderr.splitlines()
        assert len(lines) == 1 and lines[0].startswith("error: --skill-md: "), result.stderr
        assert needle in lines[0] and skill.as_posix() in lines[0], lines[0]
        assert target.read_bytes() == before
        assert sorted(p.name for p in tmp_path.iterdir() if p.name.startswith(".")) == []

    def test_a_missing_guard_writes_nothing(self, tmp_path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        script = Path(shutil.copy(SCRIPT_PATH, scripts))
        shutil.copy(QUICK_METADATA_PATH, scripts)
        target, skill = _staged(tmp_path, SKILL_MD.encode("utf-8"))
        before = target.read_bytes()
        result = _run(tmp_path, skill, script)
        assert result.returncode == 1 and result.stdout == ""
        lines = result.stderr.splitlines()
        assert len(lines) == 1 and lines[0].startswith(
            "error: cannot load skf-description-guard.py beside skf-build-change-manifest.py"), result.stderr
        assert lines[0].endswith("re-install SKF")
        assert target.read_bytes() == before

    def test_the_skf_root_probe_still_fails_first(self, tmp_path):
        # neither sibling beside the script: the --skf-root probe's error is the one named
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        script = Path(shutil.copy(SCRIPT_PATH, scripts))
        _target, skill = _staged(tmp_path, None)
        result = _run(tmp_path, skill, script, "--skf-root", str(tmp_path))
        assert result.returncode == 1
        assert result.stderr.startswith("error: cannot load skf-render-quick-metadata.py beside "), result.stderr

    def test_the_flag_is_required(self, tmp_path):
        _staged(tmp_path, SKILL_MD.encode("utf-8"))
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "metadata", "--metadata", str(tmp_path / "metadata.json"),
             "--lists", str(tmp_path / "lists.json"), "--stats", str(tmp_path / "stats.json"),
             "--version", "2.1.0", "--generation-date", GENERATION_DATE],
            capture_output=True, encoding="utf-8", check=False)
        assert result.returncode == 2 and "--skill-md" in result.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
