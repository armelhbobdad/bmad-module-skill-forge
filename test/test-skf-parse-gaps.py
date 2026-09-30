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
    assert mod.map_extensions(prov) == ["vue"]  # file_entries (docs, scripts) add no extension


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



def test_usage_error_exits_2():
    proc = run(SCRIPT, "parse", "--no-such-flag")
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert "--no-such-flag" in proc.stderr
