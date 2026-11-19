#!/usr/bin/env python3
"""Tests for what a docs-only update writes from the documents it re-fetched.

Covers skf-build-change-manifest.py `apply` in docs-only mode: each
provenance entry of a re-fetched document takes every key its re-extract
record gives (a quote, a description), a kept entry drops what the earlier
fetch read that the record does not give again, and a new entry takes the
one extraction_method the map's T3 entries share (#1247). Then a document
the update cites first (#1249): `apply` writes the entries of an export URL
the map holds none of and warns about each record it leaves out, and
skf-detect-docs.py `refresh-hashes --records` starts tracking each cited
document `doc_sources` lacks, so the next comparison reads it; with the
prose of re-extract.md, write-metadata.md and the result envelope schema.
Last, the counts a docs-only run records (#1266): a URL changed_urls lists
twice is applied once, and a record left out counts toward neither.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
SCRIPTS = REPO_ROOT / "src" / "shared" / "scripts"
MANIFEST_PATH = SCRIPTS / "skf-build-change-manifest.py"
DETECT_DOCS_PATH = SCRIPTS / "skf-detect-docs.py"
RE_EXTRACT = REPO_ROOT / "src" / "skf-update-skill" / "references" / "re-extract.md"
WRITE_META = REPO_ROOT / "src" / "skf-update-skill" / "references" / "write-metadata.md"
ENVELOPE_SCHEMA = SCRIPTS / "schemas" / "skf-update-result-envelope.v1.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


manifest = _load("skf_build_change_manifest_docs_only", MANIFEST_PATH)
detect_docs = _load("skf_detect_docs_docs_only", DETECT_DOCS_PATH)

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


# --------------------------------------------------------------------------
# #1249: a document the update cites first is written and tracked
# --------------------------------------------------------------------------

NEW_URL = "https://docs.example.com/linked"


def test_an_export_on_a_document_the_map_does_not_hold_is_applied():
    """A page a changed document now links to: its exports become entries though changed_urls does not list it."""
    doc, summary = _apply([_doc_entry("get", URL)], {"mode": "docs-only", "changed_urls": [URL], "exports": [
        {"name": "get", "type": "function", "params": ["id"], "url": URL},
        {"name": "linked", "type": "function", "params": ["x"], "url": NEW_URL, "quote": "linked q"},
        {"name": "linked_too", "type": "function", "params": [], "url": NEW_URL}]})
    linked = _by_name(doc)["linked"]
    assert (linked["source_file"], linked["confidence"], linked["signature_source"], linked["quote"]) == \
        (NEW_URL, "T3", "T3", "linked q")
    assert linked["extraction_method"] == "doc-fetch"
    # the new document counts once, however many exports it has
    assert doc["files_changed"] == 2 and summary["warnings"] == []
    assert (summary["entries"]["added"], summary["entries"]["removed"]) == (["get", "linked", "linked_too"], ["get"])


def test_a_record_left_out_is_named_in_one_warning():
    """An export on a URL the map holds entries of that changed_urls does not list, a record with no url and one
    with no name: the held document's entries stay as they were, and one warning names all three."""
    held = [_doc_entry("get", URL), _doc_entry("other", KEPT_URL, quote="other q")]
    doc, summary = _apply([dict(e) for e in held], {"mode": "docs-only", "changed_urls": [URL], "exports": [
        {"name": "get", "type": "function", "url": URL},
        {"name": "stray", "type": "function", "url": KEPT_URL},
        {"name": "lost", "type": "function"},
        {"type": "function", "url": URL}]})
    entries = _by_name(doc)
    assert "stray" not in entries and "lost" not in entries
    assert [e["export_name"] for e in doc["entries"] if e["source_file"] == URL] == ["get"]
    assert [e for e in doc["entries"] if e["source_file"] == KEPT_URL] == [held[1]]
    assert len(summary["warnings"]) == 1
    warning = summary["warnings"][0]
    assert warning.startswith("provenance: 3 docs-only records not applied")
    assert f"stray ({KEPT_URL})" in warning and "lost (no url)" in warning and f"(no name) ({URL})" in warning
    assert (doc["files_changed"], doc["exports_affected"]) == (1, 1)


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _cli(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(DETECT_DOCS_PATH), *argv], capture_output=True, encoding="utf-8")


def _write_json(path: Path, data) -> Path:
    path.write_bytes((json.dumps(data) + "\n").encode("utf-8"))
    return path


