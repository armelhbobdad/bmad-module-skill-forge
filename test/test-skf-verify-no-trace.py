#!/usr/bin/env python3
"""Tests for skf-verify-no-trace.py."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-verify-no-trace.py"

spec = importlib.util.spec_from_file_location("skf_verify_no_trace", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

OLD = "rename"
NEW = "rename-skill"


def build_tree(tmp_path, version, skill_md, metadata, snippet, provenance, inner_name=NEW):
    """Materialize a new_skill_group + new_forge_group for one version."""
    skill_group = tmp_path / "out" / NEW
    forge_group = tmp_path / "forge" / NEW
    inner = skill_group / version / inner_name
    inner.mkdir(parents=True)
    (inner / "SKILL.md").write_text(skill_md)
    (inner / "metadata.json").write_text(metadata)
    (inner / "context-snippet.md").write_text(snippet)
    fv = forge_group / version
    fv.mkdir(parents=True)
    (fv / "provenance-map.json").write_text(provenance)
    return skill_group, forge_group


CLEAN_SKILL_MD = (
    "---\nname: rename-skill\ndescription: x\n---\n"
    "# rename-skill\nHistorically this was the rename workflow.\n"
)
CLEAN_METADATA = json.dumps({"name": NEW, "version": "1.0.0"}, indent=2) + "\n"
CLEAN_SNIPPET = "[rename-skill v1.0.0]|root: .claude/skills/rename-skill/\n"
CLEAN_PROV = json.dumps({"skill_name": NEW}, indent=2) + "\n"


class TestVerify:
    def test_clean_tree(self, tmp_path):
        sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, CLEAN_METADATA, CLEAN_SNIPPET, CLEAN_PROV)
        r = mod.verify(sg, fg, OLD, NEW, ["1.0.0"])
        assert r["clean"] is True
        assert r["hard_matches"] == []
        # Body mention of "rename" is advisory only.
        assert len(r["body_warnings"]) == 1
        assert r["body_warnings"][0]["region"] == "skill-body"
        assert r["dir_violations"] == []

    def test_new_name_substring_not_flagged(self, tmp_path):
        # OLD ("rename") is a substring of NEW ("rename-skill"); the correctly
        # renamed occurrences must NOT be hard matches.
        sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, CLEAN_METADATA, CLEAN_SNIPPET, CLEAN_PROV)
        r = mod.verify(sg, fg, OLD, NEW, ["1.0.0"])
        assert r["hard_matches"] == []

    def test_english_word_not_hard(self, tmp_path):
        # "renamed" in the body is a different word, not a name token.
        body_md = "---\nname: rename-skill\ndescription: x\n---\n# rename-skill\nrenamed elsewhere\n"
        sg, fg = build_tree(tmp_path, "1.0.0", body_md, CLEAN_METADATA, CLEAN_SNIPPET, CLEAN_PROV)
        r = mod.verify(sg, fg, OLD, NEW, ["1.0.0"])
        assert r["clean"] is True
        assert r["body_warnings"] == []

    def test_frontmatter_leak_is_hard(self, tmp_path):
        bad = "---\nname: rename\ndescription: x\n---\n# body\n"
        sg, fg = build_tree(tmp_path, "1.0.0", bad, CLEAN_METADATA, CLEAN_SNIPPET, CLEAN_PROV)
        r = mod.verify(sg, fg, OLD, NEW, ["1.0.0"])
        assert r["clean"] is False
        regions = [m["region"] for m in r["hard_matches"]]
        assert "skill-frontmatter" in regions

    def test_metadata_leak_is_hard(self, tmp_path):
        bad_meta = json.dumps({"name": "rename", "version": "1.0.0"}, indent=2) + "\n"
        sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, bad_meta, CLEAN_SNIPPET, CLEAN_PROV)
        r = mod.verify(sg, fg, OLD, NEW, ["1.0.0"])
        assert r["clean"] is False
        assert any(m["region"] == "metadata-json" for m in r["hard_matches"])

    def test_snippet_leak_is_hard(self, tmp_path):
        bad_snip = "[rename v1.0.0]|root: .claude/skills/rename/\n"
        sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, CLEAN_METADATA, bad_snip, CLEAN_PROV)
        r = mod.verify(sg, fg, OLD, NEW, ["1.0.0"])
        assert r["clean"] is False
        assert any(m["region"] == "context-snippet" for m in r["hard_matches"])

    def test_provenance_leak_is_hard(self, tmp_path):
        bad_prov = json.dumps({"skill_name": "rename"}, indent=2) + "\n"
        sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, CLEAN_METADATA, CLEAN_SNIPPET, bad_prov)
        r = mod.verify(sg, fg, OLD, NEW, ["1.0.0"])
        assert r["clean"] is False
        assert any(m["region"] == "provenance-json" for m in r["hard_matches"])

    def test_old_name_dir_present_is_violation(self, tmp_path):
        sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, CLEAN_METADATA, CLEAN_SNIPPET, CLEAN_PROV)
        # Leave an old-name inner dir behind (unrenamed).
        (sg / "1.0.0" / OLD).mkdir()
        r = mod.verify(sg, fg, OLD, NEW, ["1.0.0"])
        assert r["clean"] is False
        assert any(dv["issue"] == "old-name-dir-present" for dv in r["dir_violations"])

    def test_new_name_dir_missing_is_violation(self, tmp_path):
        sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, CLEAN_METADATA, CLEAN_SNIPPET, CLEAN_PROV, inner_name=OLD)
        r = mod.verify(sg, fg, OLD, NEW, ["1.0.0"])
        assert r["clean"] is False
        assert any(dv["issue"] == "new-name-dir-missing" for dv in r["dir_violations"])

    def test_missing_provenance_is_skipped_not_hard(self, tmp_path):
        sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, CLEAN_METADATA, CLEAN_SNIPPET, CLEAN_PROV)
        (fg / "1.0.0" / "provenance-map.json").unlink()
        r = mod.verify(sg, fg, OLD, NEW, ["1.0.0"])
        assert r["clean"] is True
        assert any(s["reason"] == "missing" for s in r["skipped"])

    def test_multiple_versions(self, tmp_path):
        sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, CLEAN_METADATA, CLEAN_SNIPPET, CLEAN_PROV)
        # Add a second version with a leak.
        inner = sg / "0.9.0" / NEW
        inner.mkdir(parents=True)
        (inner / "SKILL.md").write_text(CLEAN_SKILL_MD)
        (inner / "metadata.json").write_text(json.dumps({"name": "rename"}, indent=2))
        (inner / "context-snippet.md").write_text(CLEAN_SNIPPET)
        (fg / "0.9.0").mkdir(parents=True)
        (fg / "0.9.0" / "provenance-map.json").write_text(CLEAN_PROV)
        r = mod.verify(sg, fg, OLD, NEW, ["1.0.0", "0.9.0"])
        assert r["clean"] is False
        assert any(m["version"] == "0.9.0" for m in r["hard_matches"])


class TestCli:
    def _run(self, sg, fg, versions):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(sg), "--forge-group", str(fg),
             "--old-name", OLD, "--new-name", NEW, "--versions", versions],
            capture_output=True, text=True,
        )
        return proc.returncode, json.loads(proc.stdout)

    def test_clean_exit_0(self, tmp_path):
        sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, CLEAN_METADATA, CLEAN_SNIPPET, CLEAN_PROV)
        rc, out = self._run(sg, fg, "1.0.0")
        assert rc == 0
        assert out["clean"] is True

    def test_leak_exit_1(self, tmp_path):
        bad_meta = json.dumps({"name": "rename"}, indent=2)
        sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, bad_meta, CLEAN_SNIPPET, CLEAN_PROV)
        rc, out = self._run(sg, fg, "1.0.0")
        assert rc == 1
        assert out["clean"] is False


# --- Source facts: values that name the upstream source, not the skill -----------

# The keys whose value names the upstream source the skill was made from. A copy
# of the helper's SOURCE_FACT_KEYS, pinned below against it and against the keys
# SKF's writers emit; the rename never changes these values.
SOURCE_FACTS = ("source_repo", "source_root", "source_commit", "source_ref", "source_package", "source_library")

# Every file that says which keys metadata.json and provenance-map.json carry.
# Most write them as JSON ("key": ...); update-skill's write step names each key
# it writes in backticks, in its metadata.json and provenance-map.json sections.
WRITERS = (
    "src/skf-create-skill/assets/skill-sections.md",
    "src/skf-quick-skill/assets/skill-template.md",
    "src/skf-quick-skill/references/compile.md",
    "src/shared/scripts/skf-render-quick-metadata.py",
    "src/skf-create-stack-skill/assets/provenance-map-schema.md",
    "src/skf-create-stack-skill/assets/stack-skill-template.md",
    "src/knowledge/provenance-tracking.md",
    "src/skf-update-skill/references/write.md",
)
UPDATE_WRITE = "src/skf-update-skill/references/write.md"
UPDATE_WRITE_SECTIONS = ("### 2. Write Updated metadata.json", "### 4. Write Updated evidence-report.md")
# Names in those sections of update-skill's write step that are not keys it
# writes: a value step 1 records, and a field of a test report's gap.
UPDATE_WRITE_NOT_KEYS = {"source_version_detected", "source_citation"}
# The writers' other source_* keys: an authority enum, and a place inside the
# source rather than the source itself.
NOT_SOURCE_NAMES = {"source_authority", "source_file", "source_line"}


def _writer_keys(rel):
    """The source_* keys the writer `rel` puts in metadata.json or provenance-map.json."""
    text = (REPO / rel).read_text(encoding="utf-8")
    if rel != UPDATE_WRITE:
        return set(re.findall(r'"(source_[a-z_]+)"\s*:', text))
    start, end = UPDATE_WRITE_SECTIONS
    assert text.count(start) == 1 and text.count(end) == 1
    named = set(re.findall(r"`(source_[a-z_]+)`", text[text.index(start):text.index(end)]))
    assert UPDATE_WRITE_NOT_KEYS <= named, "a name classified as not a key is gone: drop it from the list"
    return named - UPDATE_WRITE_NOT_KEYS

# A value holding the old name as a complete token, as a library, repository,
# path or tag named like the skill does.
NAMED = f"https://github.com/acme/{OLD}"


def _verify_json(tmp_path, metadata=CLEAN_METADATA, provenance=CLEAN_PROV):
    sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, metadata, CLEAN_SNIPPET, provenance)
    return mod.verify(sg, fg, OLD, NEW, ["1.0.0"]), sg / "1.0.0" / NEW / "metadata.json", fg / "1.0.0" / "provenance-map.json"


def _dump(doc):
    return json.dumps(doc, indent=2) + "\n"


class TestSourceFacts:
    def test_the_copy_is_the_helpers_key_set(self):
        assert mod.SOURCE_FACT_KEYS == frozenset(SOURCE_FACTS)

    def test_the_keys_are_the_writers_names_for_the_source(self):
        """Every source_* key a writer emits is classified: a new one fails here until it is."""
        written = set()
        for rel in WRITERS:
            keys = _writer_keys(rel)
            assert keys, f"{rel} yields no source_* key: the pin would not see a new one there"
            written |= keys
        assert written == set(SOURCE_FACTS) | NOT_SOURCE_NAMES
        assert not set(SOURCE_FACTS) & NOT_SOURCE_NAMES

    def test_update_skills_write_step_is_read(self):
        """write.md names its keys in backticks; the pin reads them, so a new one there fails too."""
        assert _writer_keys(UPDATE_WRITE) == {"source_commit", "source_ref", "source_root", "source_file",
                                              "source_line"}

    @pytest.mark.parametrize("nested", [False, True], ids=["top-level", "nested"])
    @pytest.mark.parametrize("key", SOURCE_FACTS)
    def test_a_source_fact_naming_the_old_name_is_skipped(self, tmp_path, key, nested):
        field = {"entries": [{"export_name": "x", key: NAMED}]} if nested else {key: NAMED}
        r, _, _ = _verify_json(tmp_path, _dump({"name": NEW, **field}), _dump({"skill_name": NEW, **field}))
        assert r["clean"] is True and r["hard_matches"] == []

    def test_the_forms_writers_use(self, tmp_path):
        """Lists and maps of repositories, a tag with the package prefix, the library per entry."""
        metadata = _dump({
            "name": NEW, "source_repo": NAMED, "source_root": f"/home/me/.skf/workspace/acme/{OLD}",
            "source_commit": "2b5553f32895739befe549da1ceb6dee4fa1cd0b", "source_ref": f"{OLD}/v1.0.0",
            "source_package": OLD,
        })
        provenance = _dump({
            "skill_name": NEW, "source_repo": [NAMED, "https://github.com/acme/other"],
            "source_commit": {f"acme/{OLD}": "2b5553f3", "acme/other": "9c1e0a7d"}, "source_ref": f"{OLD}@1.0.0",
            "entries": [{"export_name": "slugify", "source_library": OLD, "source_file": "src/core.py"},
                        {"export_name": "truncate", "source_library": OLD, "source_file": "src/core.py"}],
        })
        r, _, _ = _verify_json(tmp_path, metadata, provenance)
        assert r["clean"] is True and r["hard_matches"] == []

    @pytest.mark.parametrize("doc, text", [
        ({"description": f"Use when writing {OLD} code."}, f'"description": "Use when writing {OLD} code."'),
        ({"doc_sources": [{"url": f"https://{OLD}.dev/docs"}]}, f'"url": "https://{OLD}.dev/docs"'),
        ({"entries": [{"source_library": OLD, "source_file": f"packages/{OLD}/index.ts"}]},
         f'"source_file": "packages/{OLD}/index.ts"'),
        ({"update_source": f"test-report {OLD} 79.68% FAIL"}, f'"update_source": "test-report {OLD} 79.68% FAIL"'),
        ({"notes": f"source_repo: {OLD}"}, f'"notes": "source_repo: {OLD}"'),
        ({OLD: {"source_repo": NAMED}}, f'"{OLD}": {{'),
    ], ids=["description", "doc-url", "source-file", "update-note", "note-quoting-a-key", "key"])
    @pytest.mark.parametrize("region", ["metadata-json", "provenance-json"])
    def test_every_other_value_and_key_still_counts(self, tmp_path, region, doc, text):
        """Only the source-fact values are skipped: the line and text reported are the file's own."""
        name_field = {"name": NEW} if region == "metadata-json" else {"skill_name": NEW}
        content = _dump({**name_field, "source_package": OLD, **doc})
        if region == "metadata-json":
            r, path, _ = _verify_json(tmp_path, metadata=content)
        else:
            r, _, path = _verify_json(tmp_path, provenance=content)
        line = next(n for n, t in enumerate(content.split("\n"), start=1) if t.strip().startswith(text))
        assert r["clean"] is False
        assert r["hard_matches"] == [
            {"version": "1.0.0", "file": str(path), "region": region, "line": line, "text": content.split("\n")[line - 1].strip()}]

    @pytest.mark.parametrize("region", ["metadata-json", "provenance-json"])
    def test_a_match_after_a_multi_line_source_fact_keeps_its_line(self, tmp_path, region):
        """Masking keeps the line breaks inside a skipped value, so a later match reports its own line."""
        name_field = {"name": NEW} if region == "metadata-json" else {"skill_name": NEW}
        content = _dump({
            **name_field,
            "source_repo": [NAMED, "https://github.com/acme/other"],
            "source_commit": {f"acme/{OLD}": "2b5553f3", "acme/other": "9c1e0a7d"},
            "entries": [{"export_name": "slugify", "source_library": OLD, "source_file": f"packages/{OLD}/index.ts"}],
        })
        if region == "metadata-json":
            r, path, _ = _verify_json(tmp_path, metadata=content)
        else:
            r, _, path = _verify_json(tmp_path, provenance=content)
        lines = content.split("\n")
        line = lines.index(f'      "source_file": "packages/{OLD}/index.ts"') + 1
        assert line > 10
        assert r["hard_matches"] == [{"version": "1.0.0", "file": str(path), "region": region, "line": line,
                                      "text": f'"source_file": "packages/{OLD}/index.ts"'}]

    def test_a_line_holding_a_source_fact_and_another_value_counts(self, tmp_path):
        content = '{"name": "rename-skill", "source_package": "rename", "description": "the rename helpers"}\n'
        r, path, _ = _verify_json(tmp_path, metadata=content)
        assert r["hard_matches"] == [
            {"version": "1.0.0", "file": str(path), "region": "metadata-json", "line": 1, "text": content.strip()}]

    def test_a_compact_source_fact_alone_is_skipped(self, tmp_path):
        r, _, _ = _verify_json(tmp_path, metadata='{"name": "rename-skill", "source_package": "rename"}')
        assert r["clean"] is True

    def test_a_value_with_escapes_and_brackets_ends_where_json_says(self, tmp_path):
        content = '{"skill_name": "rename-skill", "source_ref": "a\\"}] rename [{\\\\", "notes": "rename"}\n'
        assert json.loads(content)["source_ref"] == 'a"}] rename [{\\'
        r, _, path = _verify_json(tmp_path, provenance=content)
        assert [(m["line"], m["text"]) for m in r["hard_matches"]] == [(1, content.strip())]
        r, _, _ = _verify_json(tmp_path / "alone", provenance=content.replace('"notes": "rename"', '"notes": "x"'))
        assert r["clean"] is True

    @pytest.mark.parametrize("content", [
        '{\n  "skill_name": "rename-skill",\n  "source_library": "rename",\n',  # truncated
        '{"skill_name": "rename-skill", "source_library": "rename"}\n{"x": 1}\n',  # two documents
        '{"skill_name": "rename-skill", "source_library": "rename",}\n',  # trailing comma
    ], ids=["truncated", "two-documents", "trailing-comma"])
    def test_a_file_that_is_not_json_gets_no_exemption(self, tmp_path, content):
        r, _, path = _verify_json(tmp_path, provenance=content)
        assert r["clean"] is False
        assert [m["text"] for m in r["hard_matches"]] == [
            t.strip() for t in content.split("\n") if re.search(r'"rename"', t)]

    def test_the_snippet_and_frontmatter_get_no_exemption(self, tmp_path):
        """The exemption is for the two JSON files: elsewhere `source_repo: <old>` is a leftover."""
        skill_md = f"---\nname: {NEW}\nsource_repo: {NAMED}\n---\n# body\n"
        snippet = CLEAN_SNIPPET + f'|source_repo: "{NAMED}"\n'
        sg, fg = build_tree(tmp_path, "1.0.0", skill_md, CLEAN_METADATA, snippet, CLEAN_PROV)
        r = mod.verify(sg, fg, OLD, NEW, ["1.0.0"])
        assert sorted(m["region"] for m in r["hard_matches"]) == ["context-snippet", "skill-frontmatter"]

    def test_cli_exits_0_on_source_facts(self, tmp_path):
        provenance = _dump({"skill_name": NEW, "entries": [{"export_name": "x", "source_library": OLD}]})
        sg, fg = build_tree(tmp_path, "1.0.0", CLEAN_SKILL_MD, CLEAN_METADATA, CLEAN_SNIPPET, provenance)
        rc, out = TestCli()._run(sg, fg, "1.0.0")
        assert rc == 0 and out["clean"] is True
        assert set(out) == {"status", "old_name", "new_name", "versions", "hard_matches", "body_warnings",
                            "dir_violations", "skipped", "clean"}
