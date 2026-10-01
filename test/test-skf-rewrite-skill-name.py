#!/usr/bin/env python3
"""Tests for skf-rewrite-skill-name.py.

The context-snippet transform must leave nothing skf-verify-no-trace.py
counts as a leftover (rename §5 rolls back on any) in a snippet that follows
SKF's templates, and must change nothing but the places those templates write
the name. So its tests render every snippet template SKF writes from src/,
also with names that are words of the template itself, and run the rewrite
against the verifier's own token rule, whose copy here is pinned by ast
parity. The JSON kinds' --moved-folder paths are tested on the fields real
SKF skills carry, and never touch a value that names the upstream source or a
file in it. A skill named after its library, rendered from create-skill's and
Quick Skill's own writers, renames clean: its source facts stay as they are
and the verifier skips them.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
SCRIPT = SRC / "shared" / "scripts" / "skf-rewrite-skill-name.py"
VERIFY_SCRIPT = SRC / "shared" / "scripts" / "skf-verify-no-trace.py"

spec = importlib.util.spec_from_file_location("skf_rewrite_skill_name", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

_vspec = importlib.util.spec_from_file_location("skf_verify_no_trace_for_rewrite", VERIFY_SCRIPT)
verify_mod = importlib.util.module_from_spec(_vspec)
_vspec.loader.exec_module(verify_mod)


def run_cli(*args):
    """Invoke the script as a subprocess; return (returncode, parsed_stdout_or_None, stderr)."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *[str(a) for a in args]],
        capture_output=True,
        text=True,
    )
    parsed = None
    if proc.stdout.strip():
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            parsed = None
    return proc.returncode, parsed, proc.stderr


OLD = "rename"
NEW = "rename-skill"


# --- Frontmatter transform ----------------------------------------------------


class TestFrontmatter:
    def test_replaces_name_in_frontmatter_only(self):
        content = (
            "---\n"
            "name: rename\n"
            "description: A skill about the rename operation\n"
            "---\n"
            "# rename\n"
            "This body legitimately mentions rename and renamed things.\n"
        )
        new, old, matched = mod.rewrite_frontmatter_name(content, NEW)
        assert matched is True
        assert old == "rename"
        assert "name: rename-skill\n" in new
        # Body mentions preserved verbatim (not substituted).
        assert "This body legitimately mentions rename and renamed things." in new
        # description field untouched even though it contains "rename".
        assert "description: A skill about the rename operation" in new

    def test_substring_key_not_matched(self):
        # `renamed:` and a nested `  name:` must not be mistaken for the top-level name.
        content = (
            "---\n"
            "name: rename\n"
            "metadata:\n"
            "  name: nested-should-not-change\n"
            "renamed: 2020\n"
            "---\n"
            "body\n"
        )
        new, old, matched = mod.rewrite_frontmatter_name(content, NEW)
        assert old == "rename"
        assert "name: rename-skill\n" in new
        assert "  name: nested-should-not-change" in new
        assert "renamed: 2020" in new

    def test_preserves_quotes(self):
        content = "---\nname: 'rename'\ndescription: x\n---\nbody\n"
        new, old, matched = mod.rewrite_frontmatter_name(content, NEW)
        assert old == "rename"
        assert "name: 'rename-skill'\n" in new

    def test_missing_name_field(self):
        content = "---\ndescription: x\n---\nbody\n"
        new, old, matched = mod.rewrite_frontmatter_name(content, NEW)
        assert matched is False
        assert new == content

    def test_no_frontmatter_raises(self):
        with pytest.raises(ValueError):
            mod.rewrite_frontmatter_name("# just a body\n", NEW)

    def test_no_closing_delimiter_raises(self):
        with pytest.raises(ValueError):
            mod.rewrite_frontmatter_name("---\nname: rename\nno closing\n", NEW)


# --- JSON transforms ----------------------------------------------------------


class TestJsonField:
    def test_metadata_name_roundtrip_preserves_key_order(self):
        content = json.dumps(
            {"name": "rename", "version": "1.0.0", "language": "python"}, indent=2
        )
        new, old, matched = mod.rewrite_json_field(content, "name", NEW)
        assert old == "rename"
        assert matched is True
        data = json.loads(new)
        assert data["name"] == NEW
        assert list(data.keys()) == ["name", "version", "language"]
        assert new.endswith("\n")

    def test_provenance_skill_name(self):
        content = json.dumps({"skill_name": "rename", "entries": []}, indent=2)
        new, old, matched = mod.rewrite_json_field(content, "skill_name", NEW)
        assert old == "rename"
        assert json.loads(new)["skill_name"] == NEW

    def test_absent_field_is_set(self):
        content = json.dumps({"version": "1.0.0"}, indent=2)
        new, old, matched = mod.rewrite_json_field(content, "name", NEW)
        assert matched is False
        assert old is None
        assert json.loads(new)["name"] == NEW

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError):
            mod.rewrite_json_field("{not valid", "name", NEW)


# --- Context-snippet transform ------------------------------------------------


class TestContextSnippet:
    def test_header_and_ide_root(self):
        content = "[rename v1.2.0]|root: .windsurf/skills/rename/\n|IMPORTANT: read me\n"
        new, details = mod.rewrite_context_snippet(content, OLD, NEW)
        assert details["header_rewritten"] is True
        assert "[rename-skill v1.2.0]" in new
        assert "root: .windsurf/skills/rename-skill/" in new
        assert details["roots"] == [
            {"old": ".windsurf/skills/rename/", "new": ".windsurf/skills/rename-skill/"}
        ]

    def test_draft_skills_prefix(self):
        content = "[rename v0.1.0]|root: skills/rename/\n"
        new, details = mod.rewrite_context_snippet(content, OLD, NEW)
        assert "root: skills/rename-skill/" in new

    def test_legacy_nested_form_flattens(self):
        content = "[rename v0.1.0]|root: skills/rename/active/rename/\n"
        new, details = mod.rewrite_context_snippet(content, OLD, NEW)
        assert "root: skills/rename-skill/" in new
        assert "active" not in new

    def test_prefix_containing_old_name_preserved(self):
        # A prefix segment that merely contains the old name must survive.
        content = "[rename v1.0.0]|root: .claude/rename-tools/rename/\n"
        new, details = mod.rewrite_context_snippet(content, OLD, NEW)
        assert "root: .claude/rename-tools/rename-skill/" in new

    def test_header_substring_not_matched(self):
        # old_name is a substring of the actual header name -> no change.
        content = "[renamer v1.0.0]|root: .claude/skills/renamer/\n"
        new, details = mod.rewrite_context_snippet(content, OLD, NEW)
        assert new == content
        assert details["header_rewritten"] is False
        assert details["roots"] == []


# --- CLI: atomic write + exit codes -------------------------------------------


