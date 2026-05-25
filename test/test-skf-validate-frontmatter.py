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


def _skill_md_with_body(n_body_lines: int) -> str:
    """Build a valid SKILL.md whose body is exactly `n_body_lines` lines."""
    body = "\n".join(["x"] * n_body_lines) + "\n"
    return f"---\nname: my-skill\ndescription: hello\n---\n{body}"


class TestBodyLineCount:
    def test_body_lines_present_in_output(self):
        """body_lines is an additive output field (backward-compatible)."""
        r = validate_frontmatter(VALID_SKILL_MD, "my-skill")
        assert "body_lines" in r
        assert isinstance(r["body_lines"], int)

    def test_body_lines_exact_count(self):
        r = validate_frontmatter(_skill_md_with_body(5), "my-skill")
        assert r["body_lines"] == 5

    def test_body_lines_none_without_closing_delimiter(self):
        r = validate_frontmatter("---\nname: foo\n", "foo")
        assert r["body_lines"] is None

    def test_body_lines_none_without_opening_delimiter(self):
        r = validate_frontmatter("name: foo\n---\nbody\n", "foo")
        assert r["body_lines"] is None

    def test_body_lines_handles_crlf(self):
        content = "---\r\nname: my-skill\r\ndescription: hello\r\n---\r\nx\r\ny\r\n"
        r = validate_frontmatter(content, "my-skill")
        assert r["body_lines"] == 2


class TestBodyMaxLinesGate:
    def test_no_check_when_flag_unset(self):
        """Opt-in: an oversized body is ignored when max_body_lines is None,
        so the other validator consumers are unaffected."""
        r = validate_frontmatter(_skill_md_with_body(600), "my-skill")
        assert r["status"] == "pass"
        assert not any(i["field"] == "body" for i in r["issues"])

    def test_exceeds_max_emits_high_body_issue(self):
        r = validate_frontmatter(_skill_md_with_body(501), "my-skill", max_body_lines=500)
        assert r["status"] == "fail"
        body_issues = [i for i in r["issues"] if i["field"] == "body"]
        assert len(body_issues) == 1
        assert body_issues[0]["severity"] == "high"
        assert "exceeds max 500" in body_issues[0]["message"]

    def test_at_limit_passes(self):
        """Strict `>`: a body exactly at the limit does not trip the gate."""
        r = validate_frontmatter(_skill_md_with_body(500), "my-skill", max_body_lines=500)
        assert r["status"] == "pass"
        assert not any(i["field"] == "body" for i in r["issues"])

    def test_under_limit_passes(self):
        r = validate_frontmatter(_skill_md_with_body(10), "my-skill", max_body_lines=500)
        assert r["status"] == "pass"
        assert not any(i["field"] == "body" for i in r["issues"])

    def test_undefined_body_does_not_trip_gate(self):
        """No closing delimiter → body_lines None → no body issue (the
        missing-delimiter error is reported by frontmatter parsing instead)."""
        r = validate_frontmatter("---\nname: foo\n", "foo", max_body_lines=500)
        assert not any(i["field"] == "body" for i in r["issues"])


def _skill_md_with_dense_body(n_chars: int) -> str:
    """Build a valid SKILL.md whose body is short in lines but dense in chars."""
    body = "x" * n_chars + "\n"
    return f"---\nname: my-skill\ndescription: hello\n---\n{body}"


class TestBodyTokenEstimate:
    def test_body_tokens_present_in_output(self):
        """body_tokens is an additive output field (backward-compatible)."""
        r = validate_frontmatter(VALID_SKILL_MD, "my-skill")
        assert "body_tokens" in r
        assert isinstance(r["body_tokens"], int)

    def test_body_tokens_calculation(self):
        """Token estimate = ceil(char_count / 4)."""
        content = _skill_md_with_dense_body(100)
        r = validate_frontmatter(content, "my-skill")
        assert r["body_tokens"] == 25  # ceil(100/4) — 100 x-chars

    def test_body_tokens_none_without_closing_delimiter(self):
        r = validate_frontmatter("---\nname: foo\n", "foo")
        assert r["body_tokens"] is None

    def test_body_tokens_none_without_opening_delimiter(self):
        r = validate_frontmatter("name: foo\n---\nbody\n", "foo")
        assert r["body_tokens"] is None


class TestBodyMaxTokensGate:
    def test_no_check_when_flag_unset(self):
        """Opt-in: an over-token body is ignored when max_body_tokens is None."""
        r = validate_frontmatter(_skill_md_with_dense_body(25000), "my-skill")
        assert r["status"] == "pass"
        assert not any(i["field"] == "body" for i in r["issues"])

    def test_exceeds_max_emits_high_body_issue(self):
        content = _skill_md_with_dense_body(20100)  # ceil(20101/4) = 5026 > 5000
        r = validate_frontmatter(content, "my-skill", max_body_tokens=5000)
        assert r["status"] == "fail"
        body_issues = [i for i in r["issues"] if i["field"] == "body"]
        assert len(body_issues) == 1
        assert body_issues[0]["severity"] == "high"
        assert "token estimate" in body_issues[0]["message"]
        assert "exceeds max 5000" in body_issues[0]["message"]

    def test_at_limit_passes(self):
        """Strict `>`: a body exactly at the limit does not trip the gate."""
        content = _skill_md_with_dense_body(19999)  # ceil(20000/4) = 5000 == 5000
        r = validate_frontmatter(content, "my-skill", max_body_tokens=5000)
        assert not any(i["field"] == "body" for i in r["issues"])

    def test_under_limit_passes(self):
        content = _skill_md_with_dense_body(100)  # 26 tokens
        r = validate_frontmatter(content, "my-skill", max_body_tokens=5000)
        assert r["status"] == "pass"
        assert not any(i["field"] == "body" for i in r["issues"])

    def test_undefined_body_does_not_trip_token_gate(self):
        """No closing delimiter → body_tokens None → no body issue."""
        r = validate_frontmatter("---\nname: foo\n", "foo", max_body_tokens=5000)
        assert not any(i["field"] == "body" for i in r["issues"])

    def test_dense_body_under_line_limit_but_over_token_limit(self):
        """The exact scenario from fp-b842e0e: under 500 lines but over 5000 tokens."""
        lines = ["x" * 120] * 200
        body = "\n".join(lines) + "\n"
        content = f"---\nname: my-skill\ndescription: hello\n---\n{body}"
        r = validate_frontmatter(content, "my-skill", max_body_lines=500, max_body_tokens=5000)
        assert r["body_lines"] == 200  # under 500 line limit
        assert r["body_tokens"] > 5000  # over token limit
        body_issues = [i for i in r["issues"] if i["field"] == "body"]
        assert len(body_issues) == 1  # only token issue fires, not line
        assert "token estimate" in body_issues[0]["message"]
