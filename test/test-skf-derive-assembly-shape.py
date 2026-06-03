#!/usr/bin/env python3
"""Tests for skf-derive-assembly-shape.py — the whole-language assembly gate.

Proves the gate fires on exactly a registry-corpora brief and NOT on the
negative-control shapes (ordinary library, parser library, component-library,
reference-app, docs-only) or the registry-miss N==0 case. This is the
deterministic regression proof for the otherwise-LLM-driven #430 assembly.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPT_PATH = ROOT / "src" / "shared" / "scripts" / "skf-derive-assembly-shape.py"

spec = importlib.util.spec_from_file_location("skf_derive_assembly_shape", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _brief(scope_type="full-library", doc_urls=None, notes=""):
    b = {
        "name": "x",
        "version": "1.0.0",
        "source_repo": "https://github.com/x/y",
        "language": "rust",
        "description": "d",
        "forge_tier": "Forge",
        "created": "2026-06-03",
        "created_by": "armel",
        "scope": {"type": scope_type, "include": [], "exclude": [], "notes": notes},
    }
    if doc_urls is not None:
        b["doc_urls"] = doc_urls
    return b


CAVEAT = " LANGUAGE-REFERENCE CAVEAT: this skill's value is the rust prose ..."


class TestWholeLanguageGate:
    def test_registry_corpus_fires_gate(self):
        brief = _brief(doc_urls=[
            {"url": "https://doc.rust-lang.org/book/", "label": "Book",
             "source": "language-registry"},
        ])
        out = mod.derive_assembly_shape(brief)
        assert out == {"assembly_shape": "whole-language-reference",
                       "gate_signal": "language-registry"}

    def test_mixed_with_one_registry_entry_fires(self):
        brief = _brief(doc_urls=[
            {"url": "https://docs.rs/x", "source": "readme-detection"},
            {"url": "https://doc.rust-lang.org/std/", "source": "language-registry"},
        ])
        assert mod.derive_assembly_shape(brief)["assembly_shape"] == "whole-language-reference"


class TestNegativeControls:
    def test_ordinary_library_readme_docs_only(self):
        # full-library with only README-detected docs — no registry corpus.
        brief = _brief(doc_urls=[
            {"url": "https://docs.x.com/", "source": "readme-detection"},
            {"url": "https://x.com/", "source": "homepage"},
        ])
        assert mod.derive_assembly_shape(brief)["assembly_shape"] == "standard"

    def test_parser_library_no_corpora(self):
        # pest/lalrpop: §6b is skipped, no corpora seeded.
        brief = _brief(doc_urls=[{"url": "https://docs.rs/pest", "source": "readme-detection"}])
        assert mod.derive_assembly_shape(brief)["assembly_shape"] == "standard"

    def test_component_library(self):
        brief = _brief(scope_type="component-library", doc_urls=[
            {"url": "https://ui.example.com/", "source": "homepage"},
        ])
        assert mod.derive_assembly_shape(brief)["assembly_shape"] == "standard"

    def test_reference_app_including_dsl_subshape(self):
        brief = _brief(scope_type="reference-app", doc_urls=[
            {"url": "https://surrealdb.com/docs", "source": "readme-detection"},
        ])
        assert mod.derive_assembly_shape(brief)["assembly_shape"] == "standard"

    def test_docs_only_user_urls(self):
        # docs-only doc_urls are user-provided and carry no source.
        brief = _brief(scope_type="docs-only", doc_urls=[{"url": "https://docs.x.com/"}])
        assert mod.derive_assembly_shape(brief)["assembly_shape"] == "standard"

    def test_no_doc_urls(self):
        assert mod.derive_assembly_shape(_brief())["assembly_shape"] == "standard"

    def test_empty_doc_urls(self):
        assert mod.derive_assembly_shape(_brief(doc_urls=[]))["assembly_shape"] == "standard"

    def test_n0_registry_miss_caveat_only_not_gated(self):
        # A registry-miss whole-language ref: the DEGRADED caveat is in notes,
        # but no language-registry doc_url exists — must NOT fire (nothing to
        # foreground). Gating on the structured field, not the notes substring.
        brief = _brief(notes="Auto-scoped." + CAVEAT, doc_urls=None)
        assert mod.derive_assembly_shape(brief)["assembly_shape"] == "standard"

    def test_scope_notes_caveat_does_not_gate_with_readme_docs(self):
        # Caveat present + README docs added post-hoc — still must NOT fire,
        # because none of the docs are registry-sourced (the old fallback would
        # have misfired here).
        brief = _brief(notes=CAVEAT, doc_urls=[
            {"url": "https://x.com/", "source": "homepage"},
        ])
        assert mod.derive_assembly_shape(brief)["assembly_shape"] == "standard"


class TestCli:
    def test_cli_stdin_whole_language(self):
        brief = _brief(doc_urls=[
            {"url": "https://doc.rust-lang.org/book/", "source": "language-registry"},
        ])
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "-"],
            input=json.dumps(brief), capture_output=True, text=True, timeout=15,
        )
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["assembly_shape"] == "whole-language-reference"

    def test_cli_path_standard(self, tmp_path):
        import yaml as _yaml
        p = tmp_path / "skill-brief.yaml"
        p.write_text(_yaml.safe_dump(_brief()), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), str(p)],
            capture_output=True, text=True, timeout=15,
        )
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["assembly_shape"] == "standard"

    def test_cli_missing_file_exit_2(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "/no/such/brief.yaml"],
            capture_output=True, text=True, timeout=15,
        )
        assert proc.returncode == 2