class TestCli:
    def test_frontmatter_writes_atomically(self, tmp_path):
        f = tmp_path / "SKILL.md"
        f.write_text("---\nname: rename\ndescription: x\n---\n# rename\nrename body\n")
        rc, out, err = run_cli(f, "--kind", "skill-frontmatter", "--old-name", OLD, "--new-name", NEW)
        assert rc == 0, err
        assert out["changed"] is True
        assert out["wrote"] == str(f)
        text = f.read_text()
        assert "name: rename-skill\n" in text
        assert "rename body" in text  # body preserved

    def test_metadata_cli(self, tmp_path):
        f = tmp_path / "metadata.json"
        f.write_text(json.dumps({"name": "rename", "version": "1.0.0"}, indent=2) + "\n")
        rc, out, err = run_cli(f, "--kind", "metadata-json", "--old-name", OLD, "--new-name", NEW)
        assert rc == 0, err
        assert json.loads(f.read_text())["name"] == NEW

    def test_no_change_no_write(self, tmp_path):
        f = tmp_path / "metadata.json"
        f.write_text(json.dumps({"name": NEW}, indent=2) + "\n")
        rc, out, err = run_cli(f, "--kind", "metadata-json", "--old-name", OLD, "--new-name", NEW)
        assert rc == 0, err
        assert out["changed"] is False
        assert out["wrote"] is None

    def test_dry_run_does_not_write(self, tmp_path):
        f = tmp_path / "SKILL.md"
        original = "---\nname: rename\ndescription: x\n---\nbody\n"
        f.write_text(original)
        rc, out, err = run_cli(
            f, "--kind", "skill-frontmatter", "--old-name", OLD, "--new-name", NEW, "--dry-run"
        )
        assert rc == 0, err
        assert out["dry_run"] is True
        assert "name: rename-skill" in out["new_content"]
        assert f.read_text() == original  # unchanged on disk

    def test_invalid_new_name_exit_1(self, tmp_path):
        f = tmp_path / "metadata.json"
        f.write_text(json.dumps({"name": "rename"}) + "\n")
        rc, out, err = run_cli(f, "--kind", "metadata-json", "--old-name", OLD, "--new-name", "Bad Name")
        assert rc == 1

    def test_missing_target_exit_1(self, tmp_path):
        rc, out, err = run_cli(
            tmp_path / "nope.json", "--kind", "metadata-json", "--old-name", OLD, "--new-name", NEW
        )
        assert rc == 1

    def test_malformed_skill_md_exit_2(self, tmp_path):
        f = tmp_path / "SKILL.md"
        f.write_text("# no frontmatter here\n")
        rc, out, err = run_cli(f, "--kind", "skill-frontmatter", "--old-name", OLD, "--new-name", NEW)
        assert rc == 2

    def test_invalid_json_exit_2(self, tmp_path):
        f = tmp_path / "metadata.json"
        f.write_text("{not valid json")
        rc, out, err = run_cli(f, "--kind", "metadata-json", "--old-name", OLD, "--new-name", NEW)
        assert rc == 2


# --- The snippet transform and the §5 verifier share one token rule ------------


