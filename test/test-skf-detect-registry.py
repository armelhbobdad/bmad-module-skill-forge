#!/usr/bin/env python3
"""Tests for skf-detect-registry.py: create-skill step 3d's demo counts and
registry score, and the prose of component-extraction.md that reads them.

The helper runs in process for the counting and scoring, and through its
CLI for the exit codes and the files it writes. Fixture files are written
with write_bytes, so a Windows checkout reads the same bytes and lines.
The last classes pin the step's prose (#605): Phase 1 lets the helper list
the brief's files and count the demo files, Phase 2 reads its score and
the headless gate its `headless_accept`, Phase 2b writes back only what a
user answered through the brief writer, Phase 3 maps the helper's entries,
Phase 4 runs the component-library recipes in one runner call, and a brief
the write-back produced validates and shadows no other workflow's decision.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "src" / "shared" / "scripts"
HELPER = SCRIPTS / "skf-detect-registry.py"
COMPONENT_EXTRACTION = REPO / "src" / "skf-create-skill" / "references" / "component-extraction.md"
SCHEMA_DOC = REPO / "src" / "skf-brief-skill" / "assets" / "skill-brief-schema.md"

_MODULES: dict[str, object] = {}


def _load(path: Path):
    """Load a script once, so a missing script fails each test, not collection."""
    if path not in _MODULES:
        assert path.is_file(), f"missing script: {path}"
        spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _MODULES[path] = module
    return _MODULES[path]


def _mod():
    return _load(HELPER)


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def _run(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HELPER), *args],
        input=stdin.encode("utf-8") if stdin is not None else None,
        capture_output=True,
        timeout=60,
    )


def _entries(count: int, keys: tuple[str, ...] = ("id", "name", "category")) -> str:
    """An array literal of `count` object literals, each with `keys`."""
    rows = []
    for i in range(count):
        fields = ", ".join(f'{key}: "{key}-{i}"' for key in keys)
        rows.append(f"  {{ {fields} }},")
    return "[\n" + "\n".join(rows) + "\n]"


# --------------------------------------------------------------------------
# File list
# --------------------------------------------------------------------------


class TestFileList:
    def test_lines_and_json(self, tmp_path):
        lines = _write(tmp_path, "files.txt", "./a.ts\r\nsrc\\b.ts\n\na.ts\n")
        assert _mod().read_file_list(str(lines)) == ["a.ts", "src/b.ts"]
        listed = _write(tmp_path, "files.json", json.dumps(["a.ts", "src/b.ts", "a.ts"]))
        assert _mod().read_file_list(str(listed)) == ["a.ts", "src/b.ts"]

    def test_a_route_folder_first_is_read_line_by_line(self, tmp_path):
        """A Next.js route such as `[slug]/page.tsx` opens with `[` and is not JSON."""
        listed = _write(tmp_path, "files.txt", "[slug]/page.tsx\nregistry/index.ts\n")
        assert _mod().read_file_list(str(listed)) == ["[slug]/page.tsx", "registry/index.ts"]

    def test_unreadable_list_is_a_usage_error(self, tmp_path):
        proc = _run("demo", "--files-from", str(tmp_path / "missing.txt"))
        assert proc.returncode == 2
        assert b"cannot read file list" in proc.stderr


# --------------------------------------------------------------------------
# demo
# --------------------------------------------------------------------------

LIBRARY_FILES = [
    "registry/index.ts",
    "components/ui/button.tsx",
    "examples/button-demo.tsx",
    "apps/www/demo/page.tsx",
    "src/stories/Button.stories.tsx",
    "src/Card.demo.tsx",
    "src/card.tsx",
]


class TestDemo:
    def test_auto_patterns_report_only_what_matches(self):
        result, kept = _mod().detect_demo(LIBRARY_FILES)
        assert result["mode"] == "auto"
        assert [p["pattern"] for p in result["patterns"]] == [
            "**/demo/**", "**/stories/**", "**/examples/**", "**/*.stories.*", "**/*.demo.*",
        ]
        by_pattern = {p["pattern"]: p for p in result["patterns"]}
        assert by_pattern["**/examples/**"]["files"] == 1
        assert by_pattern["**/stories/**"]["sample"] == ["src/stories/Button.stories.tsx"]
        # A file two patterns match is excluded once.
        assert result["excluded"] == 4
        assert result["directories"] == 4
        assert kept == ["registry/index.ts", "components/ui/button.tsx", "src/card.tsx"]
        assert result["kept"] == 3 and result["files_scanned"] == len(LIBRARY_FILES)

    def test_the_defaults_live_in_the_helper(self):
        """Phase 1 points at the helper's --help instead of restating its defaults."""
        mod = _mod()
        assert mod.DEMO_FOLDERS == ("demo", "demos", "stories", "__stories__", "storybook", "examples", "example")
        assert mod.DEMO_FILE_PATTERNS == ("*.stories.*", "*.story.*", "*.example.*", "*.demo.*")
        phase_1 = _phase(1)
        for folder in mod.DEMO_FOLDERS:
            if folder != "examples":  # the gate says why it asks: some examples/ folders hold API code
                assert f"`{folder}/`" not in phase_1, folder
        for pattern in mod.DEMO_FILE_PATTERNS:
            assert f"`{pattern}`" not in phase_1, pattern
        assert "uv run {detectRegistryHelper} --help" in phase_1
        assert "DEMO_FOLDERS" in mod.__doc__ and "DEMO_FILE_PATTERNS" in mod.__doc__

    def test_given_patterns_report_the_default_matches_they_leave_in(self):
        """A brief's scope.demo_patterns stops the prompt; a demo folder of another
        kind added later still shows up in also_matched."""
        result, kept = _mod().detect_demo(LIBRARY_FILES, ["stories/"])
        assert [p["pattern"] for p in result["patterns"]] == ["**/stories/**"]
        assert [(p["pattern"], p["files"]) for p in result["also_matched"]] == [
            ("**/demo/**", 1), ("**/examples/**", 1), ("**/*.demo.*", 1),
        ]
        assert "examples/button-demo.tsx" in kept
        assert _mod().detect_demo(LIBRARY_FILES)[0]["also_matched"] == []

    @pytest.mark.parametrize("given, glob", [
        ("examples/", "**/examples/**"),
        ("*.stories.*", "**/*.stories.*"),
        ("apps/www/demo/", "apps/www/demo/**"),
        ("src/**/*.demo.tsx", "src/**/*.demo.tsx"),
        ("./examples/", "**/examples/**"),
    ])
    def test_given_patterns_are_read_as_globs(self, given, glob):
        assert _mod().normalize_pattern(given) == glob

    def test_given_patterns_are_reported_matched_or_not(self):
        result, kept = _mod().detect_demo(LIBRARY_FILES, ["examples/", "nothing/**"])
        assert result["mode"] == "given"
        assert [(p["pattern"], p["files"]) for p in result["patterns"]] == [
            ("**/examples/**", 1), ("nothing/**", 0),
        ]
        assert "examples/button-demo.tsx" not in kept and len(kept) == len(LIBRARY_FILES) - 1

    def test_cli_writes_the_kept_files_as_a_json_list(self, tmp_path):
        files = _write(tmp_path, "files.txt", json.dumps(["[slug]/page.tsx", *LIBRARY_FILES]))
        kept_file = tmp_path / "scan" / "kept.txt"
        proc = _run("demo", "--files-from", str(files), "--kept-to", str(kept_file))
        assert proc.returncode == 0, proc.stderr
        result = json.loads(proc.stdout)
        assert result["kept_file"] == str(kept_file)
        kept = json.loads(kept_file.read_bytes().decode("utf-8"))
        assert kept == ["[slug]/page.tsx", "registry/index.ts", "components/ui/button.tsx", "src/card.tsx"]
        # The registry command reads that list back, the route included.
        assert _mod().read_file_list(str(kept_file)) == kept


