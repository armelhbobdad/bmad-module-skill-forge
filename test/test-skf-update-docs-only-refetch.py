#!/usr/bin/env python3
"""Tests for what a docs-only update writes from the documents it re-fetched.

Covers skf-build-change-manifest.py `apply` in docs-only mode: each
provenance entry of a re-fetched document takes every key its re-extract
record gives (a quote, a description), a kept entry drops what the earlier
fetch read that the record does not give again, and a new entry takes the
one extraction_method the map's T3 entries share (#1247); with the prose
of re-extract.md.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
SCRIPTS = REPO_ROOT / "src" / "shared" / "scripts"
MANIFEST_PATH = SCRIPTS / "skf-build-change-manifest.py"
RE_EXTRACT = REPO_ROOT / "src" / "skf-update-skill" / "references" / "re-extract.md"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


manifest = _load("skf_build_change_manifest_docs_only", MANIFEST_PATH)

BLOCK = {"generation_date": "2026-10-01T10:00:00Z", "confidence_tier": "Forge", "manual_sections_preserved": 2}

URL = "https://docs.example.com/api"
KEPT_URL = "https://docs.example.com/other"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _slice(text: str, start: str, end: str) -> str:
    i = text.index(start)
    return text[i:text.index(end, i + len(start))]


def _doc_entry(name: str, url: str, **extra) -> dict:
    """A docs-only skill's entry as create-skill writes it, plus `extra`."""
    return {"export_name": name, "export_type": "function", "source_library": "docs", "params": [],
            "return_type": None, "source_file": url, "confidence": "T3", "extraction_method": "doc-fetch",
            "signature_source": "T3", **extra}


def _apply(entries: list[dict], records: dict) -> tuple[dict, dict]:
    old = {"provenance_version": "2.0", "skill_name": "docs", "skill_type": "single", "entries": entries}
    return manifest.apply_update(update_type="incremental", provenance=old, skill_name="docs", records=records,
                                 test_report_run_id=None, **BLOCK)


def _by_name(doc: dict) -> dict:
    return {e["export_name"]: e for e in doc["entries"]}


# --------------------------------------------------------------------------
# #1247: an entry of a re-fetched document is what that run read
# --------------------------------------------------------------------------


def test_a_record_gives_its_entry_every_other_key():
    """The kept `get` and the new `put` take the quote and description their records give; an entry on a URL the
    run did not re-fetch is left as it was."""
    other = _doc_entry("other", KEPT_URL, quote="other q")
    doc, _ = _apply([_doc_entry("get", URL, quote="old q", description="old d"), dict(other)], {
        "mode": "docs-only", "changed_urls": [URL], "exports": [
            {"name": "get", "type": "function", "params": ["id"], "return_type": "Item", "url": URL,
             "quote": "new q", "description": "new d"},
            {"name": "put", "type": "function", "params": ["item"], "url": URL, "quote": "put q",
             "description": "put d"}]})
    entries = _by_name(doc)
    assert (entries["get"].get("quote"), entries["get"].get("description")) == ("new q", "new d")
    assert (entries["put"].get("quote"), entries["put"].get("description")) == ("put q", "put d")
    assert (entries["get"]["params"], entries["get"]["return_type"]) == (["id"], "Item")
    # the kept entry keeps its source_library, extraction_method and T3 labels; the new one takes the map's one
    # extraction_method
    assert (entries["get"]["source_library"], entries["get"]["extraction_method"], entries["get"]["confidence"],
            entries["get"]["signature_source"]) == ("docs", "doc-fetch", "T3", "T3")
    assert (entries["put"]["extraction_method"], entries["put"]["confidence"], entries["put"]["signature_source"]) == \
        ("doc-fetch", "T3", "T3")
    assert entries["other"] == other


def test_a_kept_entry_drops_a_key_its_record_leaves_out():
    """What the earlier fetch read (a quote, a create-time corpus position, a hand note) goes; the entry's
    source_library, extraction_method and T3 labels stay."""
    doc, _ = _apply([_doc_entry("get", URL, source_library="docs-lib", return_type="Item", quote="old q",
                                corpus_file="corpus/api.md", corpus_line=12, notes="hand note")], {
        "mode": "docs-only", "changed_urls": [URL], "exports": [
            {"name": "get", "type": "function", "params": ["id"], "return_type": None, "url": URL}]})
    get = _by_name(doc)["get"]
    for gone in ("quote", "corpus_file", "corpus_line", "notes"):
        assert gone not in get, gone
    assert (get["source_library"], get["extraction_method"], get["confidence"], get["signature_source"]) == \
        ("docs-lib", "doc-fetch", "T3", "T3")
    # a null return_type keeps the entry's value, as any rewrite does
    assert (get["params"], get["return_type"], get["source_file"]) == (["id"], "Item", URL)


def test_a_record_cannot_set_the_keys_apply_sets():
    """A record's own source_library, labels, source_file and bookkeeping keys stay off its entry, kept or new: the
    entry keeps its library (a new one takes the map's), T3 labels and its URL as source_file."""
    given = {"type": "class", "url": URL, "parameters": ["p"], "source_library": "other-lib", "confidence": "T1",
             "signature_source": "T1", "source_file": "corpus/api.md"}
    doc, _ = _apply([_doc_entry("get", URL)], {"mode": "docs-only", "changed_urls": [URL], "exports": [
        {"name": "get", **given}, {"name": "put", **given}]})
    entries = _by_name(doc)
    for name in ("get", "put"):
        entry = entries[name]
        assert (entry["source_library"], entry["confidence"], entry["signature_source"], entry["source_file"]) == \
            ("docs", "T3", "T3", URL), name
        assert (entry["export_type"], entry["params"]) == ("class", ["p"]), name
        for key in ("name", "type", "url", "parameters"):
            assert key not in entry, (name, key)


@pytest.mark.parametrize(("methods", "record_method", "expected"), [
    (("doc-fetch", "doc-fetch"), None, "doc-fetch"),
    (("doc-fetch", "doc-fetch"), "web-read", "web-read"),
    (("doc-fetch", "web-read"), None, None),
    (("doc-fetch", None), None, None),
], ids=["shared", "record-wins", "mixed", "missing"])
def test_a_new_entry_takes_the_maps_one_extraction_method(methods, record_method, expected):
    entries = []
    for i, method in enumerate(methods):
        entry = _doc_entry(f"e{i}", KEPT_URL)
        if method is None:
            del entry["extraction_method"]
        else:
            entry["extraction_method"] = method
        entries.append(entry)
    # a T1 entry's extraction_method is not a documentation entry's, so it does not count
    entries.append({**_doc_entry("code", "pkg/a.py"), "confidence": "T1", "extraction_method": "ast-grep",
                    "signature_source": "T1"})
    record = {"name": "put", "type": "function", "params": ["item"], "url": URL}
    if record_method is not None:
        record["extraction_method"] = record_method
    doc, _ = _apply(entries, {"mode": "docs-only", "changed_urls": [URL], "exports": [record]})
    put = _by_name(doc)["put"]
    assert put.get("extraction_method") == expected
    if expected is None:
        assert "extraction_method" not in put
    assert (put["source_library"], put["confidence"], put["signature_source"]) == ("docs", "T3", "T3")


def test_re_extract_asks_for_every_key_the_entries_carry():
    """re-extract.md §1's record shape has room for the keys a docs-only entry carries."""
    one = _slice(_read(RE_EXTRACT), "### 1. Check for Docs-Only Mode", "### 1b.")
    assert "such as a `quote` or a `description`" in one
    assert "drops every other key the record leaves out" in one
