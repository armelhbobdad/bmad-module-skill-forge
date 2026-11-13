#!/usr/bin/env python3
"""Tests for skf-detect-registry.py: create-skill step 3d's demo counts and
registry score, and the prose of component-extraction.md that reads them.

The helper runs in process for the counting and scoring, and through its
CLI for the exit codes and the files it writes. Fixture files are written
with write_bytes, so a Windows checkout reads the same bytes and lines.
The last classes pin the step's prose (#605): Phase 1 lets the helper list
the brief's files and count the demo files, Phase 2 reads its score and
the headless gate its `headless_accept`, Phase 2b writes back only what a
user answered through the brief writer, Phase 3 writes the helper's entries
for Phase 4's sort, Phase 4 runs the component-library recipes in one runner
call and sorts, links and counts their exports with `components` (#1146),
Phases 5 and 6 read that call's JSON, and a brief the write-back produced
validates and shadows no other workflow's decision. `components` itself is
tested one row of the spec's I/O matrix at a time, from synthetic runner
JSON (no ast-grep).
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

    def test_the_github_probe_listing_is_read_by_its_tree(self, tmp_path):
        """skf-brief-skill step 3 passes step 2's tree.json, the object skf-github-probe.py tree --out writes."""
        listing = {"status": "ok", "repo": "o/r", "ref": "main", "count": 2, "truncated": False,
                   "tree": ["src/registry.ts", "demo/button.tsx"]}
        listed = _write(tmp_path, "tree.json", json.dumps(listing) + "\n")
        assert _mod().read_file_list(str(listed)) == ["src/registry.ts", "demo/button.tsx"]
        proc = _run("demo", "--files-from", str(listed))
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["patterns"][0]["pattern"] == "**/demo/**"

    @pytest.mark.parametrize("listing,message", [
        pytest.param({"status": "unavailable", "message": "Could not reach GitHub.", "tree": []},
                     b"reports a failure (unavailable): Could not reach GitHub.", id="failed-listing"),
        pytest.param({"status": "ok", "count": 0}, b"holds no `tree` list of paths", id="no-tree"),
    ])
    def test_a_listing_that_names_no_paths_is_a_usage_error(self, tmp_path, listing, message):
        listed = _write(tmp_path, "tree.json", json.dumps(listing))
        proc = _run("registry", "--files-from", str(listed), "--candidates-only")
        assert proc.returncode == 2
        assert message in proc.stderr


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
# components: sort, link, catalog and count (#1146)
# --------------------------------------------------------------------------


def _export(name: str, rel: str, line: int, recipe: str | None, kind: str | None, signature: str = "",
            declaration: str | None = None) -> dict:
    """An export as the runner records it (ast_recipe set) or as it is read by eye (none)."""
    entry = {"export_name": name, "source_file": rel, "source_line": line, "ast_recipe": recipe,
             "export_type": kind, "signature": signature,
             "citation": f"[{'AST' if recipe else 'SRC'}:{rel}:L{line}]"}
    if declaration is not None:
        entry["declaration_signature_line"] = declaration
    return entry


def _links(result: dict) -> dict[str, tuple[str | None, str | None, str]]:
    return {f"{link['props_file']}:{link['props']}": (link["component"], link["component_file"],
                                                      link["link_method"]) for link in result["links"]}


def _names(result: dict, key: str) -> list[str]:
    return [item["name"] for item in result[key]]