BRIEF_YAML = """name: acme-ui
scope:
  type: component-library
  include: ["src/**", "./examples/**"]
  exclude: ["**/*.css"]
  notes: ""
"""


def _library_tree(root: Path) -> None:
    for rel in ("src/button.tsx", "src/button.css", "src/stories/Button.stories.tsx", "examples/demo.tsx",
                "docs/intro.md", ".storybook/main.ts", "src/.cache/x.ts"):
        _write(root, rel, "export const x = 1;\n")


class TestDemoFiles:
    """Phase 1 types no file list: demo lists the brief's files itself (#605)."""

    def test_the_tree_is_listed_and_cut_to_the_brief(self, tmp_path):
        root = tmp_path / "src-root"
        _library_tree(root)
        brief = _write(tmp_path, "skill-brief.yaml", BRIEF_YAML)
        scan = tmp_path / "scan"
        proc = _run("demo", "--source-root", str(root), "--brief", str(brief),
                    "--files-to", str(scan / "files.txt"), "--kept-to", str(scan / "kept.txt"))
        assert proc.returncode == 0, proc.stderr
        result = json.loads(proc.stdout)
        # Hidden entries are never listed; docs/ is outside scope.include and the stylesheet excluded.
        assert (result["files_listed"], result["files_scanned"]) == (5, 3)
        files = json.loads((scan / "files.txt").read_bytes())
        assert files == ["examples/demo.tsx", "src/button.tsx", "src/stories/Button.stories.tsx"]
        assert json.loads((scan / "kept.txt").read_bytes()) == ["src/button.tsx"]
        assert (result["files_file"], result["kept_file"]) == (str(scan / "files.txt"), str(scan / "kept.txt"))

    def test_git_leaves_out_what_it_ignores(self, tmp_path):
        if shutil.which("git") is None:
            pytest.skip("git is not installed")
        root = tmp_path / "src-root"
        _library_tree(root)
        _write(root, "dist/button.js", "export const x = 1;\n")
        _write(root, ".gitignore", "dist/\n")
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        assert _mod().list_tree(root) == [
            "docs/intro.md", "examples/demo.tsx", "src/button.css", "src/button.tsx", "src/stories/Button.stories.tsx",
        ]

    def test_a_remote_listing_on_stdin(self, tmp_path):
        brief = _write(tmp_path, "skill-brief.yaml", BRIEF_YAML)
        listing = "src/button.tsx\nexamples/demo.tsx\nREADME.md\n"
        proc = _run("demo", "--files-from", "-", "--brief", str(brief), stdin=listing)
        assert proc.returncode == 0, proc.stderr
        result = json.loads(proc.stdout)
        assert (result["files_listed"], result["files_scanned"], result["excluded"]) == (3, 2, 1)

    def test_without_a_brief_every_listed_file_is_in_scope(self):
        assert _mod().in_scope(["a.ts", "b.css"], [], []) == ["a.ts", "b.css"]
        assert _mod().in_scope(["a.ts", "b.css"], [], ["**/*.css"]) == ["a.ts"]

    @pytest.mark.parametrize("args, message", [
        (("demo", "--source-root", "ROOT/missing"), b"--source-root must name a folder"),
        (("demo", "--files-from", "-", "--brief", "ROOT/missing.yaml"), b"cannot read brief"),
        (("demo", "--source-root", "ROOT", "--files-from", "-"), b"not allowed with argument"),
    ], ids=["root-not-a-folder", "brief-missing", "two-sources"])
    def test_usage_errors(self, tmp_path, args, message):
        proc = _run(*[a.replace("ROOT", str(tmp_path)) for a in args], stdin="a.ts\n")
        assert proc.returncode == 2 and message in proc.stderr
        assert proc.stdout == b""