def _top_level_node(path: Path, name: str) -> str:
    """ast.dump of the top-level def named `name` (comments ignored)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.dump(node)
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.dump(node)
    raise AssertionError(f"{name} not found at the top level of {path.name}")


class TestNameTokenParity:
    """The rewriter's copy of the verifier's name-token rule stays identical."""

    def test_copy_is_identical(self):
        assert _top_level_node(SCRIPT, "_name_token_re") == _top_level_node(VERIFY_SCRIPT, "_name_token_re"), (
            "_name_token_re differs between skf-rewrite-skill-name.py and skf-verify-no-trace.py; "
            "keep the copies identical")

    @pytest.mark.parametrize("path", [SCRIPT, VERIFY_SCRIPT], ids=lambda p: p.name)
    def test_copies_carry_keep_identical_notes(self, path):
        text = path.read_text(encoding="utf-8")
        assert "Keep identical to _name_token_re in" in text
        assert "test/test-skf-rewrite-skill-name.py pins the copies" in text

    def test_the_source_fact_keys_are_the_verifiers(self):
        """The paths transform leaves exactly the values the verifier skips, plus the files in the source."""
        assert _top_level_node(SCRIPT, "SOURCE_FACT_KEYS") == _top_level_node(VERIFY_SCRIPT, "SOURCE_FACT_KEYS"), (
            "SOURCE_FACT_KEYS differs between skf-rewrite-skill-name.py and skf-verify-no-trace.py; "
            "keep the copies identical")
        for path in (SCRIPT, VERIFY_SCRIPT):
            text = path.read_text(encoding="utf-8")
            assert "Keep identical to SOURCE_FACT_KEYS in" in text
            assert "test/test-skf-rewrite-skill-name.py pins the copies" in text
        assert mod.UPSTREAM_KEYS == frozenset(UPSTREAM_KEYS)
        assert mod.UPSTREAM_KEYS - verify_mod.SOURCE_FACT_KEYS == {"source_file", "co_import_files"}

    @pytest.mark.parametrize("fn_name", ["rewrite_context_snippet", "_moved_path_re"])
    def test_transforms_match_with_the_copy(self, fn_name):
        """No parallel regex: the snippet and path transforms find the name with _name_token_re."""
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        fn = next(n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == fn_name)
        called = {c.func.id for c in ast.walk(fn)
                  if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
        assert "_name_token_re" in called


# --- Every snippet template SKF writes, rendered --------------------------------

# A template's first line: `[{name-placeholder}[-suffix] v{version...}]|root: ...`.
TEMPLATE_HEADER_RE = re.compile(r"^\[(?P<name>\{[^{}\s]+\}[a-z0-9-]*) v\{[^\]]*\}\]\|root: ")
FENCE_LINE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
# Where SKF's snippet templates live today; a new template must be added here
# (and so to the rename checks below) on purpose.
TEMPLATE_SITES = {
    "src/skf-create-skill/references/compile.md": 1,
    "src/skf-create-skill/assets/skill-sections.md": 1,
    "src/skf-create-skill/assets/compile-assembly-rules.md": 1,
    "src/skf-quick-skill/assets/skill-template.md": 1,
    "src/skf-export-skill/assets/snippet-format.md": 2,
    "src/skf-create-stack-skill/assets/stack-skill-template.md": 1,
    "src/skf-create-stack-skill/references/generate-output.md": 1,
}


class Template(NamedTuple):
    rel: str
    line: int
    name_expr: str  # `{skill-name}` or `{stack_name}`
    text: str


def _snippet_templates() -> list[Template]:
    """Every snippet template in a fenced block of a src/**/*.md file.

    A template runs from its header line to the first blank or fence line.
    """
    found = []
    for path in sorted(SRC.rglob("*.md")):
        rel = path.relative_to(REPO).as_posix()
        lines = path.read_text(encoding="utf-8").split("\n")
        fence = None
        for i, line in enumerate(lines):
            m = FENCE_LINE_RE.match(line)
            if m:
                marker = m.group(1)
                if fence is None:
                    fence = marker
                elif marker[0] == fence[0] and len(marker) >= len(fence) and not line.strip()[len(marker):]:
                    fence = None
                continue
            if fence is None:
                continue
            header = TEMPLATE_HEADER_RE.match(line.strip())
            if not header:
                continue
            indent = len(line) - len(line.lstrip())
            body = []
            for nxt in lines[i:]:
                if not nxt.strip() or FENCE_LINE_RE.match(nxt):
                    break
                body.append(nxt[indent:])
            found.append(Template(rel, i + 1, header.group("name"), "\n".join(body) + "\n"))
    return found


SNIPPET_TEMPLATES = _snippet_templates()


def _render(template: Template, name: str) -> str:
    """The snippet SKF writes from `template` for a skill called `name`."""
    m = re.fullmatch(r"(\{[^{}]+\})([a-z0-9-]*)", template.name_expr)
    placeholder, suffix = m.group(1), m.group(2)
    assert name.endswith(suffix), (name, suffix)
    out = template.text.replace(placeholder, name[: len(name) - len(suffix)])
    out = re.sub(r"\{version[^{}]*\}", "1.4.0", out)
    out = out.replace("{skill_root}", ".claude/skills/")
    return re.sub(r"\{[^{}\n]*\}", "details", out)


def _is_stack(template: Template) -> bool:
    """A stack template: the name it renders always ends in `-stack`."""
    return template.name_expr.endswith("-stack") or template.name_expr == "{stack_name}"


def _name_pairs(template: Template):
    """(old, new) pairs: a name inside the new one, and the new one inside the old."""
    if _is_stack(template):
        return [("acme-stack", "acme-web-stack"), ("web-acme-stack", "acme-stack")]
    return [(OLD, NEW), ("oms-cognee", "cognee")]


def _template_id(template: Template) -> str:
    return f"{template.rel}:{template.line}"


class TestSnippetTemplates:
    def test_template_sites_are_exactly_these(self):
        counts: dict[str, int] = {}
        for t in SNIPPET_TEMPLATES:
            counts[t.rel] = counts.get(t.rel, 0) + 1
        assert counts == TEMPLATE_SITES

    @pytest.mark.parametrize("pair", [0, 1])
    @pytest.mark.parametrize("template", SNIPPET_TEMPLATES, ids=_template_id)
    def test_rewrite_equals_the_template_rendered_with_the_new_name(self, template, pair):
        old, new = _name_pairs(template)[pair]
        before = _render(template, old)
        token = verify_mod._name_token_re(old)
        important = [line for line in before.split("\n") if line.startswith("|IMPORTANT:")]
        assert len(important) == 1 and token.search(important[0]), "the template names the skill on its IMPORTANT line"
        rewritten, details = mod.rewrite_context_snippet(before, old, new)
        assert rewritten == _render(template, new)
        assert not token.search(rewritten), "rename §5 would flag what is left"
        assert details["header_rewritten"] is True
        assert details["mentions"] == len(token.findall(before)) - 1  # every mention but the root's

    @pytest.mark.parametrize("template", SNIPPET_TEMPLATES, ids=_template_id)
    def test_rename_of_a_template_skill_passes_the_commit_gate(self, tmp_path, template):
        """Rename §3 then §5 on a skill whose snippet follows the template: verify exits 0."""
        old, new = _name_pairs(template)[0]
        code, verdict = _rename_and_verify(tmp_path, old, new, _render(template, old))
        assert code == 0 and verdict["clean"] is True, verdict["hard_matches"]

    # A stack's name ends in -stack, which no template word does, so the stack
    # templates have no such name.
    @pytest.mark.parametrize(
        "template", [t for t in SNIPPET_TEMPLATES if t.name_expr.endswith("}") and not _is_stack(t)],
        ids=_template_id)
    def test_a_name_that_is_a_word_of_the_template_changes_only_the_name(self, template):
        """A skill called `api`, `root`, `data`, `md` ...: the template's own words stay.

        The rewrite still equals the template rendered with the new name, so a field
        label (`|api:`, `root:`) or a fixed word ("training data", "SKILL.md") is never
        renamed; §5 then finds the old name in that word and rolls the rename back.
        """
        words = sorted(set(re.findall(r"(?<![a-z0-9-])[a-z][a-z0-9-]*(?![a-z0-9-])", _render(template, "x-y")))
                       - {"x-y"})
        assert {"root", "read", "code", "data", "md"} <= set(words), words
        wrong = []
        for old in words:
            new = old + "-kit"
            rewritten, _ = mod.rewrite_context_snippet(_render(template, old), old, new)
            if rewritten != _render(template, new):
                wrong.append(old)
            assert verify_mod._name_token_re(old).search(rewritten), f"{old}: §5 would let this commit"
        assert not wrong, f"the rewrite changed the template's own words for: {wrong}"

    def test_a_skill_called_like_a_field_label_rolls_back(self, tmp_path):
        """`api` renamed: the snippet keeps its `|api:` label and §5 stops the rename on it."""
        template = next(t for t in SNIPPET_TEMPLATES if t.rel.endswith("skf-create-skill/references/compile.md"))
        code, verdict = _rename_and_verify(tmp_path, "api", "api-client", _render(template, "api"))
        assert code == 1 and verdict["clean"] is False
        assert [(m["region"], m["text"]) for m in verdict["hard_matches"]] == [
            ("context-snippet", "|api: details")]


def _rename_and_verify(tmp_path, old, new, snippet, metadata=None, provenance=None, moved_folders=None):
    """Rename §3 on one version as §1-§2 leave it, then the §5 verifier: (exit code, verdict).

    `moved_folders` defaults to what §3 passes when the forge folder moves: the
    skills folder and the forge folder.
    """
    skills, forge = tmp_path / "skills", tmp_path / "forge-data"
    skill_group, forge_group = skills / new, forge / new
    package = skill_group / "1.4.0" / new
    package.mkdir(parents=True)
    (forge_group / "1.4.0").mkdir(parents=True)
    if moved_folders is None:
        moved_folders = [str(skills), str(forge)]
    files = {
        package / "SKILL.md": (f"---\nname: {old}\ndescription: Use when x.\n---\n# {old}\n", "skill-frontmatter"),
        package / "metadata.json": (
            json.dumps(metadata or {"name": old, "version": "1.4.0"}, indent=2) + "\n", "metadata-json"),
        package / "context-snippet.md": (snippet, "context-snippet"),
        forge_group / "1.4.0" / "provenance-map.json": (
            json.dumps(provenance or {"skill_name": old, "entries": []}, indent=2) + "\n", "provenance-json"),
    }
    for path, (text, kind) in files.items():
        path.write_bytes(text.encode("utf-8"))
        extra = []
        if kind.endswith("-json"):
            for folder in moved_folders:
                extra += ["--moved-folder", folder]
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(path), "--kind", kind, "--old-name", old, "--new-name", new, *extra],
            capture_output=True, encoding="utf-8")
        assert proc.returncode == 0, proc.stderr
    proc = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), str(skill_group), "--forge-group", str(forge_group),
         "--old-name", old, "--new-name", new, "--versions", "1.4.0"],
        capture_output=True, encoding="utf-8")
    return proc.returncode, json.loads(proc.stdout)


# The snippet of a real SKF skill (oh-my-skills' oms-uitripled 0.1.0), the one
# whose rename rolled back at §5 in the live run. Its IMPORTANT line names the
# library ("uitripled") where the template names the skill; that mention is not
# the old name as a token and stays.
LIVE_SNIPPET = (
    "[oms-uitripled v0.1.0]|root: skills/oms-uitripled/\n"
    "|IMPORTANT: oms-uitripled v0.1.0 — read SKILL.md before writing uitripled code. Do NOT rely on training data.\n"
    "|quick-start:SKILL.md#quick-start\n"
    "|api: ThemeProvider, useTheme, UILibraryProvider, useUILibrary, cn(), sanitizeSlug(), generateUniqueSlug(), "
    "GAP_VALUES, generateGridCode(), mergeComponentImports(), add()\n"
    "|gotchas: Copy-paste distribution — NEVER barrel-import from @uitripled/react-shadcn (src/index.ts empty by "
    "design); all 171 entries require `\"use client\"` because every one depends on framer-motion.\n"
)


class TestSnippetMentions:
    def test_live_run_snippet(self):
        new, details = mod.rewrite_context_snippet(LIVE_SNIPPET, "oms-uitripled", "uitripled-kit")
        expected = LIVE_SNIPPET.replace(
            "[oms-uitripled v0.1.0]|root: skills/oms-uitripled/", "[uitripled-kit v0.1.0]|root: skills/uitripled-kit/"
        ).replace("|IMPORTANT: oms-uitripled v0.1.0", "|IMPORTANT: uitripled-kit v0.1.0")
        assert new == expected
        assert details["mentions"] == 2
        assert not verify_mod._name_token_re("oms-uitripled").search(new)

    def test_root_prefix_is_never_rewritten(self):
        """A prefix that is the old name stays: only the trailing segment is the skill's."""
        content = (
            "[skills v1.0.0]|root: .claude/skills/skills/\n"
            "|IMPORTANT: skills v1.0.0 — read SKILL.md before writing skills code.\n"
        )
        new, details = mod.rewrite_context_snippet(content, "skills", "skill-pack")
        assert new == (
            "[skill-pack v1.0.0]|root: .claude/skills/skill-pack/\n"
            "|IMPORTANT: skill-pack v1.0.0 — read SKILL.md before writing skill-pack code.\n"
        )
        assert details["mentions"] == 3
        assert details["roots"] == [{"old": ".claude/skills/skills/", "new": ".claude/skills/skill-pack/"}]

    def test_longer_names_that_contain_the_old_name_stay(self):
        content = "[rename v1.0.0]|root: skills/rename/\n|IMPORTANT: rename v1.0.0 — see renamer and rename-skill.\n"
        new, _ = mod.rewrite_context_snippet(content, OLD, NEW)
        assert new.endswith("|IMPORTANT: rename-skill v1.0.0 — see renamer and rename-skill.\n")

    def test_cli_reports_the_mentions(self, tmp_path):
        f = tmp_path / "context-snippet.md"
        f.write_bytes(_render(SNIPPET_TEMPLATES[0], OLD).encode("utf-8"))
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(f), "--kind", "context-snippet", "--old-name", OLD, "--new-name", NEW],
            capture_output=True, encoding="utf-8")
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert out["mentions_rewritten"] == 3  # the header and the IMPORTANT line's two
        assert out["header_rewritten"] is True and out["matched"] is True and out["changed"] is True

    def test_a_mention_alone_counts_as_matched(self, tmp_path):
        f = tmp_path / "context-snippet.md"
        f.write_bytes("[rename-skill v1.0.0]|root: skills/rename-skill/\n|IMPORTANT: rename v1.0.0\n".encode("utf-8"))
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(f), "--kind", "context-snippet", "--old-name", OLD, "--new-name", NEW],
            capture_output=True, encoding="utf-8")
        out = json.loads(proc.stdout)
        assert out["matched"] is True and out["header_rewritten"] is False and out["mentions_rewritten"] == 1
        assert f.read_text(encoding="utf-8").endswith("|IMPORTANT: rename-skill v1.0.0\n")

    def test_a_mention_outside_the_template_slots_stays_and_rolls_back(self, tmp_path):
        """A later line that names the skill is the library's content: §5 stops the rename on it."""
        template = next(t for t in SNIPPET_TEMPLATES if t.rel.endswith("skf-export-skill/assets/snippet-format.md"))
        gotchas = "|gotchas: oms-cognee.add() needs await"
        snippet = _render(template, "oms-cognee").replace("|gotchas: details", gotchas)
        assert snippet.count(gotchas) == 1
        new, details = mod.rewrite_context_snippet(snippet, "oms-cognee", "cognee")
        assert new == _render(template, "cognee").replace("|gotchas: details", gotchas)
        assert details["mentions"] == 3  # the header and the IMPORTANT line's two
        code, verdict = _rename_and_verify(tmp_path, "oms-cognee", "cognee", snippet)
        assert code == 1 and [(m["region"], m["text"]) for m in verdict["hard_matches"]] == [
            ("context-snippet", gotchas)]


