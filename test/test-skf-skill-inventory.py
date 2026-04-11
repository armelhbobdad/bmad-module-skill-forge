#!/usr/bin/env python3
"""Tests for skf-skill-inventory.py."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import importlib.util
import pytest

spec = importlib.util.spec_from_file_location(
    "skf_skill_inventory",
    Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-skill-inventory.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
scan_inventory = mod.scan_inventory


def make_skill(skills_dir, name, version="1.0.0", with_metadata=True, with_provenance=False):
    """Create a mock skill with versioned directory structure."""
    skill_group = skills_dir / name
    version_dir = skill_group / version / name
    version_dir.mkdir(parents=True, exist_ok=True)

    # Write SKILL.md
    (version_dir / "SKILL.md").write_text(f"---\nname: {name}\n---\n# {name}\n")

    if with_metadata:
        meta = {
            "name": name,
            "version": version,
            "language": "TypeScript",
            "source_authority": "community",
            "source_repo": f"https://github.com/test/{name}",
            "generated_by": "create-skill",
            "confidence_tier": "Forge",
            "stats": {"exports_total": 10},
        }
        (version_dir / "metadata.json").write_text(json.dumps(meta))

    if with_provenance:
        (version_dir / "provenance-map.json").write_text("{}")

    # Create active symlink
    active_link = skill_group / "active"
    if active_link.exists() or active_link.is_symlink():
        active_link.unlink()
    active_link.symlink_to(version)

    return skill_group


class TestSkfSkillInventory:
    """Tests for the skf-skill-inventory scan_inventory function."""

    @pytest.fixture()
    def skills_dir(self):
        """Provide a temporary skills directory."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "skills"
            d.mkdir()
            yield d

    def test_empty_directory(self, skills_dir):
        result = scan_inventory(str(skills_dir))
        assert result["status"] == "ok"
        assert result["summary"]["total_skills"] == 0

    def test_single_versioned_skill(self, skills_dir):
        make_skill(skills_dir, "cocoindex", "2.1.0", with_provenance=True)
        result = scan_inventory(str(skills_dir))
        assert result["status"] == "ok"
        assert result["summary"]["total_skills"] == 1
        s = result["skills"][0]
        assert s["name"] == "cocoindex"
        assert s["active_version"] == "2.1.0"
        assert s["has_skill_md"] is True
        assert s["has_provenance_map"] is True
        assert s["metadata"]["language"] == "TypeScript"
        assert s["metadata"]["exports_total"] == 10

    def test_multiple_skills(self, skills_dir):
        make_skill(skills_dir, "react", "18.0.0")
        make_skill(skills_dir, "vue", "3.0.0")
        make_skill(skills_dir, "svelte", "4.0.0", with_metadata=False)
        result = scan_inventory(str(skills_dir))
        assert result["summary"]["total_skills"] == 3
        assert result["summary"]["with_metadata"] == 2

    def test_filter_by_name(self, skills_dir):
        make_skill(skills_dir, "react", "18.0.0")
        make_skill(skills_dir, "vue", "3.0.0")
        result = scan_inventory(str(skills_dir), skill_filter="vue")
        assert result["summary"]["total_skills"] == 1
        assert result["skills"][0]["name"] == "vue"

    def test_filter_nonexistent(self, skills_dir):
        make_skill(skills_dir, "react", "18.0.0")
        result = scan_inventory(str(skills_dir), skill_filter="angular")
        assert result["status"] == "error"
        assert result["code"] == "SKILL_NOT_FOUND"
        assert "react" in result["available"]

    def test_nonexistent_directory(self):
        result = scan_inventory("/tmp/nonexistent-skf-dir-12345")
        assert result["status"] == "error"
        assert result["code"] == "DIR_NOT_FOUND"

    def test_with_export_manifest(self, skills_dir):
        make_skill(skills_dir, "cocoindex", "2.0.0")
        manifest = {"exports": {"cocoindex": {"active_version": "2.0.0"}}}
        (skills_dir / ".export-manifest.json").write_text(json.dumps(manifest))
        result = scan_inventory(str(skills_dir))
        assert result["manifest"] is not None
        assert "cocoindex" in result["manifest"]["exports"]