# --------------------------------------------------------------------------
# registry: candidates and score
# --------------------------------------------------------------------------


class TestCandidates:
    @pytest.mark.parametrize("rel, rule", [
        ("registry.ts", 1),
        ("lib/deep/registry.js", 1),
        ("src/registry.tsx", 1),
        ("registry/components.ts", 2),
        ("app/catalog/components.tsx", 2),
        ("src/components/components.ts", 2),
        ("registry/index.ts", 3),
        ("catalog/index.tsx", 3),
        ("components/index.ts", None),
        ("src/components.ts", None),
        ("registry/index.js", None),
        ("registry/button.tsx", None),
    ])
    def test_rules(self, rel, rule):
        assert _mod().candidate_rule(rel) == rule

    def test_candidates_only_reads_no_file(self, tmp_path):
        files = _write(tmp_path, "files.txt", "registry/index.ts\nsrc/a.ts\nlib/registry.js\n")
        proc = _run("registry", "--files-from", str(files), "--candidates-only")
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout == b"registry/index.ts\nlib/registry.js\n"


class TestScore:
    """The rubric of the module docstring, which Phase 2 used to apply by eye."""

    @pytest.mark.parametrize("keys, folder, count, parts", [
        (("id", "name", "category"), "registry", 20,
         {"id": 3, "name_or_component": 2, "category_or_tags": 2, "registry_folder": 1, "entries_20_plus": 1}),
        (("id", "component", "tags"), "src", 12,
         {"id": 3, "name_or_component": 2, "category_or_tags": 2, "registry_folder": 0, "entries_20_plus": 0}),
        (("name",), "catalog", 25,
         {"id": 0, "name_or_component": 2, "category_or_tags": 0, "registry_folder": 1, "entries_20_plus": 1}),
        ((), "registry", 10,
         {"id": 0, "name_or_component": 0, "category_or_tags": 0, "registry_folder": 1, "entries_20_plus": 0}),
    ], ids=["full-marks", "no-folder", "name-only", "empty-entries"])
    def test_rubric(self, tmp_path, keys, folder, count, parts):
        rel = f"{folder}/registry.ts"
        _write(tmp_path, rel, f"export const items = {_entries(count, keys)};\n")
        candidate = _mod().evaluate(tmp_path, rel, 1)
        assert candidate["score_parts"] == parts
        assert candidate["score"] == sum(parts.values())
        assert candidate["entry_count"] == count

    def test_a_field_counts_only_when_every_entry_has_it(self, tmp_path):
        src = "export const items = [\n" + "\n".join(
            f'  {{ id: "c{i}", name: "C{i}"' + (', category: "x"' if i else "") + " },"
            for i in range(12)) + "\n];\n"
        _write(tmp_path, "registry.ts", src)
        candidate = _mod().evaluate(tmp_path, "registry.ts", 1)
        assert candidate["fields"] == {"category": 11, "id": 12, "name": 12}
        assert candidate["score_parts"]["category_or_tags"] == 0
        assert candidate["score"] == 5 and candidate["qualifies"]

    @pytest.mark.parametrize("count, keys, qualifies", [
        (9, ("id", "name", "category"), False),
        (10, ("id", "name"), True),
        (10, ("id",), False),
    ], ids=["nine-entries", "ten-entries-score-5", "ten-entries-score-3"])
    def test_qualifying_needs_ten_entries_and_a_score_of_five(self, tmp_path, count, keys, qualifies):
        _write(tmp_path, "src/registry.ts", f"export default {_entries(count, keys)};\n")
        assert _mod().evaluate(tmp_path, "src/registry.ts", 1)["qualifies"] is qualifies

    @pytest.mark.parametrize("keys, folder, accept", [
        (("id", "name", "category"), "src", True),
        (("id", "name"), "registry", False),
    ], ids=["score-7", "score-6"])
    def test_headless_accepts_at_seven(self, tmp_path, keys, folder, accept):
        rel = f"{folder}/components.ts" if folder == "registry" else f"{folder}/registry.ts"
        _write(tmp_path, rel, f"export const items = {_entries(12, keys)};\n")
        result = _mod().detect_registry(tmp_path, [rel])
        assert result["selected"] == rel
        assert result["headless_accept"] is accept

    def test_selection_order(self, tmp_path):
        """Qualifying first, then the higher score, then the lower rule, then the path."""
        _write(tmp_path, "b/registry.ts", f"export const a = {_entries(12)};\n")
        _write(tmp_path, "a/registry.ts", f"export const a = {_entries(12)};\n")
        _write(tmp_path, "registry/index.ts", f"export const a = {_entries(12)};\n")
        _write(tmp_path, "catalog/index.ts", f"export const a = {_entries(5)};\n")
        files = ["catalog/index.ts", "b/registry.ts", "registry/index.ts", "a/registry.ts"]
        result = _mod().detect_registry(tmp_path, files)
        # registry/index.ts scores 8 (its folder), the two registry.ts files 7.
        assert [c["path"] for c in result["candidates"]] == [
            "registry/index.ts", "a/registry.ts", "b/registry.ts", "catalog/index.ts",
        ]
        assert result["selected"] == "registry/index.ts" and result["headless_accept"] is True

    def test_no_qualifying_candidate_selects_nothing(self, tmp_path):
        _write(tmp_path, "registry.ts", f"export const a = {_entries(3)};\n")
        result = _mod().detect_registry(tmp_path, ["registry.ts", "src/a.ts"])
        assert result["selected"] is None and result["headless_accept"] is False
        assert [c["path"] for c in result["candidates"]] == ["registry.ts"]