# --- --moved-folder: paths into the folders the rename moves ---------------------

# The fields real SKF skills carry, from update-skill runs (oh-my-skills:
# update_operations[].test_report in oms-uitripled, which stopped the live
# rename at §5; last_update.test_report in oms-cognee;
# update_metadata.test_report_path in oms-storybook-react-vite). Each is a path
# into the forge folder that §3 moves and §8 deletes, and §5 flags each one.
LEGACY_PROVENANCE = {
    "provenance_version": "2.0",
    "skill_name": "oms-uitripled",
    "source_repo": "https://github.com/moumen-soliman/uitripled",
    "update_operations": [{
        "trigger": "test-report (gap-driven)",
        "test_report": "forge-data/oms-uitripled/0.1.0/test-report-oms-uitripled.md",
        "files_changed": 2,
    }],
    "last_update": {"trigger": "from-test-report",
                    "test_report": "forge-data/oms-uitripled/0.1.0/test-report-oms-uitripled.md"},
    "update_metadata": {
        "test_report_path": "forge-data/oms-uitripled/0.1.0/test-report-oms-uitripled.md",
        "notes": "Second gap-driven pass — see forge-data/oms-uitripled/0.1.0 for the report.",
    },
    "entries": [{"export_name": "ThemeProvider", "source_library": "@uitripled/react-shadcn",
                 "source_file": "packages/components/react-shadcn/src/components/theme-provider.tsx"}],
}


