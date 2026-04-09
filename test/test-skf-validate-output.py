#!/usr/bin/env python3
"""Tests for skf-validate-output.py."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import importlib.util
import pytest

spec = importlib.util.spec_from_file_location(
    "skf_validate_output",
    Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-validate-output.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
validate_skill_package = mod.validate_skill_package

VALID_SKILL_MD = """---
name: test-skill
description: A test skill for validation
---

# test-skill

## Overview

Test skill overview with package info.

## Key Exports

- `foo()` — does foo

## Usage Patterns

```js
import { foo } from 'test-skill'
```
"""

VALID_SNIPPET = "[test-skill v1.0.0]|root: skills/test-skill/\n|IMPORTANT: Use this for testing\n|exports: foo, bar\n"

VALID_METADATA = {
    "name": "test-skill",
    "version": "1.0.0",
    "source_authority": "community",
    "source_repo": "https://github.com/test/test-skill",
    "language": "TypeScript",
    "generated_by": "quick-skill",
    "generation_date": "2026-04-08",
    "confidence_tier": "Quick",
    "stats": {
        "exports_documented": 5,
        "exports_public_api": 5,
        "exports_total": 5,
        "public_api_coverage": 1.0,
        "total_coverage": 1.0,
    },
}


def make_valid_package(tmpdir, name="test-skill"):
    pkg = Path(tmpdir) / name
    pkg.mkdir(parents=True)
    (pkg / "SKILL.md").write_text(VALID_SKILL_MD.replace("test-skill", name))
    (pkg / "context-snippet.md").write_text(VALID_SNIPPET.replace("test-skill", name))
    meta = dict(VALID_METADATA)
    meta["name"] = name
    (pkg / "metadata.json").write_text(json.dumps(meta))
    return pkg


class TestSkfValidateOutput:
    """Tests for the skf-validate-output validate_skill_package function."""

    def test_valid_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_valid_package(tmp)
            r = validate_skill_package(str(pkg))
            assert r["result"] == "PASS"
            assert r["summary"]["by_severity"]["high"] == 0
            assert r["files_found"]["SKILL.md"] is True
            assert r["files_found"]["metadata.json"] is True

    def test_missing_skill_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "broken-skill"
            pkg.mkdir()
            (pkg / "metadata.json").write_text(json.dumps(VALID_METADATA))
            r = validate_skill_package(str(pkg))
            assert r["result"] == "FAIL"
            assert r["summary"]["by_severity"]["high"] >= 1

    def test_bad_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "bad-fm"
            pkg.mkdir()
            (pkg / "SKILL.md").write_text("# No frontmatter\n\nJust content.")
            r = validate_skill_package(str(pkg))
            assert r["result"] == "FAIL"

    def test_name_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "real-name"
            pkg.mkdir()
            (pkg / "SKILL.md").write_text("---\nname: wrong-name\ndescription: test\n---\n\n# Wrong\n\n## Overview\n\nTest\n\n## Key Exports\n\nNone\n\n## Usage\n\nNone\n")
            r = validate_skill_package(str(pkg))
            has_mismatch = any(
                "does not match" in i["message"]
                for i in r["validation"]["skill_md"]["frontmatter"]
            )
            assert has_mismatch

    def test_invalid_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_valid_package(tmp, "bad-meta")
            (pkg / "metadata.json").write_text(json.dumps({"name": "bad-meta"}))
            r = validate_skill_package(str(pkg))
            assert r["summary"]["total_issues"] > 0

    def test_generated_by_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_valid_package(tmp)
            r = validate_skill_package(str(pkg), generated_by="create-skill")
            has_gb_issue = any(
                "generated_by" in i.get("field", "")
                for i in r["validation"]["metadata"]["issues"]
            )
            assert has_gb_issue

    def test_trailing_hyphen_rejected(self):
        """Names ending with a hyphen should be rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "bad-name-"
            pkg.mkdir()
            (pkg / "SKILL.md").write_text("---\nname: bad-name-\ndescription: test\n---\n\n## Overview\n\nTest\n\n## Key Exports\n\nNone\n\n## Usage\n\nNone\n")
            (pkg / "metadata.json").write_text(json.dumps(VALID_METADATA))
            r = validate_skill_package(str(pkg))
            fm_issues = r["validation"]["skill_md"]["frontmatter"]
            assert any("must be lowercase" in i["message"] or "alphanumeric" in i["message"] for i in fm_issues), f"Expected name rejection, got: {fm_issues}"

    def test_frontmatter_with_dashes_in_value(self):
        """Frontmatter parser should not be confused by --- in YAML values."""
        content = "---\nname: test-skill\ndescription: A---great library\n---\n\n## Overview\n\nTest\n\n## Key Exports\n\nNone\n\n## Usage\n\nNone\n"
        issues = mod.validate_frontmatter(content, "test-skill")
        # Should parse successfully — no high-severity issues
        high_issues = [i for i in issues if i["severity"] == "high"]
        assert len(high_issues) == 0