def _three_documents(tmp_path: Path) -> dict:
    """A tracked and stale (its page changed), B a page the update cites first, C one it cannot fetch; the
    comparison step 2 wrote, and the records re-extract.md §1 wrote."""
    a, b, c = tmp_path / "a.md", tmp_path / "b.md", tmp_path / "c.md"
    a.write_bytes(b"a two\n")
    b.write_bytes(b"b one\n")
    urls = {name: "file://" + path.as_posix() for name, path in (("A", a), ("B", b), ("C", c))}
    meta = _write_json(tmp_path / "metadata.json", {"name": "docs", "source_type": "docs-only", "doc_sources": [
        {"url": urls["A"], "detected_via": "brief_doc_urls", "content_hash": _sha(b"a one\n"),
         "recorded_at": "2026-01-01T00:00:00+00:00"}]})
    compare = _cli("compare-hashes", str(meta))
    assert [e["url"] for e in json.loads(compare.stdout)["changed"]] == [urls["A"]]
    comparison = tmp_path / "doc-hashes.json"
    comparison.write_bytes(compare.stdout.encode("utf-8"))
    records = _write_json(tmp_path / "reextract-records.json", {
        "mode": "docs-only", "changed_urls": [urls["A"], urls["B"]],
        "exports": [{"name": "x", "url": urls["A"]}, {"name": "y", "url": urls["C"]}, {"name": "z", "url": urls["B"]},
                    {"name": "no-url"}]})
    return {"urls": urls, "meta": meta, "comparison": comparison, "records": records, "b": b}


def test_refresh_hashes_tracks_each_document_the_records_cite(tmp_path):
    docs = _three_documents(tmp_path)
    urls = docs["urls"]
    result = _cli("refresh-hashes", str(docs["meta"]), "--compare", str(docs["comparison"]),
                  "--records", str(docs["records"]))
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert (out["refreshed"], out["not_found"], out["added"]) == ([urls["A"]], [], [urls["B"], urls["C"]])
    assert [f["url"] for f in out["fetch_failed"]] == [urls["C"]] and out["fetch_failed"][0]["reason"]
    sources = json.loads(docs["meta"].read_bytes())["doc_sources"]
    assert [s["url"] for s in sources] == [urls["A"], urls["B"], urls["C"]]
    assert (sources[0]["content_hash"], sources[1]["content_hash"], sources[2]["content_hash"]) == \
        (_sha(b"a two\n"), _sha(b"b one\n"), None)
    assert [s["detected_via"] for s in sources] == ["brief_doc_urls"] * 3
    assert len({s["recorded_at"] for s in sources}) == 1  # one stamp for the refresh and the additions
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".")] == []  # no temporary file left
    # the next update compares the new document too
    docs["b"].write_bytes(b"b two\n")
    again = json.loads(_cli("compare-hashes", str(docs["meta"])).stdout)
    assert [e["url"] for e in again["changed"]] == [urls["B"]]
    assert again["stats"]["total_tracked"] == 3 and again["skipped_null_hash"] == [{"url": urls["C"]}]
    # #1267: once C can be read, update-skill's --fetch-null comparison counts it changed, refresh-hashes
    # records its hash, and the next comparison finds every document unchanged
    (tmp_path / "c.md").write_bytes(b"c one\n")
    fetched = _cli("compare-hashes", str(docs["meta"]), "--fetch-null")
    assert fetched.returncode == 0, fetched.stderr
    comparison = json.loads(fetched.stdout)
    assert [(e["url"], e["old_hash"]) for e in comparison["changed"]] == \
        [(urls["B"], _sha(b"b one\n")), (urls["C"], None)]
    assert comparison["skipped_null_hash"] == []
    saved = tmp_path / "doc-hashes-null.json"
    saved.write_bytes(fetched.stdout.encode("utf-8"))
    refresh = _cli("refresh-hashes", str(docs["meta"]), "--compare", str(saved))
    assert refresh.returncode == 0, refresh.stderr
    assert json.loads(refresh.stdout)["refreshed"] == [urls["B"], urls["C"]]
    assert json.loads(docs["meta"].read_bytes())["doc_sources"][2]["content_hash"] == _sha(b"c one\n")
    last = json.loads(_cli("compare-hashes", str(docs["meta"])).stdout)
    assert (last["changed"], last["skipped_null_hash"]) == ([], [])
    assert last["unchanged"] == [{"url": urls[name]} for name in ("A", "B", "C")]


def test_a_rerun_adds_nothing(tmp_path):
    docs = _three_documents(tmp_path)
    first = _cli("refresh-hashes", str(docs["meta"]), "--compare", str(docs["comparison"]),
                 "--records", str(docs["records"]))
    assert first.returncode == 0, first.stderr
    docs["comparison"].write_bytes(_cli("compare-hashes", str(docs["meta"])).stdout.encode("utf-8"))
    before = json.loads(docs["meta"].read_bytes())
    result = _cli("refresh-hashes", str(docs["meta"]), "--compare", str(docs["comparison"]),
                  "--records", str(docs["records"]))
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert (out["refreshed"], out["added"], out["fetch_failed"]) == ([], [], [])
    assert json.loads(docs["meta"].read_bytes()) == before


@pytest.mark.parametrize("records", [b"{nope", b"[]", b'{"changed_urls": "x"}', b'{"exports": {}}', None],
                         ids=["not-json", "not-an-object", "changed-urls-not-an-array", "exports-not-an-array",
                              "missing"])
