#!/usr/bin/env python3
"""Tests for skf-validate-frontmatter.py.

Aligned with agentskills.io canonical validation rules from
agentskills/agentskills/skills-ref/src/skills_ref/validator.py.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "skf_fm",
    Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-validate-frontmatter.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
validate_frontmatter = mod.validate_frontmatter
parse_frontmatter = mod.parse_frontmatter


VALID_SKILL_MD = """\
---
name: my-skill
description: A valid skill description.
---

# My Skill
"""

VALID_WITH_OPTIONAL = """\
---
name: my-skill
description: A valid skill.
license: MIT
compatibility: '>=1.0'
allowed-tools: tool-a, tool-b
---

# My Skill
"""

VALID_WITH_METADATA = """\
---
name: my-skill
description: A valid skill.
metadata:
  category: utilities
  author: test
---

# My Skill
"""


class TestValidFrontmatter:
    def test_pass_status(self):
        r = validate_frontmatter(VALID_SKILL_MD, "my-skill")
        assert r["status"] == "pass"

    def test_zero_issues(self):
        r = validate_frontmatter(VALID_SKILL_MD, "my-skill")
        assert r["summary"]["total"] == 0

    def test_frontmatter_parsed(self):
        r = validate_frontmatter(VALID_SKILL_MD, "my-skill")
        assert r["frontmatter"]["name"] == "my-skill"
        assert r["frontmatter"]["description"] == "A valid skill description."

    def test_optional_fields_pass(self):
        r = validate_frontmatter(VALID_WITH_OPTIONAL, "my-skill")
        assert r["status"] == "pass"

    def test_nested_metadata_parsed(self):
        r = validate_frontmatter(VALID_WITH_METADATA, "my-skill")
        assert r["status"] == "pass"
        assert r["frontmatter"]["metadata"] == {"category": "utilities", "author": "test"}


class TestYamlParsing:
    def test_multi_line_description(self):
        content = "---\nname: my-skill\ndescription: >\n  A long description\n  that spans lines.\n---\n"
        r = validate_frontmatter(content, "my-skill")
        assert r["status"] == "pass"
        assert "long description" in r["frontmatter"]["description"]

    def test_invalid_yaml(self):
        content = "---\nname: [invalid\n---\n"
        r = validate_frontmatter(content, "my-skill")
        assert r["status"] == "fail"
        assert any("Invalid YAML" in i["message"] for i in r["issues"])

    def test_non_mapping_frontmatter(self):
        content = "---\n- item1\n- item2\n---\n"
        r = validate_frontmatter(content, "my-skill")
        assert r["status"] == "fail"
        assert any("mapping" in i["message"] for i in r["issues"])

    def test_empty_frontmatter_block(self):
        content = "---\n---\n# Content\n"
        r = validate_frontmatter(content, "my-skill")
        assert r["status"] == "fail"
        assert any(i["field"] == "name" for i in r["issues"])


class TestMissingDelimiters:
    def test_no_opening_delimiter(self):
        r = validate_frontmatter("name: foo\n---\n", "foo")
        assert r["status"] == "fail"
        assert r["frontmatter"] is None

    def test_no_closing_delimiter(self):
        r = validate_frontmatter("---\nname: foo\n", "foo")
        assert r["status"] == "fail"
        assert any("closing" in i["message"] for i in r["issues"])


class TestNameValidation:
    def test_missing_name(self):
        content = "---\ndescription: hello\n---\n"
        r = validate_frontmatter(content, "my-skill")
        assert r["status"] == "fail"
        assert any(i["field"] == "name" for i in r["issues"])

    def test_uppercase_name(self):
        content = "---\nname: MySkill\ndescription: hello\n---\n"
        r = validate_frontmatter(content, "MySkill")
        assert r["status"] == "fail"
        assert any("lowercase" in i["message"] for i in r["issues"])

    def test_name_too_long(self):
        long_name = "a" * 65
        content = f"---\nname: {long_name}\ndescription: hello\n---\n"
        r = validate_frontmatter(content, long_name)
        assert r["status"] == "fail"
        assert any("exceeds" in i["message"] for i in r["issues"])

    def test_name_with_underscore(self):
        content = "---\nname: my_skill\ndescription: hello\n---\n"
        r = validate_frontmatter(content, "my_skill")
        assert r["status"] == "fail"
        assert any("invalid characters" in i["message"] for i in r["issues"])

    def test_name_starting_with_hyphen(self):
        content = "---\nname: -bad\ndescription: hello\n---\n"
        r = validate_frontmatter(content, "-bad")
        assert r["status"] == "fail"
        assert any("start or end with a hyphen" in i["message"] for i in r["issues"])

    def test_name_ending_with_hyphen(self):
        content = "---\nname: bad-\ndescription: hello\n---\n"
        r = validate_frontmatter(content, "bad-")
        assert r["status"] == "fail"
        assert any("start or end with a hyphen" in i["message"] for i in r["issues"])

    def test_consecutive_hyphens(self):
        content = "---\nname: my--skill\ndescription: hello\n---\n"
        r = validate_frontmatter(content, "my--skill")
        assert r["status"] == "fail"
        assert any("consecutive hyphens" in i["message"] for i in r["issues"])

    def test_name_directory_mismatch(self):
        r = validate_frontmatter(VALID_SKILL_MD, "different-name")
        assert r["status"] == "fail"
        assert any("does not match" in i["message"] for i in r["issues"])

    def test_name_directory_match_skipped_when_none(self):
        r = validate_frontmatter(VALID_SKILL_MD, None)
        assert r["status"] == "pass"

    def test_single_char_name(self):
        content = "---\nname: a\ndescription: hello\n---\n"
        r = validate_frontmatter(content, "a")
        assert r["status"] == "pass"

    def test_ascii_hyphenated_name(self):
        content = "---\nname: mon-outil\ndescription: hello\n---\n"
        r = validate_frontmatter(content, "mon-outil")
        assert r["status"] == "pass"

    def test_unicode_letter_name(self):
        """Unicode alphanumerics are accepted per canonical spec (isalnum())."""
        content = "---\nname: café-tool\ndescription: hello\n---\n"
        r = validate_frontmatter(content, "café-tool")
        # café contains lowercase Unicode letters — isalnum() returns True
        # but the canonical spec requires lowercase, and café is already lowercase
        assert r["status"] == "pass"

    def test_name_is_yaml_integer(self):
        """YAML parses bare `42` as int, not string — must fail."""
        content = "---\nname: 42\ndescription: hello\n---\n"
        r = validate_frontmatter(content, "42")
        assert r["status"] == "fail"
        assert any(i["field"] == "name" for i in r["issues"])


class TestDescriptionValidation:
    def test_missing_description(self):
        content = "---\nname: my-skill\n---\n"
        r = validate_frontmatter(content, "my-skill")
        assert r["status"] == "fail"
        assert any(i["field"] == "description" for i in r["issues"])

    def test_description_too_long(self):
        long_desc = "a" * 1025
        content = f"---\nname: my-skill\ndescription: {long_desc}\n---\n"
        r = validate_frontmatter(content, "my-skill")
        assert r["status"] == "warn"
        assert any("exceeds" in i["message"] for i in r["issues"])

    def test_description_is_yaml_integer(self):
        """YAML parses bare `42` as int, not string — must fail."""
        content = "---\nname: my-skill\ndescription: 42\n---\n"
        r = validate_frontmatter(content, "my-skill")
        assert r["status"] == "fail"
        assert any(i["field"] == "description" for i in r["issues"])


class TestCompatibilityValidation:
    def test_valid_compatibility(self):
        r = validate_frontmatter(VALID_WITH_OPTIONAL, "my-skill")
        assert r["status"] == "pass"

    def test_compatibility_too_long(self):
        long_compat = "a" * 501
        content = f"---\nname: my-skill\ndescription: hello\ncompatibility: {long_compat}\n---\n"
        r = validate_frontmatter(content, "my-skill")
        assert r["status"] == "warn"
        assert any("compatibility" in i["field"] for i in r["issues"])


class TestUnknownFields:
    def test_unknown_field_low_severity(self):
        content = "---\nname: my-skill\ndescription: hello\nauthor: someone\n---\n"
        r = validate_frontmatter(content, "my-skill")
        assert r["status"] == "warn"
        assert any(i["field"] == "author" and i["severity"] == "low" for i in r["issues"])

    def test_multiple_unknown_fields(self):
        content = "---\nname: my-skill\ndescription: hello\nauthor: someone\nversion: '1.0'\n---\n"
        r = validate_frontmatter(content, "my-skill")
        unknown = [i for i in r["issues"] if i["severity"] == "low"]
        assert len(unknown) == 2


class TestSummary:
    def test_severity_counts(self):
        content = "---\nname: INVALID\ndescription: hello\nauthor: extra\n---\n"
        r = validate_frontmatter(content, "INVALID")
        assert r["summary"]["high"] >= 1
        assert r["summary"]["low"] >= 1
        assert r["summary"]["total"] == r["summary"]["high"] + r["summary"]["medium"] + r["summary"]["low"]


class TestEdgeCases:
    def test_empty_content(self):
        r = validate_frontmatter("", "my-skill")
        assert r["status"] == "fail"

    def test_max_length_name(self):
        name = "a" * 64
        content = f"---\nname: {name}\ndescription: hello\n---\n"
        r = validate_frontmatter(content, name)
        assert r["status"] == "pass"

    def test_max_length_description(self):
        desc = "a" * 1024
        content = f"---\nname: my-skill\ndescription: {desc}\n---\n"
        r = validate_frontmatter(content, "my-skill")
        assert r["status"] == "pass"