class TestComponents:
    """`components` sorts, links, maps the registry and counts in place of the
    model (#1146 determinism-4), one test per row of the spec's I/O matrix
    from Naming to Bad input, the CLI's payload fed to the inventory's `set`."""

    def _runner(self, tmp_path: Path, exports: list[dict]) -> Path:
        return _write(tmp_path, "extraction.json", json.dumps({"status": "ok", "exports": exports}))

    def _brief(self, tmp_path: Path, variants: list[dict] | None = None) -> Path:
        scope = {"type": "component-library"}
        if variants is not None:
            scope["ui_variants"] = variants
        return _write(tmp_path, "skill-brief.yaml", json.dumps({"name": "acme-ui", "scope": scope}))

    def _registry(self, tmp_path: Path, rows: list[str]) -> Path:
        _write(tmp_path / "src-root", "registry/index.ts", "export const registry = [\n" + "\n".join(rows) + "\n];\n")
        result = _mod().detect_registry(tmp_path / "src-root", [], "registry/index.ts", entries=True)
        return _write(tmp_path, "registry.json", json.dumps(result))

    def _cli(self, *args: str) -> dict:
        proc = _run("components", *args)
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)

    def test_naming_convention(self):
        result = _mod().detect_components([
            _export("ButtonProps", "ui/button.tsx", 1, "react-props-interfaces", "interface"),
            _export("Button", "ui/button.tsx", 5, "react-component-functions", "function"),
            _export("Badge", "ui/button.tsx", 9, "react-component-functions", "function")], [])
        assert _links(result) == {"ui/button.tsx:ButtonProps": ("Button", "ui/button.tsx", "naming-convention")}

    def test_the_nearest_candidate_wins(self):
        """Two components share the name: the one in the contract's file, then its folder."""
        result = _mod().detect_components([
            _export("Button", "a/button.tsx", 3, "react-component-functions", "function"),
            _export("Button", "b/button.tsx", 3, "react-component-functions", "function"),
            _export("ButtonProps", "b/button.tsx", 1, "react-props-interfaces", "interface"),
            _export("Button", "b/x/button.tsx", 3, "react-component-functions", "function"),
            _export("ButtonProps", "b/x/types.ts", 1, "ts-exported-types", "interface")], [])
        links = _links(result)
        assert links["b/button.tsx:ButtonProps"][1] == "b/button.tsx"
        assert links["b/x/types.ts:ButtonProps"][1] == "b/x/button.tsx"

    def test_a_local_list_sorts_by_what_it_names(self):
        result = _mod().detect_components([
            _export("Card", "ui/card.tsx", 8, "js-local-exports", "function", "export { Card, cardVariants }"),
            _export("cardVariants", "ui/card.tsx", 8, "js-local-exports", "const", "export { Card, cardVariants }"),
            _export("CardProps", "ui/card.tsx", 9, "js-local-exports", "re-export", "export type { CardProps }"),
            _export("DialogProps", "ui/dialog.tsx", 1, "js-local-exports", "re-export",
                    "export { type DialogProps, Dialog }"),
            _export("Dialog", "ui/dialog.tsx", 1, "js-local-exports", "function",
                    "export { type DialogProps, Dialog }"),
            _export("Theme", "ui/card.tsx", 10, "js-local-exports", "re-export", "export type { Theme }"),
            _export("Size", "ui/card.tsx", 11, "ts-exported-types", "enum"),
            # an imported type a value list passes on with a bare `type` specifier, no `Props` in its name
            _export("Tone", "ui/badge.tsx", 2, "js-local-exports", "re-export", "export { type Tone, Badge }"),
            _export("Badge", "ui/badge.tsx", 2, "js-local-exports", "function", "export { type Tone, Badge }")], [])
        assert _names(result, "components") == ["Badge", "Card", "Dialog"]
        assert _names(result, "props_contracts") == ["CardProps", "DialogProps"]
        assert _names(result, "shared_exports") == ["cardVariants"]
        assert _names(result, "shared_types") == ["Tone", "Theme", "Size"]
        assert {link["link_method"] for link in result["links"]} == {"naming-convention"}

    def test_co_location_then_the_next_rule(self):
        one = _mod().detect_components([
            _export("Props", "ui/slider.tsx", 1, "ts-exported-types", "type", "export type Props = { min: number }"),
            _export("Slider", "ui/slider.tsx", 3, "react-wrapped-components", "const")], [])
        assert _links(one) == {"ui/slider.tsx:Props": ("Slider", "ui/slider.tsx", "co-location")}
        two = _mod().detect_components([
            _export("Props", "ui/slider.tsx", 1, "ts-exported-types", "type", "export type Props = { min: number }"),
            _export("Slider", "ui/slider.tsx", 3, "react-wrapped-components", "const"),
            _export("SliderThumb", "ui/slider.tsx", 7, "react-wrapped-components", "const")], [])
        assert _links(two) == {"ui/slider.tsx:Props": (None, None, "none")}

    def test_generic_param(self):
        result = _mod().detect_components([
            _export("Props", "ui/slider.tsx", 1, "ts-exported-types", "type",
                    "export type Props = React.ComponentProps<typeof Slider>"),
            _export("Slider", "ui/slider.tsx", 3, "react-wrapped-components", "const",
                    "export const Slider = React.forwardRef((props, ref) => null)"),
            _export("SliderThumb", "ui/slider.tsx", 7, "react-wrapped-components", "const"),
            _export("Props", "ui/range.tsx", 1, "ts-exported-types", "type", "export type Props = { to: number }"),
            _export("Range", "ui/range.tsx", 3, "react-wrapped-components", "const",
                    "export const Range = forwardRef<HTMLDivElement, Props>((p, r) => null)"),
            _export("RangeTrack", "ui/range.tsx", 7, "react-component-arrow-functions", "const",
                    "export const RangeTrack = (p: { on: boolean }) => <div />"),
            # a member after `typeof` names no component of that name
            _export("RootProps", "ui/root.ts", 1, "ts-exported-types", "type",
                    "export type RootProps = ComponentProps<typeof Primitive.Slider>")], [])
        links = _links(result)
        assert links["ui/slider.tsx:Props"] == ("Slider", "ui/slider.tsx", "generic-param")
        assert links["ui/range.tsx:Props"] == ("Range", "ui/range.tsx", "generic-param")
        assert links["ui/root.ts:RootProps"] == (None, None, "none")

    def test_generic_param_reads_a_local_list_items_declaration_line(self):
        """A local list item's `signature` is the list line; its `declaration_signature_line` holds the `typeof`
        or the `<...>` that names the link."""
        slider = "export { type Props, Slider, SliderThumb }"
        range_list = "export { type Props, Range, RangeTrack }"
        result = _mod().detect_components([
            _export("Props", "ui/slider.tsx", 9, "js-local-exports", "type", slider,
                    declaration="type Props = React.ComponentProps<typeof Slider>"),
            _export("Slider", "ui/slider.tsx", 9, "js-local-exports", "function", slider,
                    declaration="function Slider() {"),
            _export("SliderThumb", "ui/slider.tsx", 9, "js-local-exports", "function", slider,
                    declaration="function SliderThumb() {"),
            _export("Props", "ui/range.tsx", 9, "js-local-exports", "interface", range_list,
                    declaration="interface Props {"),
            _export("Range", "ui/range.tsx", 9, "js-local-exports", "const", range_list,
                    declaration="const Range = forwardRef<HTMLDivElement, Props>((p, r) => null)"),
            _export("RangeTrack", "ui/range.tsx", 9, "js-local-exports", "function", range_list,
                    declaration="function RangeTrack() {")], [])
        links = _links(result)
        assert links["ui/slider.tsx:Props"] == ("Slider", "ui/slider.tsx", "generic-param")
        assert links["ui/range.tsx:Props"] == ("Range", "ui/range.tsx", "generic-param")

    def test_a_vue_file_is_named_by_its_name_before_its_first_dot(self):
        """`button.client.vue` defines `Button`, and a name's non-ASCII letters stay in it."""
        result = _mod().detect_components([
            _export("Props", "vue/button.client.vue", 3, "vue-define-props", "type", "defineProps<Props>()"),
            _export("Props", "vue/sélect-menu.vue", 3, "vue-define-props", "type", "defineProps<Props>()")], [])
        assert sorted(_names(result, "components")) == ["Button", "SélectMenu"]

    def test_a_vue_contract_adds_its_file_component(self):
        result = _mod().detect_components([
            _export("Props", "vue/my-button.vue", 3, "vue-define-props", "type", "defineProps<Props>()"),
            _export("Props", "vue/IconBadge.vue", 2, "react-props-interfaces", "interface")], [])
        assert _names(result, "props_contracts") == ["Props", "Props"]
        assert _names(result, "components") == ["IconBadge", "MyButton"]
        assert _links(result) == {"vue/my-button.vue:Props": ("MyButton", "vue/my-button.vue", "co-location"),
                                  "vue/IconBadge.vue:Props": ("IconBadge", "vue/IconBadge.vue", "co-location")}
        component = result["components"][1]
        assert (component["source_line"], component["citation"]) == (3, "[AST:vue/my-button.vue:L3]")

    def test_a_props_interface_read_by_eye_is_a_contract(self, tmp_path):
        exports = _write(tmp_path, "read-by-eye.json", json.dumps([
            {"export_name": "InputProps", "export_type": "interface", "source_file": "ui/input.tsx",
             "source_line": 1, "citation": "[SRC:ui/input.tsx:L1]"},
            {"export_name": "inputVariants", "export_type": "const", "source_file": "ui/input.tsx",
             "source_line": 9, "citation": "[SRC:ui/input.tsx:L9]"}]))
        extraction = self._runner(tmp_path, [_export("Input", "ui/input.tsx", 4, "react-component-functions",
                                                     "function")])
        result = self._cli("--extraction", str(extraction), "--exports", str(exports))
        assert _names(result, "props_contracts") == ["InputProps"]
        assert result["props_contracts"][0]["ast_recipe"] is None
        assert _names(result, "shared_exports") == ["inputVariants"]
        assert _links(result) == {"ui/input.tsx:InputProps": ("Input", "ui/input.tsx", "naming-convention")}

    def test_a_constant_is_a_shared_export_and_a_props_alias_a_contract(self):
        """The Constant and alias row: a value export no component recipe matched is a component only when its
        name is PascalCase, and a `*Props` item a local list passes on (`re-export`, or `type <local> as <name>`)
        is a type."""
        list_items = "export { List, MAX_ITEMS, ListContext }"
        alias = "export { type Props as ButtonProps, Button }"
        theme = "export { type Theme as AppTheme, Button }"
        result = _mod().detect_components([
            _export("List", "ui/list.tsx", 9, "js-local-exports", "function", list_items),
            _export("MAX_ITEMS", "ui/list.tsx", 9, "js-local-exports", "const", list_items),
            _export("ListContext", "ui/list.tsx", 9, "js-local-exports", "const", list_items),
            _export("ButtonProps", "ui/button.tsx", 9, "js-local-exports", "re-export", alias),
            _export("Button", "ui/button.tsx", 9, "js-local-exports", "function", alias),
            _export("AppTheme", "ui/theme.tsx", 9, "js-local-exports", "re-export", theme),
            # read by eye: no recipe, and an imported Props passed on
            _export("DialogProps", "ui/dialog.tsx", 2, None, "re-export"),
            _export("Dialog", "ui/dialog.tsx", 5, None, "function")], [])
        assert _names(result, "shared_exports") == ["MAX_ITEMS"]
        assert _names(result, "components") == ["Button", "Dialog", "List", "ListContext"]
        assert _names(result, "props_contracts") == ["ButtonProps", "DialogProps"]
        assert _names(result, "shared_types") == ["AppTheme"]
        assert _links(result) == {"ui/button.tsx:ButtonProps": ("Button", "ui/button.tsx", "naming-convention"),
                                  "ui/dialog.tsx:DialogProps": ("Dialog", "ui/dialog.tsx", "naming-convention")}
        assert result["stats_extra"]["components_unique"] == 4

    def test_a_bare_name_in_another_file_links_nothing(self):
        """The Generic elsewhere row: `Props` in `ui/range.tsx`'s `forwardRef<HTMLDivElement, Props>` is that
        file's own type, so `ui/slider.tsx`'s `Props`, beside two components, links none."""
        result = _mod().detect_components([
            _export("Props", "ui/slider.tsx", 1, "ts-exported-types", "interface", "export interface Props {}"),
            _export("Slider", "ui/slider.tsx", 3, "react-wrapped-components", "const",
                    "export const Slider = forwardRef((p, r) => null)"),
            _export("SliderThumb", "ui/slider.tsx", 7, "react-wrapped-components", "const"),
            _export("Range", "ui/range.tsx", 3, "react-wrapped-components", "const",
                    "export const Range = forwardRef<HTMLDivElement, Props>((p, r) => null)")], [])
        assert _links(result) == {"ui/slider.tsx:Props": (None, None, "none")}

    def test_an_index_vue_is_named_by_its_folder(self):
        """The Vue index row: `Button/index.vue` and `Card/index.vue` define `Button` and `Card`, 2 units."""
        result = _mod().detect_components([
            _export("Props", "src/Button/index.vue", 3, "vue-define-props", "type", "defineProps<Props>()"),
            _export("Props", "src/Card/index.vue", 3, "vue-define-props", "type", "defineProps<Props>()")], [])
        assert _names(result, "components") == ["Button", "Card"]
        assert _links(result) == {"src/Button/index.vue:Props": ("Button", "src/Button/index.vue", "co-location"),
                                  "src/Card/index.vue:Props": ("Card", "src/Card/index.vue", "co-location")}
        assert result["stats_extra"]["components_unique"] == 2

    def test_a_vue_file_that_exports_its_component_adds_none(self):
        result = _mod().detect_components([
            _export("Props", "vue/my-button.vue", 3, "vue-define-props", "type", "defineProps<Props>()"),
            _export("MyButton", "vue/my-button.vue", 9, None, "const")], [])
        assert [(c["name"], c["source_line"]) for c in result["components"]] == [("MyButton", 9)]
        assert _links(result) == {"vue/my-button.vue:Props": ("MyButton", "vue/my-button.vue", "co-location")}

    def test_the_runner_export_wins_over_the_same_one_read_by_eye(self, tmp_path):
        """The Overlap row, through the CLI: `InputProps` in both inputs is one contract, the runner's."""
        extraction = self._runner(tmp_path, [
            _export("InputProps", "ui/input.tsx", 1, "react-props-interfaces", "interface"),
            _export("Input", "ui/input.tsx", 4, "react-component-functions", "function")])
        exports = _write(tmp_path, "read-by-eye.json", json.dumps([
            {"export_name": "InputProps", "export_type": "interface", "source_file": "ui/input.tsx",
             "source_line": 1, "citation": "[SRC:ui/input.tsx:L1]", "signature": "export interface InputProps",
             "params": None, "return_type": None}]))
        result = self._cli("--extraction", str(extraction), "--exports", str(exports))
        [contract] = result["props_contracts"]
        assert (contract["citation"], contract["ast_recipe"]) == ("[AST:ui/input.tsx:L1]", "react-props-interfaces")
        assert len(result["links"]) == 1 and result["stats_extra"]["props_interfaces_extracted"] == 1

    def _two_variants(self, tmp_path: Path, exports: list[dict]) -> dict:
        registry = self._registry(tmp_path, ['  { id: "button", name: "button" },'])
        brief = self._brief(tmp_path, [{"name": "radix", "package": "packages/radix"},
                                       {"name": "base", "package": "packages/base"}])
        return self._cli("--extraction", str(self._runner(tmp_path, exports)), "--registry", str(registry),
                         "--brief", str(brief))

    def test_the_primary_variant_comes_first_when_its_path_sorts_later(self, tmp_path):
        """The Primary sorts later row: `radix` is primary though `packages/base` sorts first."""
        exports = []
        for v in ("radix", "base"):
            exports += [_export("ButtonProps", f"packages/{v}/button.tsx", 1, "react-props-interfaces", "interface"),
                        _export("Button", f"packages/{v}/button.tsx", 5, "react-component-functions", "function")]
        [entry] = self._two_variants(tmp_path, exports)["component_catalog"]
        assert (entry["name"], entry["props"], entry["props_file"]) == ("Button", "ButtonProps",
                                                                        "packages/radix/button.tsx")
        assert entry["code_paths"] == ["packages/radix/button.tsx", "packages/base/button.tsx"]
        assert entry["available_in"] == ["radix", "base"]

    def test_a_contract_links_the_component_of_its_own_variant(self, tmp_path):
        """The Variant link row: each `ButtonProps` in `src/types/` links its own variant's `Button`."""
        exports = []
        for v in ("radix", "base"):
            exports += [
                _export("ButtonProps", f"packages/{v}/src/types/button.ts", 1, "ts-exported-types", "interface"),
                _export("Button", f"packages/{v}/src/components/button.tsx", 5, "react-component-functions",
                        "function")]
        result = self._two_variants(tmp_path, exports)
        assert _links(result) == {
            f"packages/{v}/src/types/button.ts:ButtonProps": ("Button", f"packages/{v}/src/components/button.tsx",
                                                              "naming-convention") for v in ("radix", "base")}
        [entry] = result["component_catalog"]
        assert entry["props_file"] == "packages/radix/src/types/button.ts"

    def test_the_canonical_contract_is_the_naming_convention_one(self, tmp_path):
        """The Canonical row: `ButtonGroupProps` links `Button` by co-location and sorts first by name, but the
        `button` entry's contract is `ButtonProps`, linked by naming convention."""
        registry = self._registry(tmp_path, ['  { id: "button" },'])
        extraction = self._runner(tmp_path, [
            _export("ButtonProps", "ui/button.tsx", 1, "react-props-interfaces", "interface"),
            _export("ButtonGroupProps", "ui/button.tsx", 4, "react-props-interfaces", "interface"),
            _export("Button", "ui/button.tsx", 9, "react-component-functions", "function")])
        result = self._cli("--extraction", str(extraction), "--registry", str(registry))
        assert _links(result)["ui/button.tsx:ButtonGroupProps"] == ("Button", "ui/button.tsx", "co-location")
        [entry] = result["component_catalog"]
        assert (entry["props"], entry["link_method"]) == ("ButtonProps", "naming-convention")

    def test_an_entry_no_component_names_takes_the_components_of_its_file(self, tmp_path):
        """The File join row: `ui/sonner.tsx`'s `Toaster` joins `sonner`, an `index` file by its folder, and the
        entry no component joins is left in `unmatched_entries`."""
        registry = self._registry(tmp_path, ['  { id: "sonner" },', '  { id: "toast", name: "toast" },',
                                             '  { id: "tooltip" },'])
        extraction = self._runner(tmp_path, [
            _export("Toaster", "ui/sonner.tsx", 3, "react-component-functions", "function"),
            _export("ToastViewport", "ui/toast/index.tsx", 3, "react-component-functions", "function"),
            _export("ToastProps", "ui/toast/index.tsx", 1, "react-props-interfaces", "interface")])
        result = self._cli("--extraction", str(extraction), "--registry", str(registry))
        catalog = {entry["id"]: entry for entry in result["component_catalog"]}
        assert (catalog["sonner"]["name"], catalog["sonner"]["code_paths"]) == ("Sonner", ["ui/sonner.tsx"])
        assert catalog["toast"]["code_paths"] == ["ui/toast/index.tsx"]
        assert catalog["toast"]["props"] == "ToastProps"
        assert result["unmatched_entries"] == ["tooltip"]
        assert result["stats_extra"]["components_unique"] == 3

    def test_an_entry_a_component_joins_by_name_takes_no_other_by_file(self, tmp_path):
        """`Dialog` joins `dialog` by name, so `DialogTrigger` in the same `ui/dialog.tsx` does not join it by
        file name, and its `DialogTriggerProps` is not the entry's contract."""
        registry = self._registry(tmp_path, ['  { id: "dialog" },'])
        extraction = self._runner(tmp_path, [
            _export("Dialog", "ui/dialog.tsx", 3, "react-component-functions", "function"),
            _export("DialogTriggerProps", "ui/dialog.tsx", 7, "react-props-interfaces", "interface"),
            _export("DialogTrigger", "ui/dialog.tsx", 9, "react-component-functions", "function")])
        result = self._cli("--extraction", str(extraction), "--registry", str(registry))
        [entry] = result["component_catalog"]
        assert (entry["props"], entry["link_method"], entry["code_paths"]) == (None, None, ["ui/dialog.tsx"])
        assert result["stats_extra"]["components_documented"] == 0

    def test_a_registry_with_no_array_lists_no_entries_and_the_call_runs_without_it(self, tmp_path):
        """The Registry without entries row: an object-map registry gives a selected candidate with no `entries`,
        which `components` refuses, so Phase 3 goes on with no registry and Step 4's call still sorts and counts."""
        _write(tmp_path / "src-root", "registry/index.ts",
               'export const registry = {\n  button: { name: "Button", category: "forms" },\n};\n')
        listed = _mod().detect_registry(tmp_path / "src-root", [], "registry/index.ts", entries=True)
        [chosen] = [c for c in listed["candidates"] if c["path"] == listed["selected"]]
        assert "entries" not in chosen
        registry = _write(tmp_path, "registry.json", json.dumps(listed))
        extraction = self._runner(tmp_path, [
            _export("ButtonProps", "ui/button.tsx", 1, "react-props-interfaces", "interface"),
            _export("Button", "ui/button.tsx", 5, "react-component-functions", "function")])
        refused = _run("components", "--extraction", str(extraction), "--registry", str(registry))
        assert refused.returncode == 2 and refused.stdout == b""
        result = self._cli("--extraction", str(extraction))
        assert result["stats_extra"]["components_unique"] == 1 and result["stats_extra"]["components_documented"] == 1

    def test_registry_and_variants(self, tmp_path):
        exports = []
        for variant in ("a", "b"):
            exports += [
                _export("ButtonProps", f"packages/{variant}/button.tsx", 1, "react-props-interfaces", "interface"),
                _export("Button", f"packages/{variant}/button.tsx", 5, "react-component-functions", "function"),
                _export("AlertDialog", f"packages/{variant}/alert-dialog.tsx", 3, "react-component-functions",
                        "function")]
        registry = self._registry(tmp_path, [
            '  { id: "button", name: "Button", category: "forms", description: "A button.", tags: ["form"] },',
            '  { id: "alert-dialog", name: "Alert Dialog", category: "overlay", tags: "modal" },',
            '  { id: "tooltip", name: "Tooltip", category: "overlay" },',
            '  { id: "button", name: "Button again" },',
            '  { label: "no key" },'])
        brief = self._brief(tmp_path, [{"name": "a", "package": "packages/a"}, {"name": "b", "package": "packages/b"}])
        result = self._cli("--extraction", str(self._runner(tmp_path, exports)), "--registry", str(registry),
                           "--brief", str(brief), "--demo-excluded", "4")
        assert result["variants"] == [{"name": "a", "package": "packages/a", "primary": True},
                                      {"name": "b", "package": "packages/b", "primary": False}]
        catalog = {entry["id"]: entry for entry in result["component_catalog"]}
        assert list(catalog) == ["button", "alert-dialog", "tooltip"]
        assert catalog["button"] == {
            "id": "button", "name": "Button", "description": "A button.", "category": "forms", "tags": ["form"],
            "citation": "[SRC:registry/index.ts:L2]", "available_in": ["a", "b"],
            "code_paths": ["packages/a/button.tsx", "packages/b/button.tsx"],
            "props": "ButtonProps", "props_file": "packages/a/button.tsx", "link_method": "naming-convention"}
        assert catalog["alert-dialog"]["available_in"] == ["a", "b"]
        assert (catalog["alert-dialog"]["tags"], catalog["alert-dialog"]["props"]) == (["modal"], None)
        assert catalog["tooltip"]["available_in"] == [] and catalog["tooltip"]["description"] == ""
        assert result["unmatched_entries"] == ["tooltip"]
        assert result["catalog_by_category"] == [
            {"category": "overlay", "count": 2, "components": ["AlertDialog", "Tooltip"]},
            {"category": "forms", "count": 1, "components": ["Button"]}]
        assert [w for w in result["warnings"] if "no id, name or component" in w]
        assert (result["components_unique"], result["components_total_with_variants"]) == (3, 5)
        assert result["stats_extra"] == {"components_registered": 5, "components_documented": 1,
                                         "props_interfaces_extracted": 2, "components_unique": 3,
                                         "demo_files_excluded": 4, "design_variants": {"a": 2, "b": 2}}

    def test_the_spec_registry_row(self, tmp_path):
        """Entries `button` and `alert-dialog`, Button and AlertDialog in variants a and b, the second found by
        its folder name."""
        exports = [_export("Button", f"src/{v}/button.tsx", 1, "react-component-functions", "function")
                   for v in ("a", "b")]
        exports += [_export("AlertDialog", f"src/{v}/alert-dialog.tsx", 1, "react-component-functions", "function")
                    for v in ("a", "b")]
        registry = self._registry(tmp_path, ['  { id: "button" },', '  { id: "alert-dialog" },'])
        brief = self._brief(tmp_path, [{"name": "a", "package": "src/a"}, {"name": "b"}])
        result = self._cli("--extraction", str(self._runner(tmp_path, exports)), "--registry", str(registry),
                           "--brief", str(brief))
        assert [e["available_in"] for e in result["component_catalog"]] == [["a", "b"], ["a", "b"]]
        assert [e["name"] for e in result["component_catalog"]] == ["Button", "AlertDialog"]
        stats = result["stats_extra"]
        assert (stats["components_registered"], stats["components_unique"]) == (2, 2)
        assert result["components_total_with_variants"] == 4
        assert stats["design_variants"] == {"a": 2, "b": 2}

    def test_a_missing_category_comes_from_categories(self, tmp_path):
        registry = self._registry(tmp_path, ['  { id: "button", name: "Button" },',
                                             '  { id: "dialog", name: "Dialog", category: "overlay" },'])
        extraction = self._runner(tmp_path, [_export("Button", "ui/button.tsx", 1, "react-component-functions",
                                                     "function")])
        first = self._cli("--extraction", str(extraction), "--registry", str(registry))
        assert [e["category"] for e in first["component_catalog"]] == [None, "overlay"]
        assert first["catalog_by_category"][-1] == {"category": None, "count": 1, "components": ["Button"]}
        categories = _write(tmp_path, "categories.json", json.dumps({"button": "forms", "dialog": "modals",
                                                                     "nope": "misc"}))
        second = self._cli("--extraction", str(extraction), "--registry", str(registry), "--categories",
                           str(categories))
        assert [e["category"] for e in second["component_catalog"]] == ["forms", "overlay"]
        assert second["catalog_by_category"] == [{"category": "forms", "count": 1, "components": ["Button"]},
                                                 {"category": "overlay", "count": 1, "components": ["Dialog"]}]
        assert len(second["warnings"]) == 2
        assert any("nope" in w for w in second["warnings"]) and any("dialog" in w for w in second["warnings"])

    def test_no_registry(self, tmp_path):
        exports = [_export("Button", f"{v}/button.tsx", 1, "react-component-functions", "function")
                   for v in ("shadcn", "base")]
        exports += [_export("ButtonProps", "shadcn/button.tsx", 0, "react-props-interfaces", "interface"),
                    _export("Card", "shadcn/card.tsx", 1, "react-component-functions", "function")]
        # a variant with no package holds the files under a folder of its name, matched case-insensitively
        brief = self._brief(tmp_path, [{"name": "shadcn"}, {"name": "Base", "package": None}])
        result = self._cli("--extraction", str(self._runner(tmp_path, exports)), "--brief", str(brief))
        assert (result["component_catalog"], result["catalog_by_category"], result["unmatched_entries"]) == ([], [], [])
        assert (result["components_unique"], result["components_total_with_variants"]) == (2, 3)
        assert result["stats_extra"] == {"components_registered": 0, "components_documented": 1,
                                         "props_interfaces_extracted": 1, "components_unique": 2,
                                         "demo_files_excluded": 0, "design_variants": {"shadcn": 2, "Base": 1}}
        plain = self._cli("--extraction", str(self._runner(tmp_path, exports)))
        assert (plain["variants"], plain["stats_extra"]["design_variants"]) == ([], {})
        assert plain["components_total_with_variants"] == 2

    def test_the_payload_is_what_the_inventory_sets(self, tmp_path):
        registry = self._registry(tmp_path, ['  { id: "button", name: "Button", category: "forms" },'])
        extraction = self._runner(tmp_path, [
            _export("ButtonProps", "ui/button.tsx", 1, "react-props-interfaces", "interface"),
            _export("Button", "ui/button.tsx", 5, "react-component-functions", "function")])
        target = tmp_path / "stage" / "acme-ui.components.json"
        result = self._cli("--extraction", str(extraction), "--registry", str(registry), "--set-to", str(target))
        payload = json.loads(target.read_text(encoding="utf-8"))
        assert payload == {"component_catalog": result["component_catalog"], "component_stats": result["stats_extra"]}
        inventory = tmp_path / "acme-ui.inventory.json"
        script = SCRIPTS / "skf-extraction-inventory.py"
        for args, stdin in ((["init", "--skill", "acme-ui", "--mode", "component-library", "--tier", "Forge"], None),
                            (["set"], target.read_bytes())):
            proc = subprocess.run([sys.executable, str(script), *args, "--inventory", str(inventory)], input=stdin,
                                  capture_output=True, timeout=60)
            assert proc.returncode == 0, proc.stderr
        data = json.loads(inventory.read_text(encoding="utf-8"))
        assert (data["component_catalog"], data["component_stats"]) == (payload["component_catalog"],
                                                                         payload["component_stats"])

    def test_a_failed_write_prints_nothing(self, tmp_path):
        blocker = _write(tmp_path, "blocker", "a file, not a folder")
        extraction = self._runner(tmp_path, [_export("Button", "ui/button.tsx", 5, "react-component-functions",
                                                     "function")])
        proc = _run("components", "--extraction", str(extraction), "--set-to", str(blocker / "out.json"))
        assert proc.returncode == 2 and proc.stdout == b""
        assert proc.stderr.decode("utf-8").startswith("skf-detect-registry: cannot write")

    @pytest.mark.parametrize("case", ["no-exports", "export-without-file", "registry-without-entries",
                                      "categories-not-strings", "variants-not-a-list", "variant-without-name",
                                      "negative-demo", "unreadable-json", "unreadable-brief"])
    def test_bad_input_exits_2_and_writes_nothing(self, tmp_path, case):
        good = self._runner(tmp_path, [_export("Button", "ui/button.tsx", 5, "react-component-functions",
                                               "function")])
        target = tmp_path / "out.json"

        def bad(text: str) -> str:
            return str(_write(tmp_path, "bad.json", text))

        args = {
            "no-exports": lambda: ["--extraction", bad(json.dumps({"status": "ok"}))],
            "export-without-file": lambda: ["--exports", bad(json.dumps([{"export_name": "InputProps"}]))],
            "registry-without-entries": lambda: ["--extraction", str(good), "--registry", bad(json.dumps(
                {"selected": "r.ts", "candidates": [{"path": "r.ts"}]}))],
            "categories-not-strings": lambda: ["--extraction", str(good), "--categories",
                                               bad(json.dumps({"button": ""}))],
            "variants-not-a-list": lambda: ["--extraction", str(good), "--brief",
                                            str(self._brief(tmp_path, {"name": "a"}))],
            "variant-without-name": lambda: ["--extraction", str(good), "--brief",
                                             str(self._brief(tmp_path, [{"package": "packages/a"}]))],
            "negative-demo": lambda: ["--extraction", str(good), "--demo-excluded", "-1"],
            "unreadable-json": lambda: ["--extraction", bad("{not json")],
            "unreadable-brief": lambda: ["--extraction", str(good), "--brief", str(tmp_path / "no-brief.yaml")],
        }[case]()
        proc = _run("components", *args, "--set-to", str(target))
        assert proc.returncode == 2, (case, proc.stderr)
        assert proc.stdout == b"" and not target.exists()
        assert proc.stderr.decode("utf-8").startswith("skf-detect-registry: ")
        assert len(proc.stderr.decode("utf-8").strip().splitlines()) == 1


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
        # #1146: Step 4's call maps the entries it wrote; with no helper there is no by-eye read, since the call
        # needs the same script
        assert ('--entries > "{component_scan}/registry.json"') in phase_3
        flat = " ".join(phase_3.split())
        assert "Phase 4's Step 4 call maps each entry, keyed by its `id` (else `name`, else `component`)" in flat
        assert ("When the command exits non-zero, no candidate resolves, or its selected candidate lists no `entries` "
                "(the file holds no array of object literals, such as an object map), warn \"The registry was not "
                "parsed: {its stderr, or 'skf-detect-registry.py is missing, so re-install SKF', or '{registry_file} "
                "holds no array of entries'}.\" and go on with no registry: Step 4's call reads the registry through "
                "the same script and exits 2 on one with no `entries`.") in flat
        assert "by eye" not in phase_3 and "from the directory structure" not in _text()

    def test_step_1_reads_the_fields_after_step_4s_call(self):
        """Step 1 reads each Props contract's fields once Step 4's call has listed them, and from what Steps 1 and
        2 found when the call printed nothing, so a failed call still leaves every contract its `params`."""
        phase_4 = _phase(4)
        step_1 = phase_4[phase_4.index("**Step 1 (extract Props interfaces):**"):phase_4.index("**Step 2 ")]
        assert ("Once Step 4's call has run, for each Props contract it lists in `props_contracts`, or, when it "
                "printed no JSON, each Props contract Steps 1 and 2 found (a `*Props` interface or type, or a Vue "
                "props type):") in " ".join(step_1.split())
        step_4 = phase_4.index("**Step 4 (sort, link and count):**")
        assert phase_4.index("**Step 1 (extract Props interfaces):**") < step_4

    def test_step_4_sorts_links_and_counts_through_the_helper(self):
        """#1146 determinism-4: Phase 4 sorts, links, maps and counts through
        one `components` call whose payload step 3 §5's `set` reads; with no
        helper or a failed call it warns and counts nothing by hand."""
        phase_4 = _phase(4)
        step_4 = phase_4[phase_4.index("**Step 4 (sort, link and count):**"):]
        [call] = [line for line in step_4.splitlines() if line.startswith("uv run {detectRegistryHelper} components")]
        assert call == ('uv run {detectRegistryHelper} components [--extraction "{extraction_json}"] '
                        '[--exports "{read_by_eye_json}"] [--registry "{component_scan}/registry.json"] '
                        '[--categories "{component_scan}/categories.json"] --brief "{brief_file}" '
                        '--demo-excluded {demo_files_excluded} --set-to "{components_json}" '
                        '> "{component_scan}/components.json"')
        words = re.sub(r'[\[\]"]', "", call.split(" > ")[0].replace("{demo_files_excluded}", "0")).split()
        args = _mod()._build_parser().parse_args(words[3:])
        assert (args.command, args.demo_excluded, args.set_to) == ("components", 0, "{components_json}")
        flat = " ".join(step_4.split())
        for phrase in ("write those entries, as Phase 6 lists them, each with the `export_name`, `export_type`, "
                       "`signature`, `params`, `return_type`, `source_file`, `source_line` and `citation` step 3 §5's "
                       "`add --field exports` takes, as one JSON list to `{read_by_eye_json}`",
                       "a Props contract's `params` null (Step 1 reads its fields after the call, and step 3 §5 "
                       "sends them with `patch`)",
                       "`--registry` when Phase 3's JSON lists `entries`, `--categories` only on the rerun below,",
                       "When it lists `unmatched_entries` (the registry entries no component joined, by name or by "
                       "file name), warn \"No component was found for {each of them}: their `available_in`, "
                       "`code_paths` and `props` stay empty.\"",
                       "name one from the folders of its `code_paths` (from its `name` and `description` when it has "
                       "none)",
                       "With a registry, display: \"**Parsed component catalog: {N} components across {M} "
                       "categories.**\"",
                       "{M} the `catalog_by_category` rows whose `category` is not null",
                       "When an entry's `category` is null, name one from the folders of its `code_paths`",
                       "run the command once more with `--categories`",
                       "warn \"Components were not sorted or counted: {its stderr, or 'skf-detect-registry.py is "
                       "missing, so re-install SKF'}.\", send the warning with step 3 §5's `add --field warnings`, and "
                       "go on with no `{components_json}`: never sort, link or count by hand."):
            assert phrase in flat, phrase
        # the sort and link rules live in the helper's docstring, not in the prose
        text = _text()
        for gone in ("Naming convention (primary)", "stripping the `Props` suffix", "A PascalCase value item",
                     "A type-only item", "Use a 3-level fallback chain"):
            assert gone not in text, gone
        doc = " ".join(_mod().__doc__.split())
        for rule in ("naming-convention a component named as the contract less its `Props` suffix",
                     "co-location a `.vue` contract's file component, or the only component in the contract's file",
                     "generic-param a component the contract's `declaration_signature_line` (else `signature`) "
                     "names right after `typeof`",
                     "or one in the contract's file whose own line names the contract inside `<...>`",
                     "Of several candidates, the one in the contract's file wins, then one in its folder, then one in "
                     "its variant, then the first by path.",
                     "whose name is PascalCase: upper-case first and not all upper-case (`MAX_ITEMS` is a shared "
                     "export)",
                     "an export whose `export_type` is `re-export` and whose name ends in `Props`",
                     "an `index.vue` its folder's name, so `Button/index.vue` gives `Button`",
                     "in PascalCase (`alert-dialog` gives `AlertDialog`)",
                     "a naming-convention link before a co-location one before a generic-param one",
                     "then a null category after the named ones of the same count, then category"):
            assert rule in doc, rule

    def test_phases_5_and_6_read_the_call(self):
        flat = " ".join(_phase(5).split())
        assert "**Skip this phase unless Step 4's call printed JSON whose `variants` is not empty**" in flat
        for token in ("**Variant consolidation: {components_unique} unique components across {variant_count} variants**",
                      "({components_total_with_variants} total including variants)",
                      "Primary variant: {the `variants` entry whose `primary` is true}",
                      "compare the Props contracts `links` gives for its files, and record each variant-specific "
                      "prop as a note"):
            assert token in flat, token
        for gone in ("Count unique components", "Use the primary variant", "no variant directories detected"):
            assert gone not in _text(), gone
        text = _text()
        six = text[text.index("### Phase 6:"):text.index("## RETURN PROTOCOL")]
        assert ("`component_stats` is Step 4's `stats_extra`, which the call wrote with `component_catalog` to "
                "`{components_json}`") in " ".join(six.split())
        for key in _mod().STATS_KEYS:
            assert f"`{key}`:" not in text, key
        assert "Linked component name" not in six and "Linked Props interface" not in six

    def test_phase_4_runs_the_component_library_recipes_once(self):
        phase_4 = _phase(4)
        [call] = [line for line in phase_4.splitlines() if line.startswith("uv run {extractPublicApiHelper}")]
        assert "--mode full" in call and "--recipe-set component-library" in call
        assert '--files-from "{scan_list}"' in call
        assert 'pass `--brief "{brief_file}"` in place of `--files-from "{scan_list}"`' in phase_4
        assert "A `missing` or `unreadable` issue is a listed file the runner could not read" in phase_4
        # it acts on the JSON's status, as the protocol does, never on the exit code
        assert "Act on the JSON's `status`, never on the exit code." in phase_4
        fallback = phase_4[phase_4.index("**On `no-ast-grep`"):phase_4.index("**Step 1 ")]
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
        assert "step 3 §2b may have amended it" in phase_2b and "`{brief_file}.bak`" in phase_2b
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