# The values the paths transform never changes: the verifier's source facts,
# and the files in the source. A copy of the helper's UPSTREAM_KEYS, pinned in
# TestNameTokenParity.
UPSTREAM_KEYS = ("source_repo", "source_root", "source_commit", "source_ref", "source_package", "source_library",
                 "source_file", "co_import_files")


class TestMovedPaths:
    OLD, NEW = "oms-uitripled", "uitripled-kit"

    FOLDERS = ("/home/me/proj/forge-data", "/home/me/proj/skills", "C:\\proj\\forge-data")

    def _rewrite(self, value, folders=FOLDERS, old=None, new=None):
        text = json.dumps({"v": value}, indent=2) + "\n"
        out, paths = mod.rewrite_moved_paths(text, old or self.OLD, new or self.NEW, list(folders))
        return json.loads(out)["v"], paths

    def test_legacy_test_report_fields(self):
        text = json.dumps(LEGACY_PROVENANCE, indent=2) + "\n"
        out, paths = mod.rewrite_moved_paths(text, self.OLD, self.NEW, ["forge-data", "skills"])
        data = json.loads(out)
        report = "forge-data/uitripled-kit/0.1.0/test-report-oms-uitripled.md"
        assert data["update_operations"][0]["test_report"] == report
        assert data["last_update"]["test_report"] == report
        assert data["update_metadata"]["test_report_path"] == report
        assert data["update_metadata"]["notes"] == "Second gap-driven pass — see forge-data/uitripled-kit/0.1.0 for the report."
        expected = json.loads(json.dumps(LEGACY_PROVENANCE))
        for place in (expected["update_operations"][0], expected["last_update"]):
            place["test_report"] = report
        expected["update_metadata"]["test_report_path"] = report
        expected["update_metadata"]["notes"] = data["update_metadata"]["notes"]
        assert data == expected and list(data) == list(LEGACY_PROVENANCE)  # nothing else, key order kept
        assert len(paths) == 4

    @pytest.mark.parametrize("value, expected", [
        ("skills/oms-uitripled/0.1.0/oms-uitripled/SKILL.md", "skills/uitripled-kit/0.1.0/uitripled-kit/SKILL.md"),
        ("skills/oms-uitripled/active/oms-uitripled/", "skills/uitripled-kit/active/uitripled-kit/"),
        ("skills/oms-uitripled/0.1.0/references/api.md", "skills/uitripled-kit/0.1.0/references/api.md"),
        ("skills/oms-uitripled/0.1.0/oms-uitripled.md", "skills/uitripled-kit/0.1.0/oms-uitripled.md"),
        ("/home/me/proj/forge-data/oms-uitripled/0.1.0/x.md", "/home/me/proj/forge-data/uitripled-kit/0.1.0/x.md"),
        ("C:\\proj\\forge-data\\oms-uitripled\\0.1.0\\x.md", "C:\\proj\\forge-data\\uitripled-kit\\0.1.0\\x.md"),
        ("forge-data/oms-uitripled", "forge-data/uitripled-kit"),
        ("./forge-data/oms-uitripled/0.1.0/x.md", "./forge-data/uitripled-kit/0.1.0/x.md"),
        ("see forge-data/oms-uitripled/0.1.0 for the report", "see forge-data/uitripled-kit/0.1.0 for the report"),
    ])
    def test_paths_into_a_moved_folder(self, value, expected):
        assert self._rewrite(value)[0] == expected

    @pytest.mark.parametrize("value, expected", [
        ("_bmad-output/skills/oms-uitripled/0.1.0/oms-uitripled/SKILL.md",
         "_bmad-output/skills/uitripled-kit/0.1.0/uitripled-kit/SKILL.md"),
        ("skills/oms-uitripled/0.1.0/SKILL.md", "skills/uitripled-kit/0.1.0/SKILL.md"),
        ("/home/me/proj/_bmad-output/skills/oms-uitripled/", "/home/me/proj/_bmad-output/skills/uitripled-kit/"),
        ("/home/me/other/skills/oms-uitripled/", "/home/me/other/skills/oms-uitripled/"),
    ])
    def test_a_nested_folder_matches_as_its_last_components_or_in_full(self, value, expected):
        assert self._rewrite(value, folders=("/home/me/proj/_bmad-output/skills",))[0] == expected

    @pytest.mark.parametrize("value", [
        "https://github.com/acme/oms-uitripled",  # not under a moved folder
        "my-forge-data/oms-uitripled/0.1.0/x.md",  # another folder
        "forge-data/oms-uitripled-v2/0.1.0/x.md",  # a longer name
        "forge-data/oms-uitripled.bak/x.md",  # not the folder's own segment
        "test-report oms-uitripled 79.68% FAIL",  # prose, not a path
        "forge-data/other/oms-uitripled/x.md",  # the name deeper than the skill folder
        "https://github.com/skills/oms-uitripled",  # a repository of an org called like the folder
        "https://github.com/acme/skills/oms-uitripled/blob/main/README.md",  # a URL through such a folder
        "/home/me/.skf/workspace/repos/github.com/skills/oms-uitripled",  # a clone under such an org
        "/elsewhere/forge-data/oms-uitripled/x.md",  # an absolute path into another forge folder
        "D:\\other\\forge-data\\oms-uitripled\\x.md",  # the same on Windows
        "docs/authoritative/skills/oms-uitripled/llms.txt",  # a promoted doc's namespaced source path
        "vendor/skills/oms-uitripled/x.py",  # the folder's name further in
    ])
    def test_everything_else_stays(self, value):
        assert self._rewrite(value) == (value, [])

    @pytest.mark.parametrize("nested", [False, True], ids=["top-level", "nested"])
    @pytest.mark.parametrize("key", UPSTREAM_KEYS)
    def test_the_upstream_values_stay(self, key, nested):
        """A value naming the source or a file in it is the source's layout, even as a path into a moved folder."""
        value = "skills/oms-uitripled/scripts/fill.py"
        if key == "co_import_files":
            value = [{"file": value, "line": 3}]
        doc = {"integrations": [{"libraries": ["a"], key: value}]} if nested else {key: value}
        text = json.dumps(doc, indent=2) + "\n"
        assert mod.rewrite_moved_paths(text, self.OLD, self.NEW, self.FOLDERS) == (text, [])
        # The same path under another key is a path into the moved folder.
        other = text.replace(f'"{key}"', '"test_report"')
        assert mod.rewrite_moved_paths(other, self.OLD, self.NEW, self.FOLDERS)[1] != []

    def test_keys_stay(self):
        text = json.dumps({"forge-data/oms-uitripled/x": 1}, indent=2) + "\n"
        assert mod.rewrite_moved_paths(text, self.OLD, self.NEW, ["forge-data"]) == (text, [])

    def test_cli_takes_the_folders_as_paths(self, tmp_path):
        f = tmp_path / "provenance-map.json"
        f.write_bytes((json.dumps(LEGACY_PROVENANCE, indent=2) + "\n").encode("utf-8"))
        rc, out, err = run_cli(f, "--kind", "provenance-json", "--old-name", self.OLD, "--new-name", self.NEW,
                               "--moved-folder", str(tmp_path / "skills") + os.sep,
                               "--moved-folder", str(tmp_path / "forge-data"))
        assert rc == 0, err
        assert out["matched"] is True and len(out["paths_rewritten"]) == 4
        assert out["paths_rewritten"][0] == {
            "old": "forge-data/oms-uitripled/0.1.0/test-report-oms-uitripled.md",
            "new": "forge-data/uitripled-kit/0.1.0/test-report-oms-uitripled.md"}
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["skill_name"] == self.NEW and not verify_mod._name_token_re(self.OLD).search(json.dumps(data))

    def test_cli_without_folders_changes_no_path(self, tmp_path):
        f = tmp_path / "provenance-map.json"
        f.write_bytes((json.dumps(LEGACY_PROVENANCE, indent=2) + "\n").encode("utf-8"))
        rc, out, err = run_cli(f, "--kind", "provenance-json", "--old-name", self.OLD, "--new-name", self.NEW)
        assert rc == 0, err
        assert out["paths_rewritten"] == []
        assert json.loads(f.read_text(encoding="utf-8"))["last_update"] == LEGACY_PROVENANCE["last_update"]

    @pytest.mark.parametrize("kind", ["skill-frontmatter", "context-snippet"])
    def test_cli_refuses_folders_for_the_text_kinds(self, tmp_path, kind):
        f = tmp_path / "file.md"
        f.write_bytes(b"---\nname: oms-uitripled\n---\n")
        rc, out, err = run_cli(f, "--kind", kind, "--old-name", self.OLD, "--new-name", self.NEW,
                               "--moved-folder", str(tmp_path))
        assert rc == 1 and "--moved-folder" in err
        assert f.read_bytes() == b"---\nname: oms-uitripled\n---\n"

    def test_rename_of_a_skill_with_legacy_fields_passes_the_commit_gate(self, tmp_path):
        """The live run's oms-uitripled: its snippet and its recorded test report path."""
        metadata = {"name": self.OLD, "version": "1.4.0",
                    "last_test_report": "forge-data/oms-uitripled/1.4.0/test-report-oms-uitripled.md"}
        code, verdict = _rename_and_verify(tmp_path, self.OLD, self.NEW, LIVE_SNIPPET, metadata, LEGACY_PROVENANCE)
        assert code == 0 and verdict["clean"] is True, verdict["hard_matches"]

    def test_a_forge_folder_left_in_place_keeps_its_paths(self, tmp_path):
        """Without the forge folder among the moved ones, §5 still reports the paths into it."""
        code, verdict = _rename_and_verify(tmp_path, self.OLD, self.NEW, LIVE_SNIPPET, None, LEGACY_PROVENANCE,
                                           moved_folders=[str(tmp_path / "skills")])
        assert code == 1
        assert {m["region"] for m in verdict["hard_matches"]} == {"provenance-json"}


