#!/usr/bin/env python3
"""Tests for skf-merge-doc-urls.py — the deterministic doc_urls merge/suppress.

Covers the three operations (normalized-URL dedup, non-corpus segment
suppression, non-primary-locale collapse), the whole-language gate, and the
no-false-drift guarantee for ordinary skills. Plus a CLI-contract test.

v4.0.0 quality gate run 2 (skf-brief-skill determinism-1): the files form
maps skf-detect-docs.py's raw entries to the brief's {url, label, source}
and reads the existing entries from the upstream brief, so step-auto-brief
types no entry, and its source tokens stay inside the schema's enum.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT_PATH = ROOT / "src" / "shared" / "scripts" / "skf-merge-doc-urls.py"
SCHEMA_PATH = ROOT / "src" / "shared" / "scripts" / "schemas" / "skill-brief.v1.json"

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

    def test_cli_non_ascii_survives_cp1252_stdio(self):
        # Issue #465: a default Windows console decodes stdout as cp1252, which
        # crashed ensure_ascii=False output carrying non-ASCII (e.g. emoji).
        # PYTHONIOENCODING=cp1252 simulates that console on any platform; the
        # stdin payload stays ASCII-safe (json.dumps escapes the emoji) so only
        # the output path is under test.
        payload = {
            "scope_type": "full-library",
            "existing": [_reg("https://doc.rust-lang.org/book/", label="The Book \U0001F4CA")],
            "detected": [],
        }
        env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            input=json.dumps(payload),
            capture_output=True, encoding="utf-8", timeout=15, env=env,
        )
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert out["doc_urls"][0]["label"] == "The Book \U0001F4CA"

    def test_cli_raw_utf8_stdin_survives_cp1252_stdio(self):
        # Issue #465, stdin half: raw UTF-8 bytes (emoji NOT ASCII-escaped)
        # piped in under a cp1252 console. Without the sys.stdin reconfigure
        # the emoji's UTF-8 bytes decode as cp1252 mojibake, which the
        # round-trip assert below catches.
        payload = {
            "scope_type": "full-library",
            "existing": [_reg("https://doc.rust-lang.org/book/", label="The Book \U0001F4CA")],
            "detected": [],
        }
        env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            capture_output=True, timeout=15, env=env,
        )
        assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
        out = json.loads(proc.stdout.decode("utf-8"))
        assert out["doc_urls"][0]["label"] == "The Book \U0001F4CA"


# --------------------------------------------------------------------------
# Files form: skf-detect-docs.py's entries mapped, the existing entries read
# from the upstream brief (v4.0.0 quality gate run 2, determinism-1)
# --------------------------------------------------------------------------


def _raw(url, detected_via="readme_link", content_type="reference"):
    return {"url": url, "detected_via": detected_via, "content_hash": "sha256:0", "content_type": content_type}


def _cli(*args, stdin=""):
    return subprocess.run([sys.executable, str(SCRIPT_PATH), *args], input=stdin, capture_output=True,
                          text=True, encoding="utf-8", timeout=15)


class TestMapDetected:
    @pytest.mark.parametrize("detected_via, source", [
        pytest.param("homepageUrl", "homepage", id="homepage"),
        pytest.param("readme_link", "readme-detection", id="readme-link"),
        pytest.param("pages_api", "pages-api", id="pages-api"),
        pytest.param("docs_folder", "docs-folder", id="docs-folder"),
    ])
    def test_source_comes_from_detected_via(self, detected_via, source):
        mapped, suppressed = mod.map_detected([_raw("https://x.dev/", detected_via)])
        assert mapped == [{"url": "https://x.dev/", "label": "Reference", "source": source}]
        assert suppressed == []

    @pytest.mark.parametrize("content_type, label", [
        pytest.param("api-docs", "API Documentation", id="api-docs"),
        pytest.param("guide", "Guide", id="guide"),
        pytest.param("reference", "Reference", id="reference"),
        pytest.param(None, "", id="none"),
    ])
    def test_label_comes_from_content_type_only(self, content_type, label):
        # no "README Link" label: detected_via never names the label
        [entry], _ = mod.map_detected([_raw("https://x.dev/", "readme_link", content_type)])
        assert entry["label"] == label

    def test_an_unknown_detected_via_is_suppressed_never_merged(self):
        mapped, suppressed = mod.map_detected([_raw("https://x.dev/a", "brief_doc_urls"), {"url": "https://x.dev/b"},
                                               _raw("https://x.dev/c", ["readme_link"]), {"detected_via": "pages_api"}])
        assert mapped == []
        assert suppressed == [{"url": f"https://x.dev/{c}", "reason": "unknown-detected-via"} for c in "abc"]

    def test_every_source_it_writes_is_in_the_schema_enum(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        enum = set(schema["properties"]["doc_urls"]["items"]["properties"]["source"]["enum"])
        assert set(mod._SOURCE_BY_DETECTED_VIA.values()) == enum - {"language-registry"}


class TestFilesForm:
    def _brief(self, tmp_path, text):
        path = tmp_path / "skill-brief.yaml"
        path.write_bytes(text.encode("utf-8"))
        return path

    def test_detected_file_and_existing_brief_merge_as_the_stdin_form_does(self, tmp_path):
        brief = self._brief(tmp_path, "name: rust\nscope:\n  type: full-library\ndoc_urls:\n"
                                      "  - url: https://doc.rust-lang.org/book/\n    label: The Book\n"
                                      "    source: language-registry\n---\n")  # an SKF 1.x trailing ---
        detected = tmp_path / "detected.json"
        detected.write_bytes(json.dumps([
            _raw("https://doc.rust-lang.org/book/index.html"),           # dedup against the corpus
            _raw("https://doc.rust-lang.org/whatsnew/"),                 # whole-language noise
            _raw("https://docs.rs/serde", "docs_folder", "api-docs"),
            _raw("https://x.dev/", "brief_doc_urls"),
        ]).encode("utf-8"))
        proc = _cli("--scope-type", "full-library", "--detected-file", detected.as_posix(),
                    "--existing-brief", brief.as_posix(), stdin="not read")
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert out["doc_urls"] == [
            {"url": "https://doc.rust-lang.org/book/", "label": "The Book", "source": "language-registry"},
            {"url": "https://docs.rs/serde", "label": "API Documentation", "source": "docs-folder"},
        ]
        assert out["suppressed"] == [{"url": "https://x.dev/", "reason": "unknown-detected-via"},
                                     {"url": "https://doc.rust-lang.org/whatsnew/", "reason": "non-corpus-segment"}]

    def test_a_brief_without_doc_urls_gives_no_existing_entry(self, tmp_path):
        brief = self._brief(tmp_path, "name: demo\nscope:\n  type: public-api\n")
        detected = tmp_path / "detected.json"
        detected.write_bytes(json.dumps([_raw("https://demo.dev/guide/", "homepageUrl", "guide")]).encode("utf-8"))
        proc = _cli("--scope-type", "public-api", "--detected-file", detected.as_posix(),
                    "--existing-brief", brief.as_posix())
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout) == {
            "doc_urls": [{"url": "https://demo.dev/guide/", "label": "Guide", "source": "homepage"}],
            "suppressed": []}

    @pytest.mark.parametrize("detected, brief, message", [
        pytest.param(None, "name: x\n", "cannot read --detected-file", id="missing-detected-file"),
        pytest.param('{"url": "https://x.dev/"}', "name: x\n", "must hold a JSON array", id="detected-not-an-array"),
        pytest.param("[]", "name: [unclosed\n", "is not YAML", id="brief-not-yaml"),
        pytest.param("[]", "- a\n- b\n", "holds no brief mapping", id="brief-not-a-mapping"),
        pytest.param("[]", "doc_urls: https://x.dev/\n", "must be a list", id="doc-urls-not-a-list"),
    ])
    def test_bad_inputs_exit_2(self, tmp_path, detected, brief, message):
        detected_path = tmp_path / "detected.json"
        if detected is not None:
            detected_path.write_bytes(detected.encode("utf-8"))
        proc = _cli("--detected-file", detected_path.as_posix(),
                    "--existing-brief", self._brief(tmp_path, brief).as_posix())
        assert proc.returncode == 2 and message in proc.stderr, proc.stderr
