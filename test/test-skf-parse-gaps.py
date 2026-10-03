#!/usr/bin/env python3
"""Tests for src/shared/scripts/skf-parse-gaps.py.

update-skill's gap-driven mode reads a test report's gaps through this
helper:
  - the ledger beside the report wins (run id from the frontmatter, else
    the file name); --ledger names another one; another schema_version is
    refused
  - without a ledger, the rendered Gap Report: the Gap Entry Format, older
    variants, multi-line remediation, fenced code, a doubled section
  - a Gap Report rendered from a ledger parses back to the same gaps
  - source citations, remediation path tokens: framework route names,
    Markdown link targets, Kotlin, Swift, C#, PHP, --ext, code that is not
    a path
  - --source-root: glob and folder expansion, route folders taken as
    written, brackets literal in a glob, a glob walk that follows no link
    and enters a skipped folder only when named, outside-root and symlink
    rejection, not-found and no-match, dedupe
  - --provenance-map: the extensions of the map's source files join the
    list; `paths`: the same root check on paths a step names itself
  - --provenance-map: each gap's `map_match`, gap-driven.md's lookup of its
    export (no citation, several same-name entries, a `./` or backslash
    path); `match`: the same lookup for a name a step takes elsewhere
  - `translate`: gap-driven.md §1's change manifest, every routed ledger
    category through the table, an unrouted one warned, a citation inside
    the skill package dropped, the answers it asks for (category, name,
    rescope, source file) with the gap's text to judge from and how it reads
    them, rescope asked of every remediation a person wrote and never of the
    ledger's own text, a rescope's amendment and exclude path, a rule R3
    gap's root check, and its CLI
"""

from __future__ import annotations

import doctest
import importlib.util
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "src" / "shared" / "scripts" / "skf-parse-gaps.py"
LEDGER_SCRIPT = REPO / "src" / "skf-test-skill" / "scripts" / "gap-ledger.py"