# --- A skill SKF's own writers made, named after its library ----------------------

CREATE_SECTIONS = "src/skf-create-skill/assets/skill-sections.md"
DOC_SOURCES_STEP = REPO / "src" / "skf-create-skill" / "references" / "step-doc-sources.md"
QUICK_METADATA = SRC / "shared" / "scripts" / "skf-render-quick-metadata.py"

_dspec = importlib.util.spec_from_file_location("skf_detect_docs_for_rewrite",
                                                SRC / "shared" / "scripts" / "skf-detect-docs.py")
detect_docs = importlib.util.module_from_spec(_dspec)
_dspec.loader.exec_module(detect_docs)


def _template_json(rel: str, heading: str):
    """The ```json template under `heading` in a src file, its `//` comment lines dropped."""
    text = (REPO / rel).read_text(encoding="utf-8")
    assert text.count(heading) == 1, heading
    block = re.search(r"^```json\n(.*?)^```", text[text.index(heading):], re.S | re.M).group(1)
    return json.loads("\n".join(line for line in block.split("\n") if not line.strip().startswith("//")))


def _template_optional(rel: str, heading: str, key: str):
    """The value of an optional `// "key": ...` line of the ```json template under `heading`."""
    text = (REPO / rel).read_text(encoding="utf-8")
    block = re.search(r"^```json\n(.*?)^```", text[text.index(heading):], re.S | re.M).group(1)
    lines = [line.strip() for line in block.split("\n") if line.strip().startswith(f'// "{key}":')]
    assert len(lines) == 1, key
    return json.loads("{" + lines[0][len("//"):].rstrip(",") + "}")[key]