# --------------------------------------------------------------------------
# registry: the lexical parse
# --------------------------------------------------------------------------


TRICKY_REGISTRY = (
    "﻿// a comment holding [ { id: 1 } ] is no array\r\n"
    "/* nor is [ { id: 2 }, { id: 3 } ] */\r\n"
    "const re = /\\[\\{/g;\r\n"
    "const half = total / 2 / 3;\r\n"
    "const base = { tags: [] };\r\n"
    "export const components: ComponentEntry[] = [\r\n"
    + "".join(
        f"  {{ id: 'c{i}', name: `Comp ${{x}} {i}`, ...base, ['k']: 1, "
        f"component: memo(() => <p>it's [{i}]</p>), get category() {{ return \"forms\"; }} }},\r\n"
        for i in range(11))
    + "];\r\n"
    "export const small = [{ id: 'x' }, { id: 'y' }];\r\n"
)


class TestParse:
    def test_strings_comments_regexes_and_jsx_never_open_an_array(self, tmp_path):
        _write(tmp_path, "registry/components.ts", TRICKY_REGISTRY)
        candidate = _mod().evaluate(tmp_path, "registry/components.ts", 2)
        assert candidate["error"] is None
        assert candidate["array"] == {"name": "components", "line": 6, "annotation": "ComponentEntry[]"}
        assert candidate["entry_count"] == 11
        # A spread and a computed key add no key; a getter names its key.
        assert candidate["fields"] == {"category": 11, "component": 11, "id": 11, "name": 11}
        assert candidate["score"] == 3 + 2 + 2 + 1
        first = candidate["sample"][0]
        assert first["line"] == 7 and first["id"] == "c0" and first["name"] == "Comp ${x} 0"
        assert first["component"] == "memo(() => <p>it's [0]</p>)"
        assert len(candidate["sample"]) == 5

    @pytest.mark.parametrize("source, name", [
        ("module.exports = ARRAY;\n", "module.exports"),
        ("export default ARRAY;\n", "default"),
        ("export const registry = { items: ARRAY };\n", "items"),
        ("let list: Entry[] = ARRAY;\n", "list"),
    ], ids=["module-exports", "export-default", "object-key", "let-annotated"])
    def test_binding_names(self, tmp_path, source, name):
        _write(tmp_path, "registry.js", source.replace("ARRAY", _entries(10)))
        assert _mod().evaluate(tmp_path, "registry.js", 1)["array"]["name"] == name

    def test_the_largest_array_of_objects_wins(self, tmp_path):
        src = (f"export const few = {_entries(10)};\n"
               f"export const many = {_entries(14, ('id',))};\n"
               "export const words = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o'];\n")
        _write(tmp_path, "registry.ts", src)
        candidate = _mod().evaluate(tmp_path, "registry.ts", 1)
        assert candidate["array"]["name"] == "many" and candidate["entry_count"] == 14

    def test_long_values_are_cut_in_the_sample(self, tmp_path):
        long_call = "load(" + ", ".join(f"'part-{i}'" for i in range(20)) + ")"
        src = "export const r = [\n" + "\n".join(
            f"  {{ id: 'c{i}', component: {long_call}, tags: ['a', 'b'] }}," for i in range(10)) + "\n];\n"
        _write(tmp_path, "registry.ts", src)
        sample = _mod().evaluate(tmp_path, "registry.ts", 1)["sample"][0]
        assert sample["tags"] == ["a", "b"]
        assert len(sample["component"]) == _mod().VALUE_TEXT_LIMIT and sample["component"].endswith("...")


