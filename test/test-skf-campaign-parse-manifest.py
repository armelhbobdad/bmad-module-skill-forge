"""Tests for campaign-parse-manifest.py — deterministic --manifest parsing.

Pins the format documented in SKILL.md On Activation: per-line
`name,repo_url,tier,pin[;deps]`, blank/comment skip, all-or-nothing error
reporting with line numbers (never a silent partial target set).
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "src" / "skf-campaign" / "scripts" / "campaign-parse-manifest.py"


def _load():
    spec = importlib.util.spec_from_file_location("campaign_parse_manifest", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()


class TestParse:
    def test_basic(self):
        r = mod.parse_manifest_text("auth,https://github.com/o/auth,A,v1.2.3\n")
        assert r["errors"] == []
        t = r["targets"][0]
        assert t == {"name": "auth", "repo_url": "https://github.com/o/auth", "tier": "A", "pin": "v1.2.3", "depends_on": []}

    def test_pin_omitted_is_null(self):
        r = mod.parse_manifest_text("data,https://github.com/o/data,B\n")
        assert r["targets"][0]["pin"] is None

    def test_empty_pin_field_is_null(self):
        r = mod.parse_manifest_text("data,https://github.com/o/data,B,\n")
        assert r["targets"][0]["pin"] is None

    def test_depends_on_segment(self):
        r = mod.parse_manifest_text("svc,https://github.com/o/svc,A,;auth,data\n")
        assert r["targets"][0]["depends_on"] == ["auth", "data"]

    def test_blank_and_comment_skipped(self):
        text = "# header\n\nauth,https://github.com/o/auth,A\n\n# trailing\n"
        r = mod.parse_manifest_text(text)
        assert len(r["targets"]) == 1
        assert r["errors"] == []

    def test_bad_tier_errors_with_line(self):
        r = mod.parse_manifest_text("auth,https://github.com/o/auth,C\n")
        assert r["targets"] == []
        assert r["errors"][0]["line"] == 1
        assert "tier" in r["errors"][0]["message"]

    def test_too_few_fields(self):
        r = mod.parse_manifest_text("justname\n")
        assert r["errors"][0]["line"] == 1

    def test_empty_repo_url(self):
        r = mod.parse_manifest_text("auth,,A\n")
        assert r["errors"]
        assert "repo_url" in r["errors"][0]["message"]

    def test_duplicate_name(self):
        text = "auth,https://github.com/o/auth,A\nauth,https://github.com/o/auth2,B\n"
        r = mod.parse_manifest_text(text)
        assert len(r["targets"]) == 1
        assert any("duplicate" in e["message"] for e in r["errors"])

    def test_partial_collects_good_and_reports_bad(self):
        text = "good,https://github.com/o/good,A\nbad,https://github.com/o/bad,Z\n"
        r = mod.parse_manifest_text(text)
        assert [t["name"] for t in r["targets"]] == ["good"]
        assert r["errors"][0]["line"] == 2


class TestRun:
    def test_clean_exit_0(self, tmp_path, capsys):
        p = tmp_path / "m.txt"
        p.write_text("auth,https://github.com/o/auth,A,v1\n", encoding="utf-8")
        rc = mod.run(str(p))
        assert rc == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["targets"][0]["name"] == "auth"

    def test_errors_exit_1(self, tmp_path, capsys):
        p = tmp_path / "m.txt"
        p.write_text("bad,,A\n", encoding="utf-8")
        rc = mod.run(str(p))
        assert rc == 1
        out = json.loads(capsys.readouterr().out.strip())
        assert out["errors"]

    def test_missing_file_exit_2(self, tmp_path, capsys):
        rc = mod.run(str(tmp_path / "nope.txt"))
        assert rc == 2
        err = json.loads(capsys.readouterr().err.strip())
        assert err["code"] == "MANIFEST_NOT_FOUND"