def _fill(node):
    """Every `{placeholder}` of a template becomes `details`, nested ones included."""
    if isinstance(node, dict):
        return {key: _fill(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_fill(value) for value in node]
    if isinstance(node, str):
        while (filled := re.sub(r"\{[^{}]*\}", "details", node)) != node:
            node = filled
    return node


def _create_skill_json(name: str, repo: str = "acme/lib"):
    """metadata.json and provenance-map.json as create-skill's templates write them for single skill `name`.

    The source is the GitHub repository `repo` (the live run's was acme/lib),
    cloned where SKF keeps its workspace. Each provenance entry's
    source_library takes the template's own default, the skill name; a single
    skill omits integrations and constituents; doc_sources holds the README
    entry step-doc-sources §3 adds for every repository.
    """
    sections = (REPO / CREATE_SECTIONS).read_text(encoding="utf-8")
    assert '"source_library": "{library-name — defaults to skill name for single skills}"' in sections
    doc_step = DOC_SOURCES_STEP.read_text(encoding="utf-8")
    assert "uv run {detectDocsHelper} readme-entry" in doc_step
    source = {"source_repo": f"https://github.com/{repo}",
              "source_commit": "2b5553f32895739befe549da1ceb6dee4fa1cd0b", "source_ref": "v1.0.0"}
    metadata = _fill(_template_json(CREATE_SECTIONS, "## metadata.json Structure"))
    metadata.update(name=name, source_root=f"/home/me/.skf/workspace/repos/github.com/{repo}", **source)
    readme = _fill(_template_optional(CREATE_SECTIONS, "## metadata.json Structure", "doc_sources")[0])
    # The URL readme-entry builds from a tree whose README is README.md, as this checkout's is.
    readme.update(url=detect_docs.readme_url(source["source_repo"], source["source_ref"], str(REPO)),
                  detected_via=detect_docs.README_ALWAYS_DETECTED_VIA)
    assert readme["url"] == f"https://raw.githubusercontent.com/{repo}/{source['source_ref']}/README.md"
    metadata["doc_sources"] = [readme]
    provenance = _fill(_template_json(CREATE_SECTIONS, "## provenance-map.json Structure"))
    del provenance["integrations"], provenance["constituents"]
    provenance.update(skill_name=name, **source)
    for entry in provenance["entries"]:
        entry["source_library"] = name
    return metadata, provenance


def _snippet(rel_suffix: str, name: str) -> str:
    return _render(next(t for t in SNIPPET_TEMPLATES if t.rel.endswith(rel_suffix)), name)


class TestSkillNamedAfterItsLibrary:
    """Rename §3 then §5 on what SKF's writers produce for a skill that shares its library's name."""

    OLD, NEW = "acme-lib", "acme-str"  # the live run's create-skill skill

    def _after(self, tmp_path, new=None):
        """The renamed metadata.json and provenance-map.json."""
        new = new or self.NEW
        return (json.loads((tmp_path / "skills" / new / "1.4.0" / new / "metadata.json").read_text(encoding="utf-8")),
                json.loads((tmp_path / "forge-data" / new / "1.4.0" / "provenance-map.json").read_text(encoding="utf-8")))

    def test_a_create_skill_skill_renames_clean(self, tmp_path):
        metadata, provenance = _create_skill_json(self.OLD)
        snippet = _snippet("skf-create-skill/references/compile.md", self.OLD)
        code, verdict = _rename_and_verify(tmp_path, self.OLD, self.NEW, snippet, metadata, provenance)
        assert code == 0 and verdict["clean"] is True, verdict["hard_matches"]
        assert [w["text"] for w in verdict["body_warnings"]] == [f"# {self.OLD}"]
        meta_after, after = self._after(tmp_path)
        assert after["skill_name"] == self.NEW
        # The rename leaves the library's name as it is.
        assert [e["source_library"] for e in after["entries"]] == [self.OLD] * len(provenance["entries"])
        assert after == {**provenance, "skill_name": self.NEW}
        assert meta_after == {**metadata, "name": self.NEW}

    def test_a_create_skill_skill_named_like_its_repository_stops_on_the_readme_url(self, tmp_path):
        """Pinned as it is: the README URL create-skill records is a value the check does not skip.

        source_repo and source_root name the repository too and are skipped;
        the doc_sources URL is not a source-fact key, so the rename rolls back
        on it, with every file as it was.
        """
        metadata, provenance = _create_skill_json(self.OLD, repo=f"acme/{self.OLD}")
        snippet = _snippet("skf-create-skill/references/compile.md", self.OLD)
        code, verdict = _rename_and_verify(tmp_path, self.OLD, self.NEW, snippet, metadata, provenance)
        assert code == 1
        assert [(m["region"], m["text"]) for m in verdict["hard_matches"]] == [
            ("metadata-json", f'"url": "https://raw.githubusercontent.com/acme/{self.OLD}/v1.0.0/README.md",')]

    def test_source_values_that_hold_a_moved_folder_path_stay(self, tmp_path):
        """A repository of an org called `skills`: §3 changes none of its values, and §5 reports the README URL.

        The source facts are skipped by §5, so only the URL, which also stays
        as it was, stops the rename.
        """
        metadata, provenance = _create_skill_json(self.OLD, repo=f"skills/{self.OLD}")
        metadata["source_ref"] = provenance["source_ref"] = f"skills/{self.OLD}/v1.0.0"
        snippet = _snippet("skf-create-skill/references/compile.md", self.OLD)
        code, verdict = _rename_and_verify(tmp_path, self.OLD, self.NEW, snippet, metadata, provenance)
        meta_after, after = self._after(tmp_path)
        assert meta_after == {**metadata, "name": self.NEW}
        assert after == {**provenance, "skill_name": self.NEW}
        assert code == 1
        assert [(m["region"], m["text"]) for m in verdict["hard_matches"]] == [
            ("metadata-json", f'"url": "https://raw.githubusercontent.com/skills/{self.OLD}/v1.0.0/README.md",')]

    def test_a_source_file_under_a_folder_called_like_the_skills_folder_stays_and_rolls_back(self, tmp_path):
        """A skill collection keeps its packages under skills/<name>/: those paths are the source's, not SKF's."""
        old, new = "pdf", "pdf-forms"
        metadata, provenance = _create_skill_json(old, repo="acme/agent-skills")
        script = _fill(_template_optional(CREATE_SECTIONS, "## metadata.json Structure", "scripts")[0])
        script.update(file="scripts/fill.py", source_file=f"skills/{old}/scripts/fill.py")
        metadata["scripts"] = [script]
        provenance["file_entries"][0].update(file_name="scripts/fill.py", source_file=f"skills/{old}/scripts/fill.py")
        snippet = _snippet("skf-create-skill/references/compile.md", old)
        code, verdict = _rename_and_verify(tmp_path, old, new, snippet, metadata, provenance)
        meta_after, after = self._after(tmp_path, new)
        assert meta_after == {**metadata, "name": new}
        assert after == {**provenance, "skill_name": new}
        assert code == 1
        assert [(m["region"], m["text"]) for m in verdict["hard_matches"]] == [
            ("metadata-json", f'"source_file": "skills/{old}/scripts/fill.py",'),
            ("provenance-json", f'"source_file": "skills/{old}/scripts/fill.py",')]

    @pytest.mark.parametrize("where", ["metadata-description", "provenance-source-file"])
    def test_a_value_outside_the_source_facts_still_rolls_back(self, tmp_path, where):
        metadata, provenance = _create_skill_json(self.OLD)
        if where == "metadata-description":
            metadata["description"] = f"Text utilities from the {self.OLD} package."
            expected = ("metadata-json", f'"description": "Text utilities from the {self.OLD} package.",')
        else:
            provenance["entries"][0]["source_file"] = f"src/{self.OLD}/core.py"
            expected = ("provenance-json", f'"source_file": "src/{self.OLD}/core.py",')
        snippet = _snippet("skf-create-skill/references/compile.md", self.OLD)
        code, verdict = _rename_and_verify(tmp_path, self.OLD, self.NEW, snippet, metadata, provenance)
        assert code == 1
        assert [(m["region"], m["text"]) for m in verdict["hard_matches"]] == [expected]

    def test_a_quick_skill_named_after_its_repository_renames_clean(self, tmp_path):
        """Quick Skill's renderer defaults source_package to the skill name; the repository shares it."""
        spec = importlib.util.spec_from_file_location("skf_render_quick_metadata_for_rename", QUICK_METADATA)
        quick = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(quick)
        metadata = quick.render_metadata(
            {"name": "zod", "language": "typescript", "source_repo": "https://github.com/colinhacks/zod",
             "source_root": "/home/me/.skf/workspace/colinhacks/zod", "source_commit": "4b7b5c1d",
             "description": "TypeScript-first schema validation. Use when validating input.", "exports": ["object"]},
            now_fn=lambda: "2026-09-28T00:00:00Z")
        assert metadata["source_package"] == "zod"
        snippet = _snippet("skf-quick-skill/assets/skill-template.md", "zod")
        code, verdict = _rename_and_verify(tmp_path, "zod", "zod-kit", snippet, metadata)
        assert code == 0 and verdict["clean"] is True, verdict["hard_matches"]


# --- The step prose says what the transform rewrites -----------------------------

RENAME_EXECUTE = REPO / "src" / "skf-rename-skill" / "references" / "execute.md"
RENAME_SELECT = REPO / "src" / "skf-rename-skill" / "references" / "select.md"
VERSION_PATHS = REPO / "src" / "knowledge" / "version-paths.md"


def _between(text: str, start: str, end: str) -> str:
    assert text.count(start) == 1, f"marker {start!r} must occur once"
    body = text[text.index(start):]
    assert end in body, f"marker {end!r} missing after {start!r}"
    return body[:body.index(end)]


class TestRenameProse:
    def test_step_3c_rewrites_the_template_slots_only(self):
        three_c = _between(RENAME_EXECUTE.read_text(encoding="utf-8"),
                           "**3c. context-snippet.md**", "**3d. provenance-map.json**")
        assert "Rewrites `{old_name}` where every SKF snippet template writes the name" in three_c
        assert "the same rule `{verifyNoTraceHelper}` uses" in three_c
        assert "the first word of the `|IMPORTANT:` line and its `writing {old_name} code` phrase" in three_c
        assert "Nothing else in the snippet changes" in three_c
        assert "§5 reports it and the rename rolls back rather than commit a changed snippet" in three_c
        assert "and any other mention" not in three_c
        assert "keeps the prefix verbatim" in three_c

    def test_steps_3b_and_3d_pass_the_moved_folders(self):
        text = RENAME_EXECUTE.read_text(encoding="utf-8")
        section3 = _between(text, "### 3. Update File Contents", "### 4. ")
        assert '[--moved-folder "{folder}"]' in section3
        moved = _between(section3, "**Moved folders (3b and 3d only).**", "Read the JSON result")
        assert 'Pass `--moved-folder "{skills_output_folder}"`, and also `--moved-folder "{forge_data_folder}"` ' \
               "when `{forge_move}` or `{same_folder}` is true" in moved
        assert "A forge folder left in place keeps its name, so paths into it stay as they are." in moved
        three_b = _between(section3, "**3b. metadata.json**", "**3c. context-snippet.md**")
        assert "Every string value that is a path into a moved folder, `{folder}/{old_name}/…`, " \
               "is pointed at `{folder}/{new_name}/…`" in three_b
        assert "file names such as `test-report-{old_name}.md` stay" in three_b
        for phrase in ("A path counts only where it begins, at the start of the value or of a word in it, spelled as "
                       "the folder's full path or as its last components",
                       "so a URL or a path that only holds the folder's name further in stays",
                       "The values that name the upstream source or a file in it never change, even when one holds "
                       "such a path",
                       "the source-fact keys §5 lists, `source_file` and a stack's `co_import_files`",
                       "§5 then reports a `source_file` that names `{old_name}`"):
            assert phrase in three_b, phrase
        named = set(re.findall(r"`(source_[a-z_]+|co_import_files)`", three_b))
        assert named == {"source_file", "co_import_files"}
        three_d = _between(section3, "**3d. provenance-map.json**", "**Rollback on any update failure")
        assert "with the moved folders above, points the paths into them at `{new_name}` as 3b does" in three_d

    def test_plan_and_knowledge_name_what_is_rewritten(self):
        select = RENAME_SELECT.read_text(encoding="utf-8")
        assert "context-snippet.md (the name in its header, its IMPORTANT line and its root paths)" in select
        assert "metadata.json (`name` field, and paths into the moved folders)" in select
        assert "provenance-map.json (`skill_name` field and paths into the moved folders, under {old_forge_group})" in select
        assert "(every mention of the name, root paths included)" not in select
        rename = _between(VERSION_PATHS.read_text(encoding="utf-8"), "### Rename (RS - Rename Skill)", "### Drop")
        assert "The name where the snippet template writes it in `context-snippet.md`: display header, first word " \
               "and `writing {name} code` on the `|IMPORTANT:` line, and root paths" in rename
        assert "`metadata.json` `name` field, and any path value into a moved folder" in rename
        assert "`provenance-map.json` `skill_name` field, and any path value into a moved folder" in rename
        assert "Every mention of the name" not in rename

    def test_docs_name_verify_failed(self):
        workflows = (REPO / "docs" / "workflows.md").read_text(encoding="utf-8")
        rs = next(line for line in workflows.split("\n") if line.startswith("- **`/skf-rename-skill` (RS)**"))
        assert "`3` resolution-failure (`manifest-corrupt`, `nothing-to-rename`)" in rs
        assert "`verify-failed` when the old name is still in the renamed files" in rs
        trouble = _between((REPO / "docs" / "troubleshooting.md").read_text(encoding="utf-8"),
                           "### Rename Skill stops with `verify-failed`", "\n### ")
        for phrase in ("(exit `5`)", "the skill keeps its old name and every file as it was",
                       "such as a test report path an update run recorded",
                       "**The skill is named after its library or repository**",
                       "(`api`, `root`, `data`), the skill cannot be renamed"):
            assert phrase in trouble, phrase

    def test_every_description_of_section_5_names_the_verifiers_source_facts(self):
        """Step §5, the knowledge file and troubleshooting list exactly the keys the helper skips."""
        keys = set(verify_mod.SOURCE_FACT_KEYS)
        section5 = _between(RENAME_EXECUTE.read_text(encoding="utf-8"), "### 5. Verify", "### 6. ")
        assert "in the two JSON files a match inside the value of a source-fact key, below, does not count" in section5
        assert "§3 leaves them unchanged and the helper does not count a match inside them" in section5
        assert "Every other value and every key outside those values still counts, and a JSON file that does not " \
            "parse is scanned whole" in section5
        rename = _between(VERSION_PATHS.read_text(encoding="utf-8"), "### Rename (RS - Rename Skill)", "### Drop")
        assert "In the two JSON files it skips the values of the keys that name the upstream source" in rename
        trouble = _between((REPO / "docs" / "troubleshooting.md").read_text(encoding="utf-8"),
                           "### Rename Skill stops with `verify-failed`", "\n### ")
        assert "In the two JSON files it skips the values of `source_repo`" in trouble
        for phrase in ("and a value that rename does not skip names the library or the repository: the `description`",
                       "an export that has the library's name, the path of a file in the source",
                       "for a skill named like its repository, the README URL create-skill records in `metadata.json` "
                       "`doc_sources`",
                       "The source values above and the paths of files in the source stay as they are"):
            assert phrase in trouble, phrase
        for name, text in (("execute.md §5", section5), ("version-paths.md", rename), ("troubleshooting.md", trouble)):
            assert set(re.findall(r"`(source_[a-z_]+)`", text)) == keys, name