class TestEntries:
    """Phase 3 maps the entries the helper lists, lines included (#605)."""

    LONG = "A button that submits the form it sits in, with a loading state and every variant the design has."

    def _registry(self, root: Path) -> str:
        rows = [f'  {{ id: "c{i}", name: "C{i}", category: "forms", description: "{self.LONG}", files: ["ui/c{i}.tsx"] }},'
                for i in range(12)]
        return _write(root, "registry/index.ts", "export const items = [\n" + "\n".join(rows) + "\n];\n").name

    def test_every_entry_in_full(self, tmp_path):
        self._registry(tmp_path)
        result = _mod().detect_registry(tmp_path, [], "registry/index.ts", entries=True)
        [candidate] = result["candidates"]
        assert len(candidate["entries"]) == 12
        first = candidate["entries"][0]
        assert first == {"line": 2, "keys": ["id", "name", "category", "description", "files"], "id": "c0",
                         "name": "C0", "category": "forms", "description": self.LONG}
        assert candidate["entries"][11]["line"] == 13
        # The sample stays short, and carries no description.
        assert "description" not in candidate["sample"][0]

    def test_only_the_selected_candidate_lists_its_entries(self, tmp_path):
        self._registry(tmp_path)
        _write(tmp_path, "lib/registry.ts", f"export const few = {_entries(3)};\n")
        result = _mod().detect_registry(tmp_path, ["registry/index.ts", "lib/registry.ts"], entries=True)
        assert result["selected"] == "registry/index.ts"
        assert [("entries" in c) for c in result["candidates"]] == [True, False]
        assert "entries" not in _mod().detect_registry(tmp_path, ["registry/index.ts"])["candidates"][0]

    def test_cli(self, tmp_path):
        self._registry(tmp_path)
        proc = _run("registry", "--source-root", str(tmp_path), "--path", "registry/index.ts", "--entries")
        assert proc.returncode == 0, proc.stderr
        assert len(json.loads(proc.stdout)["candidates"][0]["entries"]) == 12


