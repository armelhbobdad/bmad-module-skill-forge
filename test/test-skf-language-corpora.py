#!/usr/bin/env python3
"""Tests for skf-language-corpora.py — the canonical language→corpora registry.

Pure-function tests over corpora_for(), plus subprocess tests for the CLI
contract (exit 0 hit / 1 miss / 2 error) and the brief doc_urls output shape.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT_PATH = ROOT / "src" / "shared" / "scripts" / "skf-language-corpora.py"
DATA_PATH = ROOT / "src" / "shared" / "data" / "language-corpora.json"

spec = importlib.util.spec_from_file_location("skf_language_corpora", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

SEEDED = ["rust", "python", "go", "typescript", "javascript", "ruby"]


class TestCorporaLookup:
    @pytest.mark.parametrize("lang", SEEDED)
    def test_seeded_language_has_corpora(self, lang):
        result = mod.corpora_for(lang)
        assert len(result) >= 1, f"{lang} should have ≥1 corpus"

    def test_case_insensitive(self):
        assert mod.corpora_for("Rust") == mod.corpora_for("rust")
        assert mod.corpora_for("  PYTHON  ") == mod.corpora_for("python")

    def test_unknown_language_is_empty(self):
        assert mod.corpora_for("cobol") == []
        assert mod.corpora_for("") == []

    def test_output_is_brief_contract_shape_only(self):
        """Each entry is exactly {url, label, source} — NOT the detect-docs shape
        with content_type/detected_via. The `source` field (issue #432) marks
        these as registry-guaranteed corpora so downstream noise-suppression
        (#431) and assembly tier-ordering (#430) can branch on provenance."""
        for lang in SEEDED:
            for entry in mod.corpora_for(lang):
                assert set(entry.keys()) == {"url", "label", "source"}, entry
                assert entry["url"].startswith("http")
                assert entry["label"]
                assert entry["source"] == "language-registry"

    def test_rust_includes_book_and_std(self):
        urls = [e["url"] for e in mod.corpora_for("rust")]
        assert any("/book/" in u for u in urls)
        assert any("/std/" in u for u in urls)


class TestRegistryData:
    def test_all_keys_lowercase_and_known(self):
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        keys = [k for k in data if not k.startswith("_")]
        assert set(keys) == set(SEEDED), keys
        assert all(k == k.lower() for k in keys)

    def test_no_duplicate_urls_within_a_language(self):
        for lang in SEEDED:
            urls = [e["url"] for e in mod.corpora_for(lang)]
            assert len(urls) == len(set(urls)), f"{lang} has duplicate URLs"


class TestCli:
    def test_cli_hit_exit_0(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--language", "rust"],
            capture_output=True, text=True, timeout=15,
        )
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert isinstance(out, list) and len(out) >= 1
        assert set(out[0].keys()) == {"url", "label", "source"}
        assert out[0]["source"] == "language-registry"

    def test_cli_miss_exit_1(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--language", "brainfuck"],
            capture_output=True, text=True, timeout=15,
        )
        assert proc.returncode == 1
        assert json.loads(proc.stdout) == []

    def test_cli_missing_arg_exit_2(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            capture_output=True, text=True, timeout=15,
        )
        assert proc.returncode == 2