spec = importlib.util.spec_from_file_location("skf_parse_gaps", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

RUN_ID = "20260930T101010Z-4242-ab12"
EM_DASH = "\u2014"


def run(script: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def parse(*args: str) -> tuple[int, dict]:
    proc = run(SCRIPT, "parse", *args)
    return proc.returncode, json.loads(proc.stdout)


def write_report(folder: Path, body: str, *, run_id: str | None = RUN_ID, name_run_id: str = RUN_ID) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"test-report-demo-{name_run_id}.md"
    front = "---\nworkflowType: 'test-skill'\n"
    if run_id is not None:
        front += f"runId: '{run_id}'\n"
    front += "testResult: 'fail'\n---\n\n# Test Report: demo\n\n"
    path.write_text(front + textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
    return path


def write_ledger(path: Path, stage: str, records: list[dict]) -> Path:
    proc = run(LEDGER_SCRIPT, "append", "--ledger", str(path), "--stage", stage, stdin=json.dumps(records))
    assert proc.returncode == 0, proc.stdout
    return path


LEDGER_RECORDS = [
    {
        "severity": "Medium",
        "category": "missing-export",
        "title": "parseDate undocumented",
        "source": "src/index.ts",
        "remediation": "Document `parseDate` exported from `src/dates/parse.ts:12` (see src/dates/).",
        "export": "parseDate",
    },
    {
        "severity": "Critical",
        "category": "signature-mismatch",
        "title": "formatDate signature",
        "source": "src/dates/format.ts:42",
        "issue": "SKILL.md documents one parameter; the source takes two.",
        "remediation": "Update SKILL.md line 78 to match `src/dates/format.ts:42`.",
        "export": "formatDate",
    },
    {
        "severity": "High",
        "category": "broken-reference",
        "title": "Link to a missing reference file",
        "source": "SKILL.md:120",
        "remediation": "Create `references/api.md` or remove the link.",
    },
]

LEGACY_GAP_REPORT = f"""
## Coverage Analysis

### GAP-900: Not in the Gap Report

**Severity:** Critical
**Source:** src/nowhere.ts:1

## Gap Report

**Total Gaps:** 3

### Remediation Summary

| Severity | Count | Estimated Effort |
|----------|-------|-----------------|
| Critical | 1 | reading source |

### GAP-001: Missing export `createStore`

**Severity:** Critical
**Category:** Coverage
**Source:** `packages/core/src/store.ts:33`

**Issue:** `createStore` is exported but not documented.

**Remediation:** Document `createStore(options)` from
`packages/core/src/store.ts:33`, then list it in the exports table.

```ts
### not a heading: this sits in a fence
export function createStore(options: Options): Store
```

---

### GAP-002 {EM_DASH} Signature mismatch for useStore

- **Severity:** **High**
- **Category:** Coherence
- **Source:** @storybook/addon-docs control primitives
- **Remediation:** Re-extract `packages/hooks` and update the signature.

#### GAP-003: Description triggers

**Severity**: Low
**Category:** Structural

**Remediation:**

Add negative triggers to the description.

### Discovery Quality

| Prompt | Selected | Result |
|--------|----------|--------|
| a | demo | PASS |

## Something Else

### GAP-901: Also not in the Gap Report

**Severity:** High
"""


@pytest.fixture
def version_dir(tmp_path: Path) -> Path:
    return tmp_path / "forge-data" / "demo" / "1.0.0"


def test_embedded_doctests_pass():
    results = doctest.testmod(mod, verbose=False)
    assert results.failed == 0, f"{results.failed} doctest(s) failed"


# --------------------------------------------------------------------------
# Ledger
# --------------------------------------------------------------------------


class TestLedger:
    def test_ledger_beside_the_report_wins(self, version_dir: Path):
        ledger = write_ledger(version_dir / f"test-findings-{RUN_ID}.json", "coverage-check", LEDGER_RECORDS)
        report = write_report(version_dir, LEGACY_GAP_REPORT)
        code, out = parse("--report", str(report))
        assert code == 0
        assert out["read_from"] == "ledger"
        assert out["ledger_path"] == str(ledger)
        assert out["report_path"] == str(report)
        assert out["gap_count"] == 3
        assert out["counts"] == {"Critical": 1, "High": 1, "Medium": 1, "Low": 0, "Info": 0}
        assert [g["id"] for g in out["gaps"]] == ["GAP-002", "GAP-003", "GAP-001"]
        critical = out["gaps"][0]
        assert critical == {
            "id": "GAP-002",
            "title": "formatDate signature",
            "severity": "Critical",
            "category": "signature-mismatch",
            "category_group": "Coverage",
            "source": "src/dates/format.ts:42",
            "source_citation": {"file": "src/dates/format.ts", "line": 42},
            "export": "formatDate",
            "issue": "SKILL.md documents one parameter; the source takes two.",
            "remediation": "Update SKILL.md line 78 to match `src/dates/format.ts:42`.",
            "remediation_paths": ["src/dates/format.ts"],
        }
        medium = out["gaps"][2]
        assert medium["category"] == "missing-export"
        assert medium["source_citation"] is None
        assert medium["remediation_paths"] == ["src/dates/parse.ts", "src/dates/"]
        assert "resolved_files" not in out
        assert out["source_root"] is None

    def test_run_id_from_the_file_name(self, version_dir: Path):
        write_ledger(version_dir / f"test-findings-{RUN_ID}.json", "coverage-check", LEDGER_RECORDS)
        report = write_report(version_dir, "## Gap Report\n", run_id=None)
        _, out = parse("--report", str(report))
        assert out["read_from"] == "ledger"

    def test_unsafe_run_id_never_leaves_the_folder(self, version_dir: Path, tmp_path: Path):
        write_ledger(tmp_path / "test-findings-x.json", "coverage-check", LEDGER_RECORDS)
        report = write_report(version_dir, LEGACY_GAP_REPORT, run_id="../../../x", name_run_id="draft")
        _, out = parse("--report", str(report))
        assert out["read_from"] == "gap-report"

    def test_explicit_ledger_without_a_report(self, tmp_path: Path):
        ledger = write_ledger(tmp_path / "findings.json", "coverage-check", LEDGER_RECORDS)
        code, out = parse("--ledger", str(ledger))
        assert code == 0
        assert out["report_path"] is None
        assert out["gap_count"] == 3

    def test_explicit_ledger_that_is_missing(self, version_dir: Path):
        report = write_report(version_dir, LEGACY_GAP_REPORT)
        code, out = parse("--report", str(report), "--ledger", str(version_dir / "nope.json"))
        assert code == 1
        assert out["code"] == "LEDGER_MISSING"

    def test_invalid_ledger(self, version_dir: Path):
        version_dir.mkdir(parents=True)
        (version_dir / f"test-findings-{RUN_ID}.json").write_text('{"records": [{"id": "GAP-001", "severity": "Blocker"}]}', encoding="utf-8")
        report = write_report(version_dir, LEGACY_GAP_REPORT)
        code, out = parse("--report", str(report))
        assert code == 1
        assert out["code"] == "LEDGER_INVALID"

    def test_ledger_of_another_schema_version_is_refused(self, version_dir: Path):
        version_dir.mkdir(parents=True)
        ledger = version_dir / f"test-findings-{RUN_ID}.json"
        ledger.write_text(json.dumps({"schema_version": 2, "stages": [], "records": []}), encoding="utf-8")
        report = write_report(version_dir, LEGACY_GAP_REPORT)
        code, out = parse("--report", str(report))
        assert code == 1
        assert out["code"] == "LEDGER_INVALID"
        assert "schema_version 2" in out["error"]

    def test_empty_ledger_means_no_gaps(self, version_dir: Path):
        write_ledger(version_dir / f"test-findings-{RUN_ID}.json", "coverage-check", [])
        report = write_report(version_dir, LEGACY_GAP_REPORT)
        _, out = parse("--report", str(report))
        assert out["read_from"] == "ledger"
        assert out["gap_count"] == 0


# --------------------------------------------------------------------------
# Rendered Gap Report
# --------------------------------------------------------------------------


class TestGapReport:
    def test_legacy_entries(self, version_dir: Path):
        report = write_report(version_dir, LEGACY_GAP_REPORT)
        code, out = parse("--report", str(report))
        assert code == 0
        assert out["read_from"] == "gap-report"
        assert out["ledger_path"] is None
        assert [g["id"] for g in out["gaps"]] == ["GAP-001", "GAP-002", "GAP-003"]
        first, second, third = out["gaps"]

        assert first["title"] == "Missing export `createStore`"
        assert first["severity"] == "Critical"
        assert first["category"] is None
        assert first["category_group"] == "Coverage"
        assert first["source"] == "packages/core/src/store.ts:33"
        assert first["source_citation"] == {"file": "packages/core/src/store.ts", "line": 33}
        assert first["issue"] == "`createStore` is exported but not documented."
        assert first["remediation"].startswith("Document `createStore(options)` from\n")
        assert "### not a heading: this sits in a fence" in first["remediation"]
        assert first["remediation"].rstrip().endswith("```")
        assert first["remediation_paths"] == ["packages/core/src/store.ts"]

        assert second["title"] == "Signature mismatch for useStore"
        assert second["severity"] == "High"
        assert second["category_group"] == "Coherence"
        assert second["source"] == "@storybook/addon-docs control primitives"
        assert second["source_citation"] is None
        assert second["remediation_paths"] == ["packages/hooks"]

        assert third["severity"] == "Low"
        assert third["remediation"] == "Add negative triggers to the description."
        assert "Discovery" not in third["remediation"]
        assert out["warnings"] == []

    def test_doubled_section_placeholder_first(self, version_dir: Path):
        appended = LEGACY_GAP_REPORT.split("## Gap Report", 1)[1]
        body = "## Gap Report\n\n<!-- Populated by report -->\n\n## Gap Report\n" + appended
        report = write_report(version_dir, body)
        _, out = parse("--report", str(report))
        assert [g["id"] for g in out["gaps"]] == ["GAP-001", "GAP-002", "GAP-003"]

    def test_duplicate_id_is_kept_once(self, version_dir: Path):
        entry = "### GAP-001: Twice\n\n**Severity:** High\n**Source:** a.ts:1\n\n**Remediation:** Fix `a.ts`.\n\n"
        report = write_report(version_dir, "## Gap Report\n\n" + entry + "## Gap Report\n\n" + entry.replace("High", "Low"))
        _, out = parse("--report", str(report))
        assert out["gap_count"] == 1
        assert out["gaps"][0]["severity"] == "High"
        assert any("more than once" in w for w in out["warnings"])

    def test_placeholder_only(self, version_dir: Path):
        report = write_report(version_dir, "## Gap Report\n\n<!-- Populated by report -->\n")
        _, out = parse("--report", str(report))
        assert out["gap_count"] == 0
        assert out["warnings"] == ["the Gap Report section holds no GAP entries"]

    def test_no_gap_report_section(self, version_dir: Path):
        report = write_report(version_dir, "## Coverage Analysis\n\nNothing.\n")
        _, out = parse("--report", str(report))
        assert out["gap_count"] == 0
        assert out["warnings"] == ["the report has no ## Gap Report section"]

    def test_unreadable_severity_is_warned(self, version_dir: Path):
        report = write_report(version_dir, "## Gap Report\n\n### GAP-004: Odd\n\n**Severity:** Blocker\n")
        _, out = parse("--report", str(report))
        assert out["gaps"][0]["severity"] is None
        assert any("GAP-004" in w for w in out["warnings"])

    def test_rendered_ledger_parses_back_to_the_same_gaps(self, version_dir: Path, tmp_path: Path):
        ledger = write_ledger(tmp_path / "elsewhere" / f"test-findings-{RUN_ID}.json", "coverage-check", LEDGER_RECORDS)
        rendered = run(LEDGER_SCRIPT, "render", "--ledger", str(ledger), "--heading").stdout
        report = write_report(version_dir, rendered + "\n### Discovery Quality\n\nAll prompts routed.\n")
        _, from_report = parse("--report", str(report))
        _, from_ledger = parse("--ledger", str(ledger))
        assert from_report["read_from"] == "gap-report"
        assert from_report["gaps"] == from_ledger["gaps"]
        assert from_report["counts"] == from_ledger["counts"]


# --------------------------------------------------------------------------
# Citations and path tokens
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("src/a.ts:12", {"file": "src/a.ts", "line": 12}),
        ("`src/a.ts:12-20`", {"file": "src/a.ts", "line": 12}),
        ("src/a.ts:12:4", {"file": "src/a.ts", "line": 12}),
        ("src/a.py#L7", {"file": "src/a.py", "line": 7}),
        ("src/a.ts", None),
        ("src/a.ts:12 (formatDate)", None),
        ("SKILL.md line 78", None),
        ("https://example.com:443", None),
        (None, None),
    ],
)
def test_source_citation(source, expected):
    assert mod.source_citation(source) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Fix `src/a.ts:10` and src/b.tsx:3-9, then src/a.ts again.", ["src/a.ts", "src/b.tsx"]),
        ("See lib/x.py#L4 and pkg/y.rs.", ["lib/x.py", "pkg/y.rs"]),
        ("Scan `src/**/*.vue` and packages/*/src/index.ts", ["src/**/*.vue", "packages/*/src/index.ts"]),
        ("Walk src/hooks/ for the export.", ["src/hooks/"]),
        ("Update references/api.md and SKILL.md.", []),
        ("Use `react-dom/client` and/or 3/4 of `@scope/pkg`.", ["react-dom/client"]),
        ("Like Node.js and Vue.js do, read main.go and util.h.", ["main.go", "util.h"]),
        ("Link: https://github.com/o/r/blob/main/src/a.ts", []),
        ("`(date: Date) => string` is wrong", []),
        ("", []),
        (None, []),
        # Framework route names, bare and in code spans.
        (
            "Re-extract app/[slug]/page.tsx and app/[...slug]/page.tsx.",
            ["app/[slug]/page.tsx", "app/[...slug]/page.tsx"],
        ),
        (
            "See `app/(group)/page.tsx` and (app/routes/posts.$slug.tsx).",
            ["app/(group)/page.tsx", "app/routes/posts.$slug.tsx"],
        ),
        (
            "Scan `app/(shop)/`, app/[[...slug]]/ and `src/routes/[id=integer]/+page.ts`",
            ["app/(shop)/", "app/[[...slug]]/", "src/routes/[id=integer]/+page.ts"],
        ),
        ("`Math.floor(x/2)`, `arr[i/2]` and `key=src/a` are code, not paths", []),
        # A Markdown link counts by its target.
        ("Document it (see [the store](src/store.ts) and [`lib/a.py`](lib/a.py)).", ["src/store.ts", "lib/a.py"]),
        (
            "Fix src/main/kotlin/com/acme/Store.kt:12, build.gradle.kts, Sources/Acme/Model.swift, src/Api.cs and lib/a.php.",
            ["src/main/kotlin/com/acme/Store.kt", "build.gradle.kts", "Sources/Acme/Model.swift", "src/Api.cs", "lib/a.php"],
        ),
    ],
)
def test_remediation_paths(text, expected):
    assert mod.remediation_paths(text) == expected