# --------------------------------------------------------------------------
# registry: a given path
# --------------------------------------------------------------------------


class TestGivenPath:
    def test_a_given_file_is_selected_whatever_its_score(self, tmp_path):
        _write(tmp_path, "src/catalog.ts", f"export const all = {_entries(3, ('slug',))};\n")
        result = _mod().detect_registry(tmp_path, [], "src/catalog.ts")
        assert result["explicit"] is True
        assert result["selected"] == "src/catalog.ts" and result["headless_accept"] is True
        assert result["candidates"][0]["score"] == 0 and result["candidates"][0]["rule"] == 0

    @pytest.mark.parametrize("given", ["gone.ts", "../outside.ts"], ids=["missing", "outside-the-tree"])
    def test_an_unreadable_given_file_selects_nothing(self, tmp_path, given):
        root = tmp_path / "src-root"
        root.mkdir()
        _write(tmp_path, "outside.ts", f"export const all = {_entries(12)};\n")
        result = _mod().detect_registry(root, [], given)
        assert result["selected"] is None and result["headless_accept"] is False
        assert result["candidates"][0]["error"].startswith(f"cannot read {given}")

    def test_cli(self, tmp_path):
        _write(tmp_path, "registry/index.ts", f"export const r = {_entries(20)};\n")
        files = _write(tmp_path, "files.txt", json.dumps(["registry/index.ts", "a.ts"]))
        proc = _run("registry", "--files-from", str(files), "--source-root", str(tmp_path))
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["selected"] == "registry/index.ts"
        proc = _run("registry", "--source-root", str(tmp_path), "--path", "registry/index.ts")
        assert proc.returncode == 0 and json.loads(proc.stdout)["explicit"] is True

    @pytest.mark.parametrize("args", [
        ("registry", "--files-from", "LIST"),
        ("registry", "--source-root", "ROOT"),
        ("registry", "--candidates-only"),
        ("registry", "--files-from", "LIST", "--source-root", "ROOT/missing"),
    ], ids=["no-root", "no-list", "candidates-without-list", "root-not-a-folder"])
    def test_usage_errors(self, tmp_path, args):
        files = _write(tmp_path, "files.txt", "registry.ts\n")
        argv = [a.replace("LIST", str(files)).replace("ROOT", str(tmp_path)) for a in args]
        proc = _run(*argv)
        assert proc.returncode == 2
        assert proc.stdout == b""


# --------------------------------------------------------------------------
# component-extraction.md: the prose reads the helper
# --------------------------------------------------------------------------


def _text() -> str:
    return COMPONENT_EXTRACTION.read_text(encoding="utf-8")


def _phase(number: str | int) -> str:
    text = _text()
    start = text.index(f"### Phase {number}:")
    end = text.index("\n### ", start + 1)
    return text[start:end]