def test_bad_records_exit_2_and_write_nothing(tmp_path, records):
    docs = _three_documents(tmp_path)
    before = docs["meta"].read_bytes()
    bad = tmp_path / "bad-records.json"
    if records is not None:
        bad.write_bytes(records)
    result = _cli("refresh-hashes", str(docs["meta"]), "--compare", str(docs["comparison"]), "--records", str(bad))
    assert result.returncode == 2 and json.loads(result.stderr)["code"] == "REFRESH_FAILED"
    assert docs["meta"].read_bytes() == before
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".")] == []


def test_without_records_nothing_is_added(tmp_path):
    docs = _three_documents(tmp_path)
    result = _cli("refresh-hashes", str(docs["meta"]), "--compare", str(docs["comparison"]))
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert (out["refreshed"], out["added"], out["fetch_failed"]) == ([docs["urls"]["A"]], [], [])
    assert [s["url"] for s in json.loads(docs["meta"].read_bytes())["doc_sources"]] == [docs["urls"]["A"]]


def _warnings_description(schema) -> str:
    """The description of the envelope's `warnings` array."""
    if isinstance(schema, dict):
        warnings = schema.get("properties", {}).get("warnings")
        if isinstance(warnings, dict) and "description" in warnings:
            return warnings["description"]
        for value in schema.values():
            found = _warnings_description(value)
            if found:
                return found
    if isinstance(schema, list):
        for value in schema:
            found = _warnings_description(value)
            if found:
                return found
    return ""


def test_the_steps_pass_the_records_and_report_each_document_added():
    paragraph = _read(WRITE_META).split("**A docs-only skill's document hashes.**", 1)[1]
    fence = paragraph.split("```bash\n", 1)[1].split("```", 1)[0]
    assert '--records "{run_dir}/reextract-records.json"' in fence
    assert "`doc-source-added: {url}`" in paragraph and "`doc-not-hashed: {url} ({reason})`" in paragraph
    one = _slice(_read(RE_EXTRACT), "### 1. Check for Docs-Only Mode", "### 1b.")
    assert "[<each URL this step fetched>]" in one and "a page a changed document now links to" in one
    assert "doc-source-added" in _warnings_description(json.loads(_read(ENVELOPE_SCHEMA)))


# --------------------------------------------------------------------------
# #1266: a docs-only run counts only what it applied
# --------------------------------------------------------------------------


def _held() -> list[dict]:
    """The map each #1266 run starts from."""
    return [_doc_entry("get", URL), _doc_entry("other", KEPT_URL)]


@pytest.mark.parametrize(("changed_urls", "exports", "counts", "names"), [
    pytest.param([URL, URL], [{"name": "get", "type": "function", "url": URL}], (1, 1), ["get"], id="twice"),
    pytest.param([URL, KEPT_URL, URL], [{"name": "get", "type": "function", "url": URL},
                                        {"name": "other", "type": "function", "url": KEPT_URL}],
                 (2, 2), ["get", "other"], id="among-others"),
])
def test_a_url_listed_twice_is_applied_once(changed_urls, exports, counts, names):
    """A URL changed_urls lists twice: the document counts once, the summary names each of its exports once, and
    the map's entries are those of a run listing it once."""
    doc, summary = _apply(_held(), {"mode": "docs-only", "changed_urls": changed_urls,
                                    "exports": [dict(e) for e in exports]})
    assert (doc["files_changed"], doc["exports_affected"]) == counts
    assert (summary["entries"]["added"], summary["entries"]["removed"]) == (names, names)
    assert summary["warnings"] == []
    once, _ = _apply(_held(), {"mode": "docs-only", "changed_urls": list(dict.fromkeys(changed_urls)),
                               "exports": [dict(e) for e in exports]})
    assert doc["entries"] == once["entries"]


def test_a_nameless_record_on_a_new_document_counts_no_document():
    """A record with no name on a URL the map holds no entry of: neither count takes it, the warning still names
    it, and the map's entries are those of a run without it."""
    get = {"name": "get", "type": "function", "url": URL}
    doc, summary = _apply(_held(), {"mode": "docs-only", "changed_urls": [URL], "exports": [
        dict(get), {"type": "function", "url": NEW_URL}]})
    assert (doc["files_changed"], doc["exports_affected"]) == (1, 1)
    assert (summary["entries"]["added"], summary["entries"]["removed"]) == (["get"], ["get"])
    assert len(summary["warnings"]) == 1
    warning = summary["warnings"][0]
    assert warning.startswith("provenance: 1 docs-only record not applied")
    assert f"(no name) ({NEW_URL})" in warning
    without, _ = _apply(_held(), {"mode": "docs-only", "changed_urls": [URL], "exports": [dict(get)]})
    assert doc["entries"] == without["entries"]