def test_remediation_paths_with_another_extension():
    text = "Re-extract `web/App.vue` and web/Button.svelte."
    assert mod.remediation_paths(text) == []
    assert mod.remediation_paths(text, mod._SOURCE_SUFFIXES | {".vue", ".svelte"}) == [
        "web/App.vue",
        "web/Button.svelte",
    ]


# --------------------------------------------------------------------------
# --source-root
# --------------------------------------------------------------------------


def _write_files(root: Path, *rels: str) -> None:
    for rel in rels:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("export {}\n", encoding="utf-8")


def _source_tree(root: Path) -> None:
    _write_files(
        root,
        "src/dates/format.ts",
        "src/dates/parse.ts",
        "src/dates/README.md",
        "src/dates/node_modules/dep/index.ts",
        "src/dates/.cache/x.ts",
        "src/index.ts",
        "lib/x.py",
    )


def _symlink_or_skip(target: Path, link: Path, *, directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks unavailable: {exc}")


def _resolve(tokens: list[str], root: Path) -> tuple[list[str], list[dict]]:
    return mod.resolve_paths(tokens, Path(os.path.realpath(root)))


class TestSourceRoot:
    def test_file_folder_and_glob(self, tmp_path: Path):
        root = tmp_path / "repo"
        _source_tree(root)
        resolved, rejected = _resolve(["src/dates/format.ts", "src/dates/", "lib/*.py"], root)
        assert resolved == ["src/dates/format.ts", "src/dates/parse.ts", "lib/x.py"]
        assert rejected == []

    def test_recursive_glob(self, tmp_path: Path):
        root = tmp_path / "repo"
        _source_tree(root)
        resolved, _ = _resolve(["src/**/*.ts"], root)
        assert resolved == ["src/dates/format.ts", "src/dates/parse.ts", "src/index.ts"]

    def test_outside_root(self, tmp_path: Path):
        root = tmp_path / "repo"
        _source_tree(root)
        (tmp_path / "secret.ts").write_text("x\n", encoding="utf-8")
        resolved, rejected = _resolve(["../secret.ts", str(tmp_path / "secret.ts"), "../*.ts", "src/../../*.ts"], root)
        assert resolved == []
        # A glob whose fixed folders leave the root is refused whole, so no
        # name from outside the root reaches the output.
        assert rejected == [
            {"path": "../secret.ts", "reason": "outside-root"},
            {"path": str(tmp_path / "secret.ts"), "reason": "outside-root"},
            {"path": "../*.ts", "reason": "outside-root"},
            {"path": "src/../../*.ts", "reason": "outside-root"},
        ]

    def test_not_found_and_no_match(self, tmp_path: Path):
        root = tmp_path / "repo"
        _source_tree(root)
        (root / "empty").mkdir()
        resolved, rejected = _resolve(["src/gone.ts", "empty/", "src/**/*.rs"], root)
        assert resolved == []
        assert rejected == [
            {"path": "src/gone.ts", "reason": "not-found"},
            {"path": "empty/", "reason": "no-match"},
            {"path": "src/**/*.rs", "reason": "no-match"},
        ]

    def test_symlinked_file_outside_root(self, tmp_path: Path):
        root = tmp_path / "repo"
        _source_tree(root)
        outside = tmp_path / "outside.ts"
        outside.write_text("x\n", encoding="utf-8")
        _symlink_or_skip(outside, root / "src" / "escape.ts")
        resolved, rejected = _resolve(["src/escape.ts", "src/*.ts"], root)
        assert resolved == ["src/index.ts"]
        assert rejected == [{"path": "src/escape.ts", "reason": "symlink-outside-root"}]

    def test_symlinked_folder_outside_root(self, tmp_path: Path):
        root = tmp_path / "repo"
        _source_tree(root)
        outside = tmp_path / "vendor"
        outside.mkdir()
        (outside / "v.ts").write_text("x\n", encoding="utf-8")
        _symlink_or_skip(outside, root / "linked", directory=True)
        resolved, rejected = _resolve(["linked/v.ts", "linked/", "linked/*.ts"], root)
        assert resolved == []
        assert rejected == [
            {"path": "linked/v.ts", "reason": "symlink-outside-root"},
            {"path": "linked/", "reason": "symlink-outside-root"},
            {"path": "linked/*.ts", "reason": "symlink-outside-root"},
        ]

    def test_link_inside_root_counts_as_its_target(self, tmp_path: Path):
        root = tmp_path / "repo"
        _source_tree(root)
        _symlink_or_skip(root / "src" / "index.ts", root / "lib" / "alias.ts")
        resolved, rejected = _resolve(["lib/alias.ts", "src/index.ts"], root)
        assert resolved == ["src/index.ts"]
        assert rejected == []

    def test_route_folders_resolve_as_written(self, tmp_path: Path):
        routes = ["app/[slug]/page.tsx", "app/[...slug]/page.tsx", "app/(group)/page.tsx", "app/routes/posts.$slug.tsx"]
        root = tmp_path / "repo"
        _write_files(root, *routes)
        resolved, rejected = _resolve(routes, root)
        assert resolved == routes
        assert rejected == []

    def test_brackets_in_a_glob_are_literal(self, tmp_path: Path):
        root = tmp_path / "repo"
        # As a character class, [slug] would match the folders s, l, u and g.
        _write_files(root, "app/[slug]/page.tsx", "app/[slug]/layout.tsx", "app/s/page.tsx", "app/(group)/about/page.tsx")
        resolved, rejected = _resolve(["app/[slug]/*.tsx", "app/(group)/**/*.tsx"], root)
        assert resolved == ["app/[slug]/layout.tsx", "app/[slug]/page.tsx", "app/(group)/about/page.tsx"]
        assert rejected == []

    def test_kotlin_file_and_swift_folder(self, tmp_path: Path):
        root = tmp_path / "repo"
        _write_files(root, "src/main/kotlin/com/acme/Store.kt", "Sources/Acme/Model.swift", "Sources/Acme/View.swift", "Sources/Acme/Info.plist")
        tokens = mod.remediation_paths("Fix src/main/kotlin/com/acme/Store.kt:12, then scan Sources/Acme/ for the rest.")
        assert tokens == ["src/main/kotlin/com/acme/Store.kt", "Sources/Acme/"]
        resolved, rejected = _resolve(tokens, root)
        assert resolved == ["src/main/kotlin/com/acme/Store.kt", "Sources/Acme/Model.swift", "Sources/Acme/View.swift"]
        assert rejected == []

    def test_glob_walk_follows_no_folder_link(self, tmp_path: Path):
        # Links back up the tree: a walk that followed them would list the
        # same files under ever longer paths (with two such links in one
        # folder, without end).
        root = tmp_path / "repo"
        _source_tree(root)
        _symlink_or_skip(root / "src", root / "src" / "loop", directory=True)
        _symlink_or_skip(root / "src" / "dates", root / "src" / "dates" / "again", directory=True)
        real_root = Path(os.path.realpath(root))
        walked = mod._glob_walk(real_root / "src", real_root, "**", False)
        assert "src/loop" in walked and "src/dates/again" in walked  # listed
        assert not [p for p in walked if p.startswith(("src/loop/", "src/dates/again/"))]  # never entered
        resolved, rejected = _resolve(["src/**/*.ts", "src/**"], root)
        assert resolved == ["src/dates/format.ts", "src/dates/parse.ts", "src/index.ts", "src/dates/README.md"]
        assert rejected == []

    def test_glob_enters_a_skipped_folder_only_when_it_names_it(self, tmp_path: Path):
        root = tmp_path / "repo"
        _source_tree(root)
        resolved, rejected = _resolve(["src/**/node_modules/**/*.ts", "src/**/.cache/*.ts"], root)
        assert resolved == ["src/dates/node_modules/dep/index.ts", "src/dates/.cache/x.ts"]
        assert rejected == []

    def test_cli_resolves_and_dedupes_across_gaps(self, version_dir: Path, tmp_path: Path):
        root = tmp_path / "repo"
        _source_tree(root)
        write_ledger(version_dir / f"test-findings-{RUN_ID}.json", "coverage-check", LEDGER_RECORDS)
        report = write_report(version_dir, "## Gap Report\n")
        code, out = parse("--report", str(report), "--source-root", str(root))
        assert code == 0
        assert out["source_root"] == os.path.realpath(root)
        by_id = {g["id"]: g for g in out["gaps"]}
        assert by_id["GAP-001"]["resolved_paths"] == ["src/dates/parse.ts", "src/dates/format.ts"]
        assert by_id["GAP-002"]["resolved_paths"] == ["src/dates/format.ts"]
        assert by_id["GAP-003"]["resolved_paths"] == []
        assert by_id["GAP-003"]["rejected_paths"] == []
        assert out["resolved_files"] == ["src/dates/format.ts", "src/dates/parse.ts"]


# --------------------------------------------------------------------------
# CLI errors
# --------------------------------------------------------------------------


def test_needs_a_report_or_a_ledger():
    code, out = parse()
    assert code == 1
    assert out["code"] == "INVALID_INPUT"


def test_missing_report(tmp_path: Path):
    code, out = parse("--report", str(tmp_path / "nope.md"))
    assert code == 1
    assert out["code"] == "REPORT_MISSING"


def test_source_root_must_be_a_folder(version_dir: Path, tmp_path: Path):
    report = write_report(version_dir, LEGACY_GAP_REPORT)
    code, out = parse("--report", str(report), "--source-root", str(tmp_path / "nope"))
    assert code == 1
    assert out["code"] == "INVALID_INPUT"


def test_ext_adds_a_source_extension(tmp_path: Path):
    root = tmp_path / "repo"
    _write_files(root, "web/App.vue", "web/Button.vue", "web/util.ts")
    gap = {
        "severity": "High",
        "category": "missing-export",
        "title": "Button undocumented",
        "source": "web components",
        "remediation": "Re-extract `web/App.vue` and the rest of web/.",
    }
    ledger = write_ledger(tmp_path / "findings.json", "coverage-check", [gap])
    _, plain = parse("--ledger", str(ledger), "--source-root", str(root))
    assert plain["gaps"][0]["remediation_paths"] == ["web/"]
    assert plain["resolved_files"] == ["web/util.ts"]
    code, out = parse("--ledger", str(ledger), "--source-root", str(root), "--ext", "vue", "--ext", ".svelte")
    assert code == 0
    assert out["gaps"][0]["remediation_paths"] == ["web/App.vue", "web/"]
    assert out["resolved_files"] == ["web/App.vue", "web/Button.vue", "web/util.ts"]


@pytest.mark.parametrize("value", ["", "*.vue", "a/b", ".."])
def test_ext_must_be_a_file_extension(tmp_path: Path, value: str):
    ledger = write_ledger(tmp_path / "findings.json", "coverage-check", LEDGER_RECORDS)
    code, out = parse("--ledger", str(ledger), "--ext", value)
    assert code == 1
    assert out["code"] == "INVALID_INPUT"


def test_provenance_map_adds_its_source_extensions(tmp_path: Path):
    root = tmp_path / "repo"
    _write_files(root, "web/App.vue", "web/Button.vue", "web/util.ts")
    gap = {"severity": "High", "category": "missing-export", "title": "Button undocumented",
           "source": "web components", "remediation": "Re-extract `web/App.vue`."}
    ledger = write_ledger(tmp_path / "findings.json", "coverage-check", [gap])
    prov = tmp_path / "provenance-map.json"
    prov.write_bytes(json.dumps({"entries": [{"export_name": "App", "source_file": "web/App.vue"},
                                             {"export_name": "x", "source_file": "README"}],
                                 "file_entries": [{"source_file": "docs/guide.md"}]}).encode("utf-8"))
    code, out = parse("--ledger", str(ledger), "--source-root", str(root), "--provenance-map", str(prov))
    assert code == 0, out
    assert out["gaps"][0]["remediation_paths"] == ["web/App.vue"]
    assert out["resolved_files"] == ["web/App.vue"]
    assert mod.map_extensions(mod.map_entries_of(prov)) == ["vue"]  # file_entries (docs, scripts) add no extension


@pytest.mark.parametrize("content", [b"{nope", b"[1]"], ids=["invalid-json", "not-an-object"])
def test_an_unreadable_provenance_map_is_invalid_input(tmp_path: Path, content: bytes):
    ledger = write_ledger(tmp_path / "findings.json", "coverage-check", LEDGER_RECORDS)
    prov = tmp_path / "provenance-map.json"
    prov.write_bytes(content)
    code, out = parse("--ledger", str(ledger), "--provenance-map", str(prov))
    assert code == 1 and out["code"] == "INVALID_INPUT"


def test_paths_checks_a_named_path_against_the_root(tmp_path: Path):
    root = tmp_path / "repo"
    _source_tree(root)
    (tmp_path / "secret.ts").write_bytes(b"export {}\n")
    proc = run(SCRIPT, "paths", "--source-root", str(root), "src/index.ts:12", "src/dates/", "../secret.ts",
               "src/missing.ts")
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["status"] == "ok"
    assert out["resolved_paths"] == ["src/index.ts", "src/dates/format.ts", "src/dates/parse.ts"]
    assert out["rejected_paths"] == [{"path": "../secret.ts", "reason": "outside-root"},
                                     {"path": "src/missing.ts", "reason": "not-found"}]


def test_paths_refuses_a_link_out_of_the_root(tmp_path: Path):
    root = tmp_path / "repo"
    _write_files(root, "src/index.ts")
    outside = tmp_path / "outside.ts"
    outside.write_bytes(b"export {}\n")
    _symlink_or_skip(outside, root / "src" / "linked.ts")
    proc = run(SCRIPT, "paths", "--source-root", str(root), "src/linked.ts")
    assert json.loads(proc.stdout)["rejected_paths"] == [{"path": "src/linked.ts", "reason": "symlink-outside-root"}]


def test_paths_needs_a_folder_root(tmp_path: Path):
    proc = run(SCRIPT, "paths", "--source-root", str(tmp_path / "nope"), "a.ts")
    assert proc.returncode == 1 and json.loads(proc.stdout)["code"] == "INVALID_INPUT"



# --------------------------------------------------------------------------
# map_match: the provenance-map lookup of a gap's export (step 5b determinism-4)
# --------------------------------------------------------------------------


def _entry(name: str, path: str, line: int, export_type: str = "function") -> dict:
    return {"export_name": name, "source_file": path, "source_line": line, "export_type": export_type}


MAP_ENTRIES = [
    _entry("search", "pkg/api.py", 5),
    _entry("parse", "pkg/a.py", 10),
    _entry("parse", "pkg/b.py", 3),
    _entry("dup", "pkg/c.py", 1),
    _entry("dup", "pkg/c.py", 9, "class"),
]


def _view(entry: dict) -> dict:
    return {key: entry[key] for key in ("source_file", "source_line", "export_type")}


@pytest.mark.parametrize("name, citation, status, entry", [
    ("search", None, "found", MAP_ENTRIES[0]),
    ("parse", None, "ambiguous", None),
    ("missing", None, "not-found", None),
    ("parse", {"file": "pkg/b.py", "line": 99}, "found", MAP_ENTRIES[2]),
    ("parse", {"file": "pkg/other.py", "line": 3}, "not-found", None),
    ("dup", {"file": "pkg/c.py", "line": 9}, "found", MAP_ENTRIES[4]),
    ("dup", {"file": "pkg/c.py", "line": 4}, "ambiguous", None),
    ("search", {"file": "./pkg/api.py", "line": 5}, "found", MAP_ENTRIES[0]),
    ("parse", {"file": "pkg\\a.py", "line": 10}, "found", MAP_ENTRIES[1]),
], ids=["no-citation-one", "no-citation-several", "no-citation-none", "citation-picks-the-file",
        "citation-names-another-file", "citation-line-breaks-the-tie", "citation-line-matches-none",
        "dot-slash-path", "backslash-path"])
def test_map_match(name, citation, status, entry):
    match = mod.map_match(MAP_ENTRIES, name, citation)
    assert match["status"] == status
    assert match["entry"] == (_view(entry) if entry else None)
    assert match["candidates"] == [_view(e) for e in MAP_ENTRIES if e["export_name"] == name]


def test_parse_adds_each_gap_its_map_match(tmp_path: Path):
    ledger = write_ledger(tmp_path / "findings.json", "coverage-check", LEDGER_RECORDS)
    prov = tmp_path / "provenance-map.json"
    prov.write_bytes(json.dumps({"entries": [_entry("formatDate", "src/dates/format.ts", 42),
                                             _entry("parseDate", "src/dates/parse.ts", 12),
                                             _entry("parseDate", "src/legacy/parse.ts", 4)]}).encode("utf-8"))
    code, out = parse("--ledger", str(ledger), "--provenance-map", str(prov))
    assert code == 0, out
    by_id = {gap["title"]: gap for gap in out["gaps"]}
    # a cited export is keyed on its citation
    assert by_id["formatDate signature"]["map_match"] == {
        "status": "found", "entry": _view(_entry("formatDate", "src/dates/format.ts", 42)),
        "candidates": [_view(_entry("formatDate", "src/dates/format.ts", 42))]}
    # an uncited one that two entries share is left for a person
    assert by_id["parseDate undocumented"]["map_match"]["status"] == "ambiguous"
    # a gap with no export has no lookup
    assert by_id["Link to a missing reference file"]["map_match"] is None
    # without the map, no gap carries the key
    code, out = parse("--ledger", str(ledger))
    assert all("map_match" not in gap for gap in out["gaps"])


def test_match_looks_a_name_up_with_its_citation(tmp_path: Path):
    prov = tmp_path / "provenance-map.json"
    prov.write_bytes(json.dumps({"entries": MAP_ENTRIES}).encode("utf-8"))
    proc = run(SCRIPT, "match", "--provenance-map", str(prov), "--name", "parse", "--citation", "pkg/b.py:3")
    assert proc.returncode == 0, proc.stdout
    out = json.loads(proc.stdout)
    assert (out["status"], out["citation"], out["map_match"]["status"]) == ("ok", {"file": "pkg/b.py", "line": 3},
                                                                           "found")
    proc = run(SCRIPT, "match", "--provenance-map", str(prov), "--name", "parse")
    assert json.loads(proc.stdout)["map_match"]["status"] == "ambiguous"
    proc = run(SCRIPT, "match", "--provenance-map", str(prov), "--name", "parse", "--citation", "a region of pkg")
    assert proc.returncode == 1 and json.loads(proc.stdout)["code"] == "INVALID_INPUT"


def test_usage_error_exits_2():
    proc = run(SCRIPT, "parse", "--no-such-flag")
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert "--no-such-flag" in proc.stderr


# --------------------------------------------------------------------------
# translate: update-skill gap-driven.md §1's change manifest
# --------------------------------------------------------------------------

_LEDGER = None


def _ledger():
    """gap-ledger.py, the script that writes the gaps translate reads."""
    global _LEDGER
    if _LEDGER is None:
        spec = importlib.util.spec_from_file_location("skf_gap_ledger_translate", LEDGER_SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        _LEDGER = module
    return _LEDGER


def _ledger_categories() -> set[str]:
    return set(_ledger().CATEGORIES)


def _gap(gid: str, category: str | None, *, export: str | None = "thing", severity: str = "High",
         citation: dict | None = None, remediation: str | None = None, title: str = "a gap", **extra) -> dict:
    """One gap as parse prints it. A missing export or type takes the remediation the ledger writes for it."""
    if remediation is None:
        remediation = _ledger()._missing_export(export or "thing", "pkg/api.py:5", "metadata.json",
                                                "type" if category == "missing-type" else "export")["remediation"] \
            if category in mod.RESCOPE_CATEGORIES else "Fix it."
    return {"id": gid, "title": title, "severity": severity, "category": category, "category_group": None,
            "source": None, "source_citation": citation, "export": export, "issue": None,
            "remediation": remediation, "remediation_paths": extra.pop("remediation_paths", []),
            "resolved_paths": extra.pop("resolved_paths", []), "rejected_paths": extra.pop("rejected_paths", []),
            **extra}


def _parsed(*gaps: dict, source_root: str | None = None, warnings: list | None = None) -> dict:
    return {"status": "ok", "read_from": "ledger", "source_root": source_root, "gap_count": len(gaps),
            "gaps": list(gaps), "warnings": warnings or []}


def _translate(*gaps: dict, judgments: dict | None = None, entries: list | None = None, **kw) -> tuple:
    return mod.translate_gaps(_parsed(*gaps, **{k: kw.pop(k) for k in ("source_root", "warnings") if k in kw}),
                              entries if entries is not None else MAP_ENTRIES, judgments or {},
                              today="2026-10-03", **kw)


def test_translate_routes_every_routed_ledger_category_by_the_table():
    assert set(mod.CHANGE_CATEGORIES) <= _ledger_categories()
    gaps = [_gap(f"GAP-{i:03d}", category) for i, category in enumerate(sorted(mod.CHANGE_CATEGORIES), start=1)]
    manifest, summary = _translate(*gaps)
    assert summary["status"] == "written" and summary["gap_count"] == len(gaps), summary
    assert {e["category"]: e["change_category"] for e in manifest["entries"]} == mod.CHANGE_CATEGORIES
    assert manifest["mode"] == "gap-driven" and summary["not_routed"] == []


def test_translate_leaves_any_other_category_unrouted():
    manifest, summary = _translate(_gap("GAP-001", "observation", title="style"),
                                   _gap("GAP-002", "missing-export", export="search"))
    assert [e["gap_id"] for e in manifest["entries"]] == ["GAP-002"]
    assert summary["not_routed"] == [{"id": "GAP-001", "title": "style", "category": "observation"}]
    assert "test-report: not routed: GAP-001 (observation)" in summary["warnings"]


def test_translate_writes_each_entry_in_the_documented_shape():
    gap = _gap("GAP-001", "signature-mismatch", export="search", citation={"file": "pkg/api.py", "line": 5},
               remediation="Update to match `pkg/api.py:5`.", remediation_paths=["pkg/api.py"],
               resolved_paths=["pkg/api.py"])
    manifest, _ = _translate(gap)
    [entry] = manifest["entries"]
    assert list(entry) == ["name", "gap_id", "category", "severity", "source_citation", "remediation_paths",
                           "resolved_paths", "rejected_paths", "change_category", "remediation", "map_match"]
    assert entry["remediation"] == "Update to match `pkg/api.py:5`."
    assert entry["map_match"] == mod.map_match(MAP_ENTRIES, "search", {"file": "pkg/api.py", "line": 5})


@pytest.mark.parametrize("path, inside", [
    ("SKILL.md", True), ("references/api.md", True), ("{skill_package}/references/api.md", True),
    ("skills/lib/1.0.0/lib/SKILL.md", True), (".\\references\\api.md", True), ("src/api.ts", False),
    ("docs/guide.md", False), ("references/nested/api.md", False),
], ids=["skill-md", "reference", "through-skill-package", "package-path", "backslashes", "source", "other-md",
        "nested-reference"])
def test_in_skill_package(path, inside):
    assert mod.in_skill_package({"file": path, "line": 4}) is inside


def test_translate_drops_a_citation_inside_the_skill_package():
    gap = _gap("GAP-001", "split-body-mismatch", export="parse", citation={"file": "references/api.md", "line": 4})
    manifest, _ = _translate(gap)
    [entry] = manifest["entries"]
    assert "source_citation" not in entry and entry["change_category"] == "STRUCTURAL_FIX"
    # the lookup keys on the name alone: two map entries share it
    assert entry["map_match"]["status"] == "ambiguous"


def test_translate_asks_what_it_cannot_decide():
    gaps = [
        _gap("GAP-001", None, export=None, title="Missing export: fetchAll"),
        _gap("GAP-002", "signature-mismatch", export=None, title="fetchAll signature"),
        _gap("GAP-003", "missing-export", export="internalThing", severity="Medium",
             remediation="internalThing is out of scope: rescope it."),
        _gap("GAP-004", "missing-export", export="fresh", severity="Medium", remediation="Document `fresh`."),
        _gap("GAP-005", "broken-reference", export=None),
    ]
    manifest, summary = _translate(*gaps)
    assert manifest is None and summary["status"] == "needs-judgment"
    assert [(n["gap_id"], n["needs"]) for n in summary["needs_judgment"]] == [
        ("GAP-001", ["category", "name"]), ("GAP-002", ["name"]), ("GAP-003", ["rescope"]), ("GAP-004", ["rescope"])]
    # each item carries the gap's own text, to judge from without reopening gaps.json
    assert summary["needs_judgment"][2] == {
        "gap_id": "GAP-003", "title": "a gap", "category": "missing-export", "issue": None,
        "remediation": "internalThing is out of scope: rescope it.", "needs": ["rescope"]}
    answers = {"GAP-001": {"category": "missing-export", "name": "fetchAll"}, "GAP-002": {"name": "fetchAll"},
               "GAP-003": {"rescope": False}, "GAP-004": {"rescope": False}}
    # an older report's gap answered a missing export is asked rule R1 next: a person wrote its remediation
    _, summary = _translate(*gaps, judgments=answers)
    assert [(n["gap_id"], n["needs"]) for n in summary["needs_judgment"]] == [("GAP-001", ["rescope"])]
    answers["GAP-001"]["rescope"] = False
    manifest, summary = _translate(*gaps, judgments=answers)
    assert summary["status"] == "written", summary
    routed = {e["gap_id"]: (e["name"], e["category"], e["change_category"]) for e in manifest["entries"]}
    assert routed == {"GAP-001": ("fetchAll", "missing-export", "NEW_EXPORT"),
                      "GAP-002": ("fetchAll", "signature-mismatch", "MODIFIED_EXPORT"),
                      "GAP-003": ("internalThing", "missing-export", "NEW_EXPORT"),
                      "GAP-004": ("fresh", "missing-export", "NEW_EXPORT"),
                      "GAP-005": (None, "broken-reference", "STRUCTURAL_FIX")}


@pytest.mark.parametrize("answers", [
    {"category": None}, {"category": "observation"}, {"category": "missing-export", "name": None},
], ids=["no-row", "a-row-update-skill-does-not-route", "no-export-name"])
def test_translate_leaves_a_gap_the_answers_do_not_route(answers):
    manifest, summary = _translate(_gap("GAP-001", None, export=None), judgments={"GAP-001": answers})
    assert summary["status"] == "written" and manifest["entries"] == []
    assert summary["not_routed"][0]["id"] == "GAP-001"


@pytest.mark.parametrize("remediation", [
    "Rescope `x`: it is internal.", "Remove `x` from the public surface.", "`x` is out of scope.",
    "`x` is out-of-scope", "Upstream marks it #[doc(hidden)].",
    "x is an internal helper (pub(crate)); drop it from the documented surface.",
    "Internal only: exclude x from the brief.", "This export is internal; do not document it.",
    "Recommend removal from the public surface.", "Document `x` with its signature.",
    "Document `x` in SKILL.md: read its definition at `pkg/api.py` and add its signature. It is internal.",
], ids=["rescope", "remove-from-surface", "out-of-scope", "hyphenated", "doc-hidden", "drop-internal",
        "exclude-internal", "internal", "removal", "no-signal", "ledger-text-a-person-extended"])
@pytest.mark.parametrize("category", ["missing-export", "missing-type"])
def test_translate_asks_rescope_of_a_remediation_a_person_wrote(remediation, category):
    """Whether a remediation names removal is rule R1's judgment: translate asks it of any text but the ledger's own."""
    _, summary = _translate(_gap("GAP-001", category, export="x", remediation=remediation))
    [item] = summary["needs_judgment"]
    assert (item["needs"], item["remediation"]) == (["rescope"], remediation)


@pytest.mark.parametrize("where", ["src/api.ts:12", "src/api.ts", None], ids=["file-line", "file", "no-file"])
@pytest.mark.parametrize("kind", ["export", "type"])
def test_translate_never_asks_rescope_of_the_ledgers_own_text(where, kind):
    """gap-ledger.py's text for a missing export or type names no removal, so a ledger's coverage gaps route
    straight to NEW_EXPORT; the one count gap asks only the name its title leaves out."""
    record = _ledger()._missing_export("x", where, "metadata.json", kind)
    gap = _gap("GAP-001", record["category"], export="x", remediation=record["remediation"])
    manifest, summary = _translate(gap)
    assert summary["status"] == "written" and manifest["entries"][0]["change_category"] == "NEW_EXPORT", summary
    [count] = _ledger().from_coverage({"branch": "scalar", "missingCount": 3, "denominator": 10, "documented": 7})
    gap = _gap("GAP-002", count["category"], export=None, remediation=count["remediation"])
    _, summary = _translate(gap)
    assert summary["needs_judgment"][0]["needs"] == ["name"]
    manifest, summary = _translate(gap, judgments={"GAP-002": {"name": "parse"}})
    assert summary["status"] == "written" and manifest["entries"][0]["change_category"] == "NEW_EXPORT", summary


def test_translate_writes_a_rescope_with_its_amendment():
    gap = _gap("GAP-001", "missing-export", export="search", severity="Medium",
               remediation="Remove `search` from the public surface.")
    manifest, summary = _translate(gap, judgments={"GAP-001": {"rescope": True}}, read_only="dry-run")
    [entry] = manifest["entries"]
    assert entry["change_category"] == "DELETED_EXPORT"
    # the exclude path is the file of the export's map entry
    assert entry["rescope"] == {
        "amendment": {"path": "pkg/api.py", "action": "excluded", "category": "scope-expansion",
                      "reason": "Remove `search` from the public surface.", "date": "2026-10-03",
                      "workflow": "skf-update-skill"},
        "exclude": "pkg/api.py"}
    assert summary["warnings"] == ["proposed-amendment: excluded pkg/api.py (scope-expansion); not written: --dry-run"]
    # a write run proposes nothing
    _, summary = _translate(gap, judgments={"GAP-001": {"rescope": True}})
    assert summary["warnings"] == []


def test_translate_asks_a_rescope_path_it_cannot_find():
    gap = _gap("GAP-001", "missing-export", export="fresh", remediation="Rescope `fresh`.")
    _, summary = _translate(gap, judgments={"GAP-001": {"rescope": True}})
    assert summary["needs_judgment"][0]["needs"] == ["source_file"]
    manifest, _ = _translate(gap, judgments={"GAP-001": {"rescope": True, "source_file": ".\\pkg\\new.py"}})
    assert manifest["entries"][0]["rescope"]["exclude"] == "pkg/new.py"
    # with no file to exclude, the export is documented instead
    manifest, summary = _translate(gap, judgments={"GAP-001": {"rescope": True, "source_file": None}})
    assert manifest["entries"][0]["change_category"] == "NEW_EXPORT" and "rescope" not in manifest["entries"][0]
    assert summary["warnings"] == ["test-report: GAP-001: no source file to exclude, so it is documented, not "
                                   "rescoped"]


def test_translate_resolves_a_rule_r3_gap_from_its_cited_file(tmp_path: Path):
    root = tmp_path / "src tree"
    _write_files(root, "pkg/api.py")
    gap = _gap("GAP-001", "provenance-completeness", export="search", severity="Low",
               citation={"file": "pkg/api.py", "line": 5})
    manifest, _ = _translate(gap, source_root=str(root))
    [entry] = manifest["entries"]
    assert (entry["resolved_paths"], entry["rejected_paths"], entry["provenance_completeness"]) == \
        (["pkg/api.py"], [], True)
    # its remediation's own paths win: no root check of the citation then
    manifest, _ = _translate({**gap, "resolved_paths": ["pkg/other.py"]}, source_root=str(root))
    assert manifest["entries"][0]["resolved_paths"] == ["pkg/other.py"]
    # a remediation whose every path was refused keeps those refusals beside the citation check's
    refused = [{"path": "pkg/gone.py", "reason": "not-found"}]
    manifest, _ = _translate({**gap, "source_citation": {"file": "pkg/none.py", "line": 2}, "rejected_paths": refused},
                             source_root=str(root))
    assert (manifest["entries"][0]["resolved_paths"], manifest["entries"][0]["rejected_paths"]) == \
        ([], [*refused, {"path": "pkg/none.py", "reason": "not-found"}])


def test_translate_passes_parse_warnings_on():
    _, summary = _translate(_gap("GAP-001", "structural", export=None), warnings=["GAP-009 has no readable severity"])
    assert summary["warnings"] == ["test-report: GAP-009 has no readable severity"]


def _translate_cli(tmp_path: Path, parsed: dict, *args: str) -> tuple[int, dict, Path]:
    gaps = tmp_path / "gaps.json"
    gaps.write_bytes(json.dumps(parsed).encode("utf-8"))
    prov = tmp_path / "provenance-map.json"
    if not prov.exists():
        prov.write_bytes(json.dumps({"entries": MAP_ENTRIES}).encode("utf-8"))
    out = tmp_path / "change-manifest.json"
    proc = run(SCRIPT, "translate", "--gaps", str(gaps), "--provenance-map", str(prov), "-o", str(out), *args)
    return proc.returncode, json.loads(proc.stdout), out


def test_translate_cli_writes_the_manifest_or_asks(tmp_path: Path):
    parsed = _parsed(_gap("GAP-001", None, export="search"))
    code, out, path = _translate_cli(tmp_path, parsed)
    assert code == 0 and out["status"] == "needs-judgment" and not path.exists(), out
    answers = tmp_path / "gap-judgments.json"
    answers.write_bytes(json.dumps({"GAP-001": {"category": "signature-mismatch", "declaring_line": 4}}).encode())
    code, out, path = _translate_cli(tmp_path, parsed, "--judgments", str(answers), "--date", "2026-10-03")
    assert code == 0 and out["status"] == "written" and out["output"] == str(path), out
    assert json.loads(path.read_bytes())["entries"][0]["change_category"] == "MODIFIED_EXPORT"


@pytest.mark.parametrize("parsed, args, message", [
    ({"status": "error", "code": "REPORT_MISSING", "error": "no test report"}, (), "not the output of a parse"),
    (_parsed(), ("--date", "3 October"), "--date takes YYYY-MM-DD"),
    (_parsed(_gap("GAP-001", None)), ("--judgments", "BAD"), "has the wrong type"),
], ids=["a-failed-parse", "a-bad-date", "an-answer-of-the-wrong-type"])
def test_translate_cli_refuses_unusable_input(tmp_path: Path, parsed, args, message):
    if "BAD" in args:
        bad = tmp_path / "gap-judgments.json"
        bad.write_bytes(json.dumps({"GAP-001": {"rescope": "yes"}}).encode("utf-8"))
        args = ("--judgments", str(bad))
    code, out, path = _translate_cli(tmp_path, parsed, *args)
    assert code == 1 and out["code"] == "INVALID_INPUT" and message in out["error"], out
    assert not path.exists()


def test_translate_cli_reads_the_parse_output_it_follows(tmp_path: Path):
    """The two documented calls chained: parse's stdout in a file, translate's manifest from it."""
    ledger = write_ledger(tmp_path / "findings.json", "coverage-check", LEDGER_RECORDS)
    proc = run(SCRIPT, "parse", "--ledger", str(ledger))
    assert proc.returncode == 0
    code, out, path = _translate_cli(tmp_path, json.loads(proc.stdout))
    # the ledger's missing export carries a remediation a person wrote: rule R1 asks about it
    assert code == 0 and [n["needs"] for n in out["needs_judgment"]] == [["rescope"]], out
    answers = tmp_path / "gap-judgments.json"
    answers.write_bytes(json.dumps({out["needs_judgment"][0]["gap_id"]: {"rescope": False}}).encode("utf-8"))
    code, out, path = _translate_cli(tmp_path, json.loads(proc.stdout), "--judgments", str(answers))
    assert code == 0 and out["gap_count"] == 3, out
    assert [e["change_category"] for e in json.loads(path.read_bytes())["entries"]] == [
        "MODIFIED_EXPORT", "STRUCTURAL_FIX", "NEW_EXPORT"]