class TestComponentExtractionProse:
    def test_phase_1_lets_the_helper_list_and_count_the_files(self):
        """The model types no file list: the helper lists the brief's files under
        the source root (or reads a remote tree's listing) and writes the lists."""
        phase_1 = _phase(1)
        assert ('uv run {detectRegistryHelper} demo --source-root "{source_root}" --brief "{brief_file}" '
                '[--pattern "{glob}"] --files-to "{component_scan}/files.txt" '
                '--kept-to "{component_scan}/kept.txt"') in phase_1
        flat = " ".join(phase_1.split())
        assert ("pipe it the repository's file list, `gh api \"repos/{owner}/{repo}/git/trees/{source_ref}?recursive=1\" "
                "--jq '.tree[] | select(.type == \"blob\") | .path'`, with `--files-from -` in place of `--source-root`") in flat
        assert "Write the filtered file list" not in _text()
        assert "Count matches per pattern category" not in _text()
        for field in ("`excluded`", "`directories`", "`also_matched[]`"):
            assert field in phase_1, field
        assert "exclude nothing and bind `{scan_list}` to null" in flat

    def test_phase_2_reads_the_score(self):
        phase_2 = _phase(2)
        assert 'uv run {detectRegistryHelper} registry --files-from "{scan_list}" --source-root "{source_root}"' in phase_2
        # The rubric lives in the helper: the prose holds no point table to apply by eye.
        assert not re.search(r"\+\d+ points?", _text())
        assert "score >= 7" not in _text() and "score < 7" not in _text()

    def test_headless_gate_reads_headless_accept(self):
        gate = next(line for line in _phase(2).splitlines() if '"gate": "registry-confirm"' in line)
        assert "`{headless_mode}` is true and `headless_accept` is true" in gate
        assert "If `headless_accept` is false in headless mode, auto-reject the candidate" in gate
        assert "below the auto-accept threshold\"" in gate

    def test_the_rubric_lives_in_the_helper(self):
        """Phase 2 names the fields it acts on and points at --help: the
        thresholds are stated once, in the helper."""
        mod = _mod()
        phase_2 = " ".join(_phase(2).split())
        assert "uv run {detectRegistryHelper} --help" in phase_2
        assert "qualifies with" not in phase_2 and "Threshold" not in phase_2
        for number in (mod.MIN_ENTRIES, mod.MIN_SCORE, mod.AUTO_ACCEPT_SCORE, mod.MANY_ENTRIES):
            assert f"{number} or more" not in phase_2, number
        assert f"threshold {mod.AUTO_ACCEPT_SCORE}" not in phase_2

    def test_an_unreadable_registry_path_still_reaches_a_gate(self):
        """A stale scope.registry_path falls back to detection, the no-registry
        gate still fires, and Phase 2b may replace the stale path."""
        phase_2 = " ".join(_phase(2).split())
        assert "set `registry_path_unreadable` ← true, and run the next command" in phase_2
        assert "**If no registry was found and the brief holds no usable `scope.registry_path`:**" in phase_2
        phase_2b = " ".join(_phase("2b").split())
        assert "replaces one Phase 2 could not read (`registry_path_unreadable`)" in phase_2b
        assert "user replaced the unreadable registry path at create-skill step 3d" in phase_2b

    def test_phase_3_maps_the_entries_the_helper_lists(self):
        phase_3 = _phase(3)
        assert 'uv run {detectRegistryHelper} registry --source-root "{source_root}" --path "{registry_file}" --entries' in phase_3
        assert "`[SRC:{registry_file}:L{line}]`, with the entry's `line`" in phase_3

    def test_phase_4_runs_the_component_library_recipes_once(self):
        phase_4 = _phase(4)
        [call] = [line for line in phase_4.splitlines() if line.startswith("uv run {extractPublicApiHelper}")]
        assert "--mode full" in call and "--recipe-set component-library" in call
        assert '--files-from "{scan_list}"' in call
        assert 'pass `--brief "{brief_file}"` in place of `--files-from "{scan_list}"`' in phase_4
        assert "A `missing` or `unreadable` issue is a listed file the runner could not read" in phase_4
        fallback = phase_4[phase_4.index("**On exit 1, 2 or 3"):phase_4.index("**Step 1 ")]
        assert "load `{extractionPatternsData}`" in fallback
        assert "AST Extraction Protocol" in fallback

    def test_scratch_folder_removal_is_guarded(self):
        text = _text()
        assert "rm -rf" in text
        assert re.findall(r'rm -rf "\{[^}"]+\}[^"]*"', text) == ['rm -rf "{component_scan}"']
        guard = next(line for line in text.splitlines() if 'rm -rf "{component_scan}"' in line)
        assert guard.startswith('case "{component_scan}" in "{project-root}/_bmad-output/.skf-run/skf-create-skill-3d-"*)')


