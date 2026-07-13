#!/usr/bin/env python3
"""Tests for skf-verify-no-trace.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-verify-no-trace.py"

spec = importlib.util.spec_from_file_location("skf_verify_no_trace", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

OLD = "rename"
NEW = "rename-skill"


def build_tree(tmp_path, version, skill_md, metadata, snippet, provenance, inner_name=NEW):
    """Materialize a new_skill_group + new_forge_group for one version."""
    skill_group = tmp_path / "out" / NEW
    forge_group = tmp_path / "forge" / NEW
    inner = skill_group / version / inner_name
    inner.mkdir(parents=True)
    (inner / "SKILL.md").write_text(skill_md)
    (inner / "metadata.json").write_text(metadata)
    (inner / "context-snippet.md").write_text(snippet)
    fv = forge_group / version
    fv.mkdir(parents=True)
    (fv / "provenance-map.json").write_text(provenance)
    return skill_group, forge_group


CLEAN_SKILL_MD = (
    "---\nname: rename-skill\ndescription: x\n---\n"
    "# rename-skill\nHistorically this was the rename workflow.\n"
)
CLEAN_METADATA = json.dumps({"name": NEW, "version": "1.0.0"}, indent=2) + "\n"
CLEAN_SNIPPET = "[rename-skill v1.0.0]|root: .claude/skills/rename-skill/\n"
CLEAN_PROV = json.dumps({"skill_name": NEW}, indent=2) + "\n"


class TestVerify:
    def test_clean_tree(self, tmp_path):
        sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, CLEAN_METADATA, CLEAN_SNIPPET, CLEAN_PROV)
        r = mod.verify(sg, fg, OLD, NEW, ["1.0.0"])
        assert r["clean"] is True
        assert r["hard_matches"] == []
        # Body mention of "rename" is advisory only.
        assert len(r["body_warnings"]) == 1
        assert r["body_warnings"][0]["region"] == "skill-body"
        assert r["dir_violations"] == []

    def test_new_name_substring_not_flagged(self, tmp_path):
        # OLD ("rename") is a substring of NEW ("rename-skill"); the correctly
        # renamed occurrences must NOT be hard matches.
        sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, CLEAN_METADATA, CLEAN_SNIPPET, CLEAN_PROV)
        r = mod.verify(sg, fg, OLD, NEW, ["1.0.0"])
        assert r["hard_matches"] == []

    def test_english_word_not_hard(self, tmp_path):
        # "renamed" in the body is a different word, not a name token.
        body_md = "---\nname: rename-skill\ndescription: x\n---\n# rename-skill\nrenamed elsewhere\n"
        sg, fg = build_tree(tmp_path, "1.0.0", body_md, CLEAN_METADATA, CLEAN_SNIPPET, CLEAN_PROV)
        r = mod.verify(sg, fg, OLD, NEW, ["1.0.0"])
        assert r["clean"] is True
        assert r["body_warnings"] == []

    def test_frontmatter_leak_is_hard(self, tmp_path):
        bad = "---\nname: rename\ndescription: x\n---\n# body\n"
        sg, fg = build_tree(tmp_path, "1.0.0", bad, CLEAN_METADATA, CLEAN_SNIPPET, CLEAN_PROV)
        r = mod.verify(sg, fg, OLD, NEW, ["1.0.0"])
        assert r["clean"] is False
        regions = [m["region"] for m in r["hard_matches"]]
        assert "skill-frontmatter" in regions

    def test_metadata_leak_is_hard(self, tmp_path):
        bad_meta = json.dumps({"name": "rename", "version": "1.0.0"}, indent=2) + "\n"
        sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, bad_meta, CLEAN_SNIPPET, CLEAN_PROV)
        r = mod.verify(sg, fg, OLD, NEW, ["1.0.0"])
        assert r["clean"] is False
        assert any(m["region"] == "metadata-json" for m in r["hard_matches"])

    def test_snippet_leak_is_hard(self, tmp_path):
        bad_snip = "[rename v1.0.0]|root: .claude/skills/rename/\n"
        sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, CLEAN_METADATA, bad_snip, CLEAN_PROV)
        r = mod.verify(sg, fg, OLD, NEW, ["1.0.0"])
        assert r["clean"] is False
        assert any(m["region"] == "context-snippet" for m in r["hard_matches"])

    def test_provenance_leak_is_hard(self, tmp_path):
        bad_prov = json.dumps({"skill_name": "rename"}, indent=2) + "\n"
        sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, CLEAN_METADATA, CLEAN_SNIPPET, bad_prov)
        r = mod.verify(sg, fg, OLD, NEW, ["1.0.0"])
        assert r["clean"] is False
        assert any(m["region"] == "provenance-json" for m in r["hard_matches"])

    def test_old_name_dir_present_is_violation(self, tmp_path):
        sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, CLEAN_METADATA, CLEAN_SNIPPET, CLEAN_PROV)
        # Leave an old-name inner dir behind (unrenamed).
        (sg / "1.0.0" / OLD).mkdir()
        r = mod.verify(sg, fg, OLD, NEW, ["1.0.0"])
        assert r["clean"] is False
        assert any(dv["issue"] == "old-name-dir-present" for dv in r["dir_violations"])

    def test_new_name_dir_missing_is_violation(self, tmp_path):
        sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, CLEAN_METADATA, CLEAN_SNIPPET, CLEAN_PROV, inner_name=OLD)
        r = mod.verify(sg, fg, OLD, NEW, ["1.0.0"])
        assert r["clean"] is False
        assert any(dv["issue"] == "new-name-dir-missing" for dv in r["dir_violations"])

    def test_missing_provenance_is_skipped_not_hard(self, tmp_path):
        sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, CLEAN_METADATA, CLEAN_SNIPPET, CLEAN_PROV)
        (fg / "1.0.0" / "provenance-map.json").unlink()
        r = mod.verify(sg, fg, OLD, NEW, ["1.0.0"])
        assert r["clean"] is True
        assert any(s["reason"] == "missing" for s in r["skipped"])

    def test_multiple_versions(self, tmp_path):
        sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, CLEAN_METADATA, CLEAN_SNIPPET, CLEAN_PROV)
        # Add a second version with a leak.
        inner = sg / "0.9.0" / NEW
        inner.mkdir(parents=True)
        (inner / "SKILL.md").write_text(CLEAN_SKILL_MD)
        (inner / "metadata.json").write_text(json.dumps({"name": "rename"}, indent=2))
        (inner / "context-snippet.md").write_text(CLEAN_SNIPPET)
        (fg / "0.9.0").mkdir(parents=True)
        (fg / "0.9.0" / "provenance-map.json").write_text(CLEAN_PROV)
        r = mod.verify(sg, fg, OLD, NEW, ["1.0.0", "0.9.0"])
        assert r["clean"] is False
        assert any(m["version"] == "0.9.0" for m in r["hard_matches"])


class TestCli:
    def _run(self, sg, fg, versions):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(sg), "--forge-group", str(fg),
             "--old-name", OLD, "--new-name", NEW, "--versions", versions],
            capture_output=True, text=True,
        )
        return proc.returncode, json.loads(proc.stdout)

    def test_clean_exit_0(self, tmp_path):
        sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, CLEAN_METADATA, CLEAN_SNIPPET, CLEAN_PROV)
        rc, out = self._run(sg, fg, "1.0.0")
        assert rc == 0
        assert out["clean"] is True

    def test_leak_exit_1(self, tmp_path):
        bad_meta = json.dumps({"name": "rename"}, indent=2)
        sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, bad_meta, CLEAN_SNIPPET, CLEAN_PROV)
        rc, out = self._run(sg, fg, "1.0.0")
        assert rc == 1
        assert out["clean"] is False
