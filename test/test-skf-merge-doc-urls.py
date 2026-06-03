#!/usr/bin/env python3
"""Tests for skf-merge-doc-urls.py — the deterministic doc_urls merge/suppress.

Covers the three operations (normalized-URL dedup, non-corpus segment
suppression, non-primary-locale collapse), the whole-language gate, and the
no-false-drift guarantee for ordinary skills. Plus a CLI-contract test.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPT_PATH = ROOT / "src" / "shared" / "scripts" / "skf-merge-doc-urls.py"

spec = importlib.util.spec_from_file_location("skf_merge_doc_urls", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _reg(url, label="C"):
    return {"url": url, "label": label, "source": "language-registry"}


def _det(url, label="D", source="readme-detection"):
    return {"url": url, "label": label, "source": source}


def _urls(entries):
    return [e["url"] for e in entries]


class TestDedup:
    def test_normalized_url_collapse_existing_wins(self):
        existing = [_reg("https://doc.rust-lang.org/book/")]
        detected = [_det("https://doc.rust-lang.org/book/index.html")]
        kept, suppressed = mod.merge_doc_urls("full-library", existing, detected)
        assert _urls(kept) == ["https://doc.rust-lang.org/book/"]
        assert suppressed == []  # a dedup is not a suppression

    def test_trailing_slash_and_host_case_dedup(self):
        existing = [_reg("https://Doc.Rust-Lang.org/std")]
        detected = [_det("https://doc.rust-lang.org/std/")]
        kept, _ = mod.merge_doc_urls("full-library", existing, detected)
        assert len(kept) == 1


class TestNonCorpusSegmentSuppression:
    def test_whatsnew_contribute_wiki_dropped_on_registry_host(self):
        existing = [_reg("https://doc.rust-lang.org/book/")]
        detected = [
            _det("https://doc.rust-lang.org/whatsnew/"),
            _det("https://doc.rust-lang.org/contribute"),
            _det("https://doc.rust-lang.org/wiki/Questions"),
        ]
        kept, suppressed = mod.merge_doc_urls("full-library", existing, detected)
        assert _urls(kept) == ["https://doc.rust-lang.org/book/"]
        assert {s["reason"] for s in suppressed} == {"non-corpus-segment"}
        assert len(suppressed) == 3

    def test_whatsnew_with_separator_dropped(self):
        existing = [_reg("https://doc.rust-lang.org/book/")]
        detected = [_det("https://doc.rust-lang.org/whatsnew-2024/")]
        kept, suppressed = mod.merge_doc_urls("full-library", existing, detected)
        assert kept == existing
        assert suppressed[0]["reason"] == "non-corpus-segment"

    def test_substring_lookalike_not_dropped(self):
        # /docs/whatsnewfeatures/ is a real guide page, NOT a changelog.
        existing = [_reg("https://doc.rust-lang.org/book/")]
        detected = [_det("https://doc.rust-lang.org/docs/whatsnewfeatures/")]
        kept, suppressed = mod.merge_doc_urls("full-library", existing, detected)
        assert "https://doc.rust-lang.org/docs/whatsnewfeatures/" in _urls(kept)
        assert suppressed == []

    def test_non_registry_host_not_suppressed(self):
        # A README doc on a DIFFERENT host than any corpus is kept even if it
        # has a /wiki/ segment — suppression is anchored to corpus hosts.
        existing = [_reg("https://doc.rust-lang.org/book/")]
        detected = [_det("https://github.com/rust-lang/rust/wiki/Home")]
        kept, suppressed = mod.merge_doc_urls("full-library", existing, detected)
        assert "https://github.com/rust-lang/rust/wiki/Home" in _urls(kept)
        assert suppressed == []


class TestLocaleCollapse:
    def test_non_primary_locale_dropped_when_twin_kept(self):
        existing = [_reg("https://docs.python.org/en/master/")]
        detected = [_det("https://docs.python.org/ja/master/")]
        kept, suppressed = mod.merge_doc_urls("full-library", existing, detected)
        assert _urls(kept) == ["https://docs.python.org/en/master/"]
        assert suppressed[0]["reason"] == "non-primary-locale-dup"

    def test_non_primary_locale_kept_without_twin(self):
        # /ja/guide with no /en/guide or /guide twin — keep it (twin-required).
        existing = [_reg("https://docs.python.org/library/")]
        detected = [_det("https://docs.python.org/ja/tutorial/")]
        kept, suppressed = mod.merge_doc_urls("full-library", existing, detected)
        assert "https://docs.python.org/ja/tutorial/" in _urls(kept)
        assert suppressed == []

    def test_short_subsection_not_treated_as_locale(self):
        # /go/ is a subsection, not a locale — must not collapse against /py/.
        existing = [_reg("https://docs.example.com/py/intro/")]
        detected = [_det("https://docs.example.com/go/intro/")]
        kept, suppressed = mod.merge_doc_urls("full-library", existing, detected)
        assert "https://docs.example.com/go/intro/" in _urls(kept)
        assert suppressed == []

    def test_primary_locale_never_dropped(self):
        existing = [_reg("https://docs.python.org/library/")]
        detected = [_det("https://docs.python.org/en/library/")]
        kept, suppressed = mod.merge_doc_urls("full-library", existing, detected)
        # /en/library normalizes to a twin of /library → it's a dedup-equivalent
        # but a primary locale is never SUPPRESSED.
        assert all(s["reason"] != "non-primary-locale-dup" for s in suppressed)


class TestGate:
    def test_non_full_library_passes_through(self):
        # An ordinary library (scope_type != full-library) gets dedup only —
        # no suppression, byte-identical merge behaviour.
        existing = [_det("https://docs.x.com/", source="readme-detection")]
        detected = [
            _det("https://docs.x.com/whatsnew/"),
            _det("https://docs.x.com/wiki/Home"),
        ]
        kept, suppressed = mod.merge_doc_urls("public-api", existing, detected)
        assert len(kept) == 3
        assert suppressed == []

    def test_full_library_without_registry_corpora_passes_through(self):
        # full-library but no language-registry entry → gate inactive (the
        # N==0 DEGRADED case is intentionally out of scope).
        existing = [_det("https://docs.x.com/", source="readme-detection")]
        detected = [_det("https://docs.x.com/whatsnew/")]
        kept, suppressed = mod.merge_doc_urls("full-library", existing, detected)
        assert "https://docs.x.com/whatsnew/" in _urls(kept)
        assert suppressed == []

    def test_seeded_corpus_under_wiki_never_dropped(self):
        # A registry-seeded entry that itself sits under /wiki/ is in `existing`
        # and is never a suppression candidate.
        existing = [_reg("https://docs.example.com/wiki/Spec")]
        detected = [_det("https://docs.example.com/whatsnew/")]
        kept, suppressed = mod.merge_doc_urls("full-library", existing, detected)
        assert "https://docs.example.com/wiki/Spec" in _urls(kept)
        assert {s["reason"] for s in suppressed} == {"non-corpus-segment"}


class TestCli:
    def test_cli_contract(self):
        payload = {
            "scope_type": "full-library",
            "existing": [_reg("https://doc.rust-lang.org/book/")],
            "detected": [
                _det("https://doc.rust-lang.org/whatsnew/"),
                _det("https://other.example.com/guide/"),
            ],
        }
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            input=json.dumps(payload),
            capture_output=True, text=True, timeout=15,
        )
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert _urls(out["doc_urls"]) == [
            "https://doc.rust-lang.org/book/",
            "https://other.example.com/guide/",
        ]
        assert len(out["suppressed"]) == 1

    def test_cli_bad_json_exit_2(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            input="not json", capture_output=True, text=True, timeout=15,
        )
        assert proc.returncode == 2