class TestWriteBack:
    """#605 enhancement-6: Phase 2b records only what a user answered."""

    def test_only_user_answers_are_written_back(self):
        phase_2b = _phase("2b")
        assert "Write back only what a user answered at a gate above, never a headless auto-decision" in phase_2b
        assert "**Skip this phase when neither `demo_answer` nor `registry_answer` is set.**" in phase_2b
        demo = " ".join(_phase(1).split())
        assert ("`demo_answer` ← the `patterns[]` globs the user confirmed or gave (none on `n`, in headless "
                "mode, or when the brief set them)") in demo

    def test_amendment_shape_matches_the_schema_doc(self):
        phase_2b = " ".join(_phase("2b").split())
        assert '`category: "demo-and-registry"`' in phase_2b
        assert '`action: "demo-excluded"`' in phase_2b and '`action: "registry-confirmed"`' in phase_2b
        doc = " ".join(SCHEMA_DOC.read_text(encoding="utf-8").split())
        assert "`demo-excluded` (the glob is written to `scope.demo_patterns`" in doc
        assert "`registry-confirmed` (the file is written to `scope.registry_path`" in doc

    def test_the_brief_writer_amends_the_brief(self):
        """No brief is re-typed by hand: the writer reads it again, keeps a .bak
        and writes atomically (test-skf-write-skill-brief.py runs amend)."""
        phase_2b = _phase("2b")
        assert 'uv run {writeSkillBriefHelper} amend --target "{brief_file}" <<\'SKF_BRIEF_ANSWERS\'' in phase_2b
        assert "step 3 §2a may have amended it" in phase_2b and "`{brief_file}.bak`" in phase_2b
        text = _text()
        assert "atomicWriteHelper" not in text and "{amended brief YAML}" not in text
        assert "{brief_path}.bak" not in text


def _written_back_brief() -> dict:
    """A brief as Phase 2b leaves it after a user confirmed both answers."""
    return {
        "name": "acme-ui",
        "version": "2.1.0",
        "source_repo": "https://github.com/acme/ui",
        "language": "typescript",
        "description": "Acme UI components. Use when building screens with Acme UI.",
        "forge_tier": "Forge",
        "created": "2026-09-30",
        "created_by": "armel",
        "scope": {
            "type": "component-library",
            "include": ["registry/**", "components/**"],
            "exclude": [],
            "notes": "",
            "amendments": [
                {"path": "llms.txt", "action": "skipped", "category": "auth-doc",
                 "reason": "user declined promotion at create-skill §2a", "heuristic": "llms.txt",
                 "date": "2026-09-30", "workflow": "skf-create-skill"},
                {"path": "**/examples/**", "action": "demo-excluded", "category": "demo-and-registry",
                 "reason": "user confirmed the demo exclusion at create-skill step 3d",
                 "evidence": "4 files", "date": "2026-10-01", "workflow": "skf-create-skill"},
                {"path": "llms.txt", "action": "registry-confirmed", "category": "demo-and-registry",
                 "reason": "user gave the registry path at create-skill step 3d",
                 "evidence": "given by the user, 12 entries", "date": "2026-10-01",
                 "workflow": "skf-create-skill"},
            ],
            "registry_path": "registry/index.ts",
            "demo_patterns": ["**/examples/**"],
        },
    }


class TestWrittenBackBrief:
    def test_validates_against_the_schema(self):
        validator = _load(SCRIPTS / "skf-validate-brief-schema.py")
        result = validator.validate_brief(_written_back_brief())
        assert result["valid"] is True, result["errors"]

    def test_never_stands_in_for_an_auth_doc_or_scope_expansion_decision(self):
        """skf-resolve-authoritative-files.py and skf-provenance-gap-dispatch.py
        reconcile amendments by path: a demo-and-registry entry on the same path
        must leave the other workflows' decisions as they were."""
        brief = _written_back_brief()
        resolver = _load(SCRIPTS / "skf-resolve-authoritative-files.py")
        _includes, _excludes, by_path = resolver.extract_scope(brief)
        assert resolver._latest_action(by_path["llms.txt"]) == "skipped"
        assert resolver._latest_action(by_path["**/examples/**"]) is None
        dispatch = _load(SCRIPTS / "skf-provenance-gap-dispatch.py")
        [classified] = dispatch.reconcile([{"path": "**/examples/**", "evidence": "new API"}], brief)
        assert (classified["status"], classified["prior_action"]) == ("unresolved", None)
