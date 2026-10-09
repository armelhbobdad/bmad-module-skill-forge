#!/usr/bin/env python3
"""Tests for src/skf-test-skill/scripts/gap-ledger.py.

The JSON ledger test-skill's stages append their gaps to, which the hard gate
counts and the Gap Report is rendered from:
  - append: validation (all or nothing), id assignment, derived group and
    stage, dedupe on a re-run (two exports that share a title and a source
    stay two gaps), a stage recorded with no records, the three input
    shapes, --input, a byte order mark on stdin, a corrupt ledger left
    untouched
  - overlapping appends: parallel appends keep every record they report,
    a held lock makes an append wait and then fail with LEDGER_LOCKED, a
    failed write leaves no temp file
  - render: severity order, counts, the Remediation Summary, the Gap Entry
    lines, --heading, the clean pass, errors on stderr only, the group
    taken from the category
  - summary and categories
  - append --from: each adapter's records (coverage, guards, numerator,
    metadata-coherence, provenance-line, coherence and structure, the
    last over the scanner's real results), their titles, Sources and
    `export`, the refusals (an option or an --input count a kind does not
    read, a result of another shape), a rerun recorded once, and the
    coverage-check §5b and coherence-check §6 calls run as written
  - documented extras (#678): a stale name with a Python or TS/JS
    `defined_at`, given a surface built from an extraction that does not
    list it outside scope, is an Info `observation` asking no change, its
    issue naming the line that documents it and its remediation saying
    whether its signature was scored; no surface, a surface without an
    extraction or `excluded`, a rescope, a dotted name or a `defined_at`
    that is no Python or TS/JS `file:line` keeps it Medium, a fabricated
    name stays Critical, a malformed `excluded` is invalid input, the
    `defined_at` extensions are pinned to the verifier's, and the
    coverage-check §5b call records one; a homonym (no `defined_at`,
    several `declared_in` files) is one when the skill's `[AST:]`/`[SRC:]`
    citations on a line naming it cite exactly one of those files, and
    stays Medium when they cite two or none, without --skill-dir, or with
    a `declared_in` that is not a list of several `file:line` items
"""

from __future__ import annotations

import doctest
import importlib.util
import json
import re
import shlex
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "skf-test-skill"
    / "scripts"
    / "gap-ledger.py"
)

spec = importlib.util.spec_from_file_location("gap_ledger", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

RUN_ID = "20260930T101010Z-4242-ab12"

# A process that appends each --input file in turn through main(), once the
# test releases it, and prints the ids it was told it appended.
APPEND_WORKER = textwrap.dedent(
    """
    import contextlib, importlib.util, io, json, sys
    spec = importlib.util.spec_from_file_location("gap_ledger", sys.argv[1])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ledger, inputs = sys.argv[2], sys.argv[3:]
    sys.stdin.readline()
    sys.stdin = io.StringIO()
    appended = []
    for path in inputs:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = mod.main(["append", "--ledger", ledger, "--stage", "coverage-check", "--input", path])
        assert code == 0, out.getvalue()
        appended += json.loads(out.getvalue())["appended"]
    print(json.dumps(appended))
    """
)

# A process that holds the append lock until it reads a line.
LOCK_HOLDER = textwrap.dedent(
    """
    import importlib.util, sys
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("gap_ledger", sys.argv[1])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with mod.ledger_lock(Path(sys.argv[2])):
        print("locked", flush=True)
        sys.stdin.readline()
    """
)


def run(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def record(**overrides) -> dict:
    base = {
        "severity": "High",
        "category": "broken-reference",
        "title": "Reference to missing file",
        "source": "SKILL.md:12",
        "remediation": "Point the link at `references/api.md`.",
    }
    base.update(overrides)
    return base


def append(ledger: Path, stage: str, records) -> subprocess.CompletedProcess:
    return run("append", "--ledger", str(ledger), "--stage", stage, stdin=json.dumps(records))


@pytest.fixture
def ledger(tmp_path: Path) -> Path:
    return tmp_path / "1.0.0" / f"test-findings-{RUN_ID}.json"


def test_embedded_doctests_pass():
    results = doctest.testmod(mod, verbose=False)
    assert results.failed == 0, f"{results.failed} doctest(s) failed"


# --------------------------------------------------------------------------
# append
# --------------------------------------------------------------------------


class TestAppend:
    def test_creates_the_ledger_with_ids_group_and_stage(self, ledger: Path):
        proc = append(
            ledger,
            "coverage-check",
            [
                record(severity="critical", category="signature-mismatch", title="formatDate", source="src/a.ts:4"),
                record(severity="Medium", category="missing-export", title="parseDate", export="parseDate"),
            ],
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        out = json.loads(proc.stdout)
        assert out["status"] == "ok"
        assert out["appended"] == ["GAP-001", "GAP-002"]
        assert out["record_count"] == 2
        data = json.loads(ledger.read_text(encoding="utf-8"))
        assert data["schema_version"] == 1
        assert data["run_id"] == RUN_ID
        assert data["stages"] == ["coverage-check"]
        first, second = data["records"]
        assert first == {
            "id": "GAP-001",
            "severity": "Critical",
            "category": "signature-mismatch",
            "group": "Coverage",
            "title": "formatDate",
            "source": "src/a.ts:4",
            "remediation": "Point the link at `references/api.md`.",
            "stage": "coverage-check",
        }
        assert second["export"] == "parseDate"
        assert second["severity"] == "Medium"

    def test_ids_continue_across_stages(self, ledger: Path):
        append(ledger, "coverage-check", [record(title="one")])
        proc = append(ledger, "coherence-check", [record(title="two"), record(title="three")])
        assert json.loads(proc.stdout)["appended"] == ["GAP-002", "GAP-003"]
        data = json.loads(ledger.read_text(encoding="utf-8"))
        assert data["stages"] == ["coverage-check", "coherence-check"]
        assert [r["stage"] for r in data["records"]] == ["coverage-check", "coherence-check", "coherence-check"]

    def test_rerun_of_a_stage_adds_no_duplicate(self, ledger: Path):
        records = [record(title="one"), record(title="two")]
        append(ledger, "coherence-check", records)
        proc = append(ledger, "coherence-check", records + [record(title="three")])
        out = json.loads(proc.stdout)
        assert out["appended"] == ["GAP-003"]
        assert out["duplicates"] == ["GAP-001", "GAP-002"]
        data = json.loads(ledger.read_text(encoding="utf-8"))
        assert len(data["records"]) == 3
        assert data["stages"] == ["coherence-check"]

    def test_duplicates_within_one_batch_are_kept_once(self, ledger: Path):
        proc = append(ledger, "coverage-check", [record(), record(remediation="Another wording.")])
        out = json.loads(proc.stdout)
        assert out["appended"] == ["GAP-001"]
        assert out["duplicates"] == ["GAP-001"]

    def test_exports_that_share_a_title_and_source_stay_two_gaps(self, ledger: Path):
        gaps = [
            record(severity="Medium", category="missing-export", title="Undocumented export", source="src/index.ts", export=name)
            for name in ("parseDate", "formatDate")
        ]
        out = json.loads(append(ledger, "coverage-check", gaps).stdout)
        assert out["appended"] == ["GAP-001", "GAP-002"]
        assert out["duplicates"] == []
        rerun = json.loads(append(ledger, "coverage-check", gaps).stdout)
        assert rerun["appended"] == []
        assert rerun["duplicates"] == ["GAP-001", "GAP-002"]
        rendered = run("render", "--ledger", str(ledger)).stdout
        assert "**Export:** parseDate" in rendered
        assert "**Export:** formatDate" in rendered

    def test_empty_list_records_the_stage(self, ledger: Path):
        proc = append(ledger, "coverage-check", [])
        assert proc.returncode == 0
        data = json.loads(ledger.read_text(encoding="utf-8"))
        assert data["stages"] == ["coverage-check"]
        assert data["records"] == []

    def test_single_object_and_records_wrapper(self, ledger: Path):
        assert append(ledger, "coverage-check", record(title="one")).returncode == 0
        assert append(ledger, "coherence-check", {"records": [record(title="two")]}).returncode == 0
        data = json.loads(ledger.read_text(encoding="utf-8"))
        assert [r["title"] for r in data["records"]] == ["one", "two"]

    def test_input_file(self, ledger: Path, tmp_path: Path):
        source = tmp_path / "records.json"
        source.write_text(json.dumps([record()]), encoding="utf-8")
        proc = run("append", "--ledger", str(ledger), "--stage", "coverage-check", "--input", str(source))
        assert proc.returncode == 0, proc.stdout
        assert json.loads(proc.stdout)["appended"] == ["GAP-001"]

    def test_byte_order_mark_on_stdin(self, ledger: Path):
        proc = run("append", "--ledger", str(ledger), "--stage", "coverage-check", stdin="\ufeff" + json.dumps([record()]))
        assert proc.returncode == 0, proc.stdout
        assert json.loads(proc.stdout)["appended"] == ["GAP-001"]

    def test_whitespace_is_normalized(self, ledger: Path):
        append(ledger, "coverage-check", [record(title="  two\n words ", source=" SKILL.md:3 ", issue="  ")])
        rec = json.loads(ledger.read_text(encoding="utf-8"))["records"][0]
        assert rec["title"] == "two words"
        assert rec["source"] == "SKILL.md:3"
        assert "issue" not in rec

    def test_non_ascii_round_trip(self, ledger: Path):
        append(ledger, "coverage-check", [record(title="Documenter l'export \u00e9t\u00e9")])
        rec = json.loads(ledger.read_text(encoding="utf-8"))["records"][0]
        assert rec["title"] == "Documenter l'export \u00e9t\u00e9"

    @pytest.mark.parametrize(
        ("bad", "fragment"),
        [
            (record(severity="Severe"), "unknown severity"),
            (record(category="missing-docs"), "unknown category"),
            ({k: v for k, v in record().items() if k != "remediation"}, "missing required field 'remediation'"),
            (record(id="GAP-007"), "assigned by the ledger"),
            (record(group="Coverage"), "assigned by the ledger"),
            (record(remedation="typo"), "unknown field"),
            (record(title=3), "'title' must be a string"),
            (record(title="   "), "'title' must not be empty"),
            (record(export=["a"]), "'export' must be a string"),
            ("not an object", "must be a JSON object"),
        ],
    )
    def test_invalid_record_writes_nothing(self, ledger: Path, bad, fragment: str):
        proc = append(ledger, "coverage-check", [record(title="good"), bad])
        assert proc.returncode == 2
        out = json.loads(proc.stdout)
        assert out["code"] == "INVALID_RECORD"
        assert out["errors"][0]["index"] == 1
        assert fragment in out["errors"][0]["error"]
        assert not ledger.exists()

    def test_invalid_record_leaves_an_existing_ledger_unchanged(self, ledger: Path):
        append(ledger, "coverage-check", [record()])
        before = ledger.read_bytes()
        proc = append(ledger, "coherence-check", [record(severity="nope")])
        assert proc.returncode == 2
        assert ledger.read_bytes() == before

    def test_malformed_json_input(self, ledger: Path):
        proc = run("append", "--ledger", str(ledger), "--stage", "coverage-check", stdin="[{")
        assert proc.returncode == 2
        assert json.loads(proc.stdout)["code"] == "INVALID_INPUT"

    def test_stage_must_be_a_slug(self, ledger: Path):
        proc = append(ledger, "Coverage Check", [])
        assert proc.returncode == 2
        assert json.loads(proc.stdout)["code"] == "INVALID_INPUT"

    def test_corrupt_ledger_is_not_overwritten(self, ledger: Path):
        ledger.parent.mkdir(parents=True)
        ledger.write_text("{not json", encoding="utf-8")
        proc = append(ledger, "coverage-check", [record()])
        assert proc.returncode == 1
        assert json.loads(proc.stdout)["code"] == "LEDGER_INVALID"
        assert ledger.read_text(encoding="utf-8") == "{not json"

    def test_no_temp_or_lock_file_is_left_behind(self, ledger: Path):
        append(ledger, "coverage-check", [record()])
        append(ledger, "coherence-check", [record(title="two")])
        assert sorted(p.name for p in ledger.parent.iterdir()) == [ledger.name]


# --------------------------------------------------------------------------
# Overlapping appends
# --------------------------------------------------------------------------


class TestOverlappingAppends:
    def test_parallel_appends_keep_every_record_they_report(self, ledger: Path, tmp_path: Path):
        workers, per_worker = 8, 10
        procs = []
        for w in range(workers):
            inputs = []
            for k in range(per_worker):
                source = tmp_path / f"records-{w}-{k}.json"
                source.write_text(json.dumps([record(title=f"gap {w}-{k}")]), encoding="utf-8")
                inputs.append(str(source))
            procs.append(
                subprocess.Popen(
                    [sys.executable, "-c", APPEND_WORKER, str(SCRIPT), str(ledger), *inputs],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                )
            )
        for proc in procs:  # every worker is started: release them together
            proc.stdin.write("go\n")
            proc.stdin.flush()
        reported: list[str] = []
        for proc in procs:
            out, err = proc.communicate(timeout=120)
            assert proc.returncode == 0, err
            reported += json.loads(out)
        data = json.loads(ledger.read_text(encoding="utf-8"))
        assert len(reported) == len(set(reported)) == workers * per_worker
        assert sorted(r["id"] for r in data["records"]) == sorted(reported)
        assert len({r["title"] for r in data["records"]}) == workers * per_worker
        assert sorted(p.name for p in ledger.parent.iterdir()) == [ledger.name]

    def test_a_rename_windows_refuses_for_a_moment_is_retried(self, ledger: Path, monkeypatch: pytest.MonkeyPatch):
        # Windows refuses os.replace while another process (a virus scanner,
        # the indexer) holds the just-written ledger open; the append retries.
        real_replace = mod.os.replace
        calls = []

        def flaky_replace(src, dst):
            calls.append(dst)
            if len(calls) < 3:
                raise PermissionError(13, "Access is denied", str(dst))
            return real_replace(src, dst)

        monkeypatch.setattr(mod, "_IS_WINDOWS", True)
        monkeypatch.setattr(mod.os, "replace", flaky_replace)
        data = mod.new_ledger(ledger)
        mod.append_records(data, "coverage-check", [record(title="retried")])
        mod.save_ledger(ledger, data)
        assert len(calls) == 3
        assert [r["title"] for r in json.loads(ledger.read_text(encoding="utf-8"))["records"]] == ["retried"]
        assert sorted(p.name for p in ledger.parent.iterdir()) == [ledger.name]

    def test_a_rename_refused_past_the_wait_fails_and_leaves_no_temp_file(self, ledger: Path, monkeypatch: pytest.MonkeyPatch):
        def refused(src, dst):
            raise PermissionError(13, "Access is denied", str(dst))

        monkeypatch.setattr(mod, "_IS_WINDOWS", True)
        monkeypatch.setattr(mod, "_REPLACE_WAIT_SECONDS", 0.05)
        monkeypatch.setattr(mod.os, "replace", refused)
        data = mod.new_ledger(ledger)
        with pytest.raises(PermissionError):
            mod.save_ledger(ledger, data)
        assert not ledger.exists() and list(ledger.parent.glob("*.skf-tmp")) == []

    def test_a_held_lock_makes_an_append_wait_then_fail(
        self, ledger: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        append(ledger, "coverage-check", [record(title="before")])
        before = ledger.read_bytes()
        source = tmp_path / "records.json"
        source.write_text(json.dumps([record(title="after")]), encoding="utf-8")
        args = ["append", "--ledger", str(ledger), "--stage", "coherence-check", "--input", str(source)]
        holder = subprocess.Popen(
            [sys.executable, "-c", LOCK_HOLDER, str(SCRIPT), str(ledger)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        try:
            assert holder.stdout.readline().strip() == "locked"
            with pytest.raises(mod.LedgerError) as exc:
                with mod.ledger_lock(ledger, timeout=0.2):
                    pass
            assert exc.value.code == "LEDGER_LOCKED"
            monkeypatch.setattr(mod, "LOCK_TIMEOUT_SECONDS", 0.2)
            assert mod.main(args) == 1
            assert json.loads(capsys.readouterr().out)["code"] == "LEDGER_LOCKED"
            assert ledger.read_bytes() == before
        finally:
            holder.communicate("release\n", timeout=30)
        # The holder is gone and so is its lock.
        assert mod.main(args) == 0
        assert json.loads(capsys.readouterr().out)["appended"] == ["GAP-002"]

    def test_a_failed_write_leaves_the_ledger_and_no_temp_file(self, ledger: Path, monkeypatch: pytest.MonkeyPatch):
        append(ledger, "coverage-check", [record()])
        before = ledger.read_bytes()

        def refuse(src, dst):
            raise OSError("disk full")

        monkeypatch.setattr(mod.os, "replace", refuse)
        with pytest.raises(OSError):
            mod.save_ledger(ledger, mod.load_ledger(ledger))
        assert ledger.read_bytes() == before
        assert sorted(p.name for p in ledger.parent.iterdir()) == [ledger.name]


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------


def _mixed_ledger(ledger: Path) -> None:
    append(
        ledger,
        "coverage-check",
        [
            record(severity="Medium", category="missing-export", title="parseDate undocumented"),
            record(severity="Critical", category="signature-mismatch", title="formatDate signature", export="formatDate"),
        ],
    )
    append(
        ledger,
        "coherence-check",
        [
            record(severity="High", category="inaccurate-reference", title="Type not exported", issue="The type is internal."),
            record(severity="Info", category="discovery", title="Discovery skipped"),
        ],
    )


class TestRender:
    def test_orders_by_severity_then_id(self, ledger: Path):
        _mixed_ledger(ledger)
        proc = run("render", "--ledger", str(ledger))
        assert proc.returncode == 0, proc.stderr
        headings = [line for line in proc.stdout.splitlines() if line.startswith("### GAP-")]
        assert headings == [
            "### GAP-002: formatDate signature",
            "### GAP-003: Type not exported",
            "### GAP-001: parseDate undocumented",
            "### GAP-004: Discovery skipped",
        ]

    def test_totals_and_summary_table(self, ledger: Path):
        _mixed_ledger(ledger)
        text = run("render", "--ledger", str(ledger)).stdout
        assert "**Total Gaps:** 4" in text
        assert "**Blocking (Critical + High):** 2" in text
        assert "**Non-blocking (Medium + Low + Info):** 2" in text
        assert "### Remediation Summary" in text
        assert "| Low | 0 | None |" in text
        assert "| Critical | 1 | Read the source code" in text
        assert "| **Total** | **4** | |" in text
        assert not text.startswith("## Gap Report")

    def test_gap_entry_lines(self, ledger: Path):
        _mixed_ledger(ledger)
        text = run("render", "--ledger", str(ledger)).stdout
        entry = text.split("### GAP-002: formatDate signature", 1)[1].split("### GAP-003", 1)[0]
        assert "**Severity:** Critical" in entry
        assert "**Category:** Coverage (signature-mismatch)" in entry
        assert "**Source:** SKILL.md:12" in entry
        assert "**Export:** formatDate" in entry
        assert "**Remediation:** Point the link at `references/api.md`." in entry
        assert "**Issue:**" not in entry
        high = text.split("### GAP-003: Type not exported", 1)[1]
        assert "**Issue:** The type is internal." in high

    def test_heading_flag(self, ledger: Path):
        _mixed_ledger(ledger)
        assert run("render", "--ledger", str(ledger), "--heading").stdout.startswith("## Gap Report\n\n")

    def test_clean_pass(self, ledger: Path):
        append(ledger, "coverage-check", [])
        text = run("render", "--ledger", str(ledger)).stdout
        assert "**Total Gaps:** 0" in text
        assert "No gaps found." in text
        assert "### GAP-" not in text

    def test_missing_ledger_reports_on_stderr_only(self, ledger: Path):
        proc = run("render", "--ledger", str(ledger))
        assert proc.returncode == 1
        assert proc.stdout == ""
        assert json.loads(proc.stderr)["code"] == "LEDGER_MISSING"

    def test_group_comes_from_the_category(self, ledger: Path):
        # A valid ledger written without `group` renders like one with it.
        ledger.parent.mkdir(parents=True)
        entry = {"id": "GAP-001", "severity": "High", "category": "broken-reference", "title": "t", "source": "SKILL.md:3", "remediation": "Fix."}
        ledger.write_text(json.dumps({"schema_version": 1, "run_id": None, "stages": ["coherence-check"], "records": [entry]}), encoding="utf-8")
        proc = run("render", "--ledger", str(ledger))
        assert proc.returncode == 0, proc.stderr
        assert "**Category:** Coherence (broken-reference)" in proc.stdout


# --------------------------------------------------------------------------
# summary, categories, ledger validation
# --------------------------------------------------------------------------


def test_summary_counts(ledger: Path):
    _mixed_ledger(ledger)
    proc = run("summary", "--ledger", str(ledger))
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["run_id"] == RUN_ID
    assert out["stages"] == ["coverage-check", "coherence-check"]
    assert out["total"] == 4
    assert out["counts"] == {"Critical": 1, "High": 1, "Medium": 1, "Low": 0, "Info": 1}
    assert out["blocking"] == 2
    assert out["non_blocking"] == 2
    assert out["by_category"] == {
        "discovery": 1,
        "inaccurate-reference": 1,
        "missing-export": 1,
        "signature-mismatch": 1,
    }


def test_summary_of_a_missing_ledger(ledger: Path):
    proc = run("summary", "--ledger", str(ledger))
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["code"] == "LEDGER_MISSING"


def test_categories_cover_the_gap_severity_rows():
    out = json.loads(run("categories").stdout)
    assert out["severities"] == ["Critical", "High", "Medium", "Low", "Info"]
    slugs = {c["category"]: c["group"] for c in out["categories"]}
    for slug in (
        "missing-export",
        "signature-mismatch",
        "fabricated-signature",
        "broken-reference",
        "inaccurate-reference",
        "integration-pattern",
        "split-body-mismatch",
        "provenance-line",
        "metadata-drift",
        "denominator-inflation",
        "brief-scope-stale",  # coverage-check 4, Medium (#677)
        "numerator-inflation",  # coverage-check 4b, High
        "reference-escape",  # coherence-check contextual 5, High
        "discovery",
        "structural",
    ):
        assert slug in slugs
    assert set(slugs.values()) <= {"Coverage", "Coherence", "Structural", "Discovery", "External"}
    assert all(c["description"] for c in out["categories"])


@pytest.mark.parametrize(
    "data",
    [
        [],
        {"schema_version": 2, "stages": [], "records": []},
        {"schema_version": 1, "stages": "x", "records": []},
        {"schema_version": 1, "stages": [], "records": [{"id": "G1"}]},
        {
            "schema_version": 1,
            "stages": [],
            "records": [
                {"id": "GAP-001", "severity": "High", "category": "structural", "title": "a", "source": "b", "remediation": "c"},
                {"id": "GAP-001", "severity": "High", "category": "structural", "title": "d", "source": "e", "remediation": "f"},
            ],
        },
        {
            "schema_version": 1,
            "stages": [],
            "records": [{"id": "GAP-001", "severity": "Blocker", "category": "structural", "title": "a", "source": "b", "remediation": "c"}],
        },
        {
            "schema_version": 1,
            "stages": [],
            "records": [
                {"id": "GAP-001", "severity": "High", "category": "structural", "title": "a", "source": "b", "remediation": "c", "export": ["x"]}
            ],
        },
    ],
)
def test_malformed_ledgers_are_refused(ledger: Path, data):
    ledger.parent.mkdir(parents=True)
    ledger.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(mod.LedgerError) as exc:
        mod.load_ledger(ledger)
    assert exc.value.code == "LEDGER_INVALID"


# --------------------------------------------------------------------------
# append --from: the records a script's result file gives
# --------------------------------------------------------------------------

REPO = Path(__file__).resolve().parent.parent
REFS = REPO / "src" / "skf-test-skill" / "references"
COVERAGE_STEP = REFS / "coverage-check.md"
COHERENCE_STEP = REFS / "coherence-check.md"
SCANNER = REPO / "src" / "shared" / "scripts" / "skf-scan-skill-md-structure.py"
# A bracketed `[--flag ...]` synopsis group of a prose call, repeatable or not.
OPTIONAL_GROUP = re.compile(r" \[(--[a-z-]+[^\]]*)\](?:\.\.\.)?")


def write_json(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(data).encode("utf-8"))
    return path


def from_file(ledger: Path, stage: str, kind: str, *inputs: Path, **options) -> subprocess.CompletedProcess:
    args = ["append", "--ledger", str(ledger), "--stage", stage, "--from", kind]
    for path in inputs:
        args += ["--input", str(path)]
    for key, value in options.items():
        for item in value if isinstance(value, list) else [value]:
            args += ["--" + key.replace("_", "-"), str(item)]
    return run(*args)


def ledger_records(ledger: Path) -> list[dict]:
    return json.loads(ledger.read_bytes())["records"]


def brief(records: list[dict]) -> list[tuple]:
    return [(r["severity"], r["category"], r["title"], r["source"], r.get("export")) for r in records]


class TestCoverageAdapter:
    SURFACE = {"inputs": {"metadata": "pkg/metadata.json"}, "guards": None, "exports": [
        {"name": "Options", "kind": "interface", "file": "src/types.ts", "line": 3},
        {"name": "fetchData", "kind": "function", "file": "src/index.ts", "line": None},
        {"name": "fetchData", "kind": "function", "file": "src/fetch.ts", "line": 12},
        {"name": "fromMeta", "kind": None, "file": None, "line": None},
    ]}

    def test_missing_names_take_their_surface_file_and_line(self):
        records = mod.from_coverage(
            {"branch": "enumerated", "missing": ["fetchData", "Options", "fromMeta"], "stale": []},
            surface=self.SURFACE, signatures={"missingTypes": ["Options"]}, metadata="pkg/metadata.json")
        assert brief(records) == [
            ("Medium", "missing-export", "Missing export: fetchData", "src/fetch.ts:12", "fetchData"),
            ("Medium", "missing-type", "Missing type: Options", "src/types.ts:3", "Options"),
            ("Medium", "missing-export", "Missing export: fromMeta", "pkg/metadata.json", "fromMeta"),
        ]
        # update-skill re-extracts from the file the remediation names
        assert "`src/fetch.ts:12`" in records[0]["remediation"]
        assert "`pkg/metadata.json` lists it" in records[2]["remediation"]

    def test_stale_names_fabricated_or_stale_documentation(self, tmp_path: Path):
        skill = tmp_path / "skill"
        (skill / "references").mkdir(parents=True)
        (skill / "SKILL.md").write_bytes(b"# demo\n\nUse `getAll()`.\n")
        (skill / "references" / "api.md").write_bytes(b"# API\n\n## get\n\n`get(key)` reads.\n")
        stale = [{"name": "ghost", "fabricated": True, "source": "src/a.ts:3", "reason": "not-defined"},
                 {"name": "get", "fabricated": False, "source": "src/b.ts:1", "reason": "defined"}]
        records = mod.from_coverage({"branch": "enumerated", "missing": [], "stale": ["ghost", "get", "nowhere"]},
                                    stale=stale, skill_dir=str(skill))
        assert brief(records) == [
            ("Critical", "fabricated-signature", "Fabricated signature: ghost", "src/a.ts:3", "ghost"),
            # `getAll` is not `get`: the first line that writes the name is in references/
            ("Medium", "stale-documentation", "Stale documentation: get", "references/api.md:3", "get"),
            ("Medium", "stale-documentation", "Stale documentation: nowhere", "SKILL.md", "nowhere"),
        ]

    def test_without_classify_stale_every_stale_name_is_medium(self):
        records = mod.from_coverage({"branch": "enumerated", "missing": [], "stale": ["ghost"]})
        assert brief(records) == [("Medium", "stale-documentation", "Stale documentation: ghost", "SKILL.md",
                                   "ghost")]

    # #678: a stale name classify-stale finds declared is a documented extra, given a surface built from an
    # extraction (the only input that fills `excluded.outsideScope`).
    EXCLUDED = {"outsideScope": [{"name": "Rescoped", "file": "pkg/old/r.py"}], "nestedEntries": []}
    EXCLUDED_SURFACE = SURFACE | {"extraction": {"status": "ok"}, "excluded": EXCLUDED}

    @pytest.mark.parametrize("defined_at", ["pkg/tasks/task.py:4", "src/tasks/task.ts:12", "lib/task.MJS:1"])
    def test_a_declared_stale_name_is_a_documented_extra(self, tmp_path: Path, defined_at: str):
        skill = tmp_path / "skill"
        (skill / "references").mkdir(parents=True)
        (skill / "SKILL.md").write_bytes(b"# demo\n\nSee references.\n")
        (skill / "references" / "api.md").write_bytes(b"# API\n\n`Task(fn)` wraps a step.\n")
        stale = [{"name": "Task", "fabricated": False, "source": None, "defined_at": defined_at,
                  "reason": "no-entry"}]
        [record] = mod.from_coverage({"branch": "enumerated", "missing": [], "stale": ["Task"]},
                                     surface=self.EXCLUDED_SURFACE, stale=stale, skill_dir=str(skill))
        assert brief([record]) == [("Info", "observation", "Documented extra: Task", defined_at, "Task")]
        assert record["remediation"] == (
            f"No change: `Task` is a documented extra, a name the source still declares at `{defined_at}` outside "
            "the enumerated surface, and its documentation stays. Its documented signature was not checked "
            "against that declaration.")
        # the issue names the line that documents it, here in references/ alone
        assert record["issue"] == ("`references/api.md:3` documents `Task`, which the enumerated source API "
                                   "surface lacks and the source still declares")
        # without the skill package, the issue names no file
        [record] = mod.from_coverage({"branch": "enumerated", "missing": [], "stale": ["Task"]},
                                     surface=self.EXCLUDED_SURFACE, stale=stale)
        assert record["issue"].startswith("the skill documents `Task`,")
        assert mod.CATEGORIES["observation"][1] == "a style suggestion, a documented extra or another " \
                                                   "non-blocking observation"

    @pytest.mark.parametrize("signatures, said", [
        ({"missingTypes": [], "comparedNames": ["fetchData"]},
         "Signature scoring compares its documented signature with the surface's record of it."),
        # on the surface's records, but the skill documents no signature for it: nothing was compared
        ({"missingTypes": [], "comparedNames": ["Options"]},
         "Its documented signature was not checked against that declaration."),
        ({"missingTypes": []}, "Its documented signature was not checked against that declaration."),
        (None, "Its documented signature was not checked against that declaration."),
    ], ids=["compared", "not-compared", "an-older-result", "no-signatures"])
    def test_the_remediation_says_whether_signature_scoring_compared_it(self, signatures, said):
        # a nested sub-package's name: out of `all`, on the records
        stale = [{"name": "fetchData", "fabricated": False, "source": None, "defined_at": "src/fetch.ts:12"}]
        [record] = mod.from_coverage({"branch": "enumerated", "missing": [], "stale": ["fetchData"]},
                                     surface=self.EXCLUDED_SURFACE, signatures=signatures, stale=stale)
        assert record["category"] == "observation"
        assert record["remediation"].endswith(said)

    @pytest.mark.parametrize("name, defined_at, surface", [
        ("Task", "pkg/tasks/task.py:4", None),
        ("Task", "pkg/tasks/task.py:4", SURFACE),
        ("Task", "pkg/tasks/task.py:4", SURFACE | {"excluded": EXCLUDED}),
        ("Task", "pkg/tasks/task.py:4", SURFACE | {"extraction": None, "excluded": EXCLUDED}),
        ("Task", "pkg/tasks/task.py:4", SURFACE | {"extraction": [], "excluded": EXCLUDED}),
        ("Task", "pkg/tasks/task.py:4", SURFACE | {"extraction": {"status": "ok"}}),
        ("Task", "pkg/tasks/task.py:4", EXCLUDED_SURFACE | {"extraction": {"status": "no-ast-grep"}}),
        ("Task", "pkg/tasks/task.py:4", EXCLUDED_SURFACE | {"extraction": {"status": "ok", "truncated": True}}),
        ("Task", "pkg/tasks/task.py:4", EXCLUDED_SURFACE | {"extraction": {
            "status": "ok", "fallback": {"needed": True, "reason": "no file in scope"}}}),
        ("Rescoped", "pkg/old/r.py:2", EXCLUDED_SURFACE),
        ("App.update", "pkg/app.py:3", EXCLUDED_SURFACE),
        ("Task", None, EXCLUDED_SURFACE),
        ("Task", "", EXCLUDED_SURFACE),
        ("Task", "pkg/tasks/task.py", EXCLUDED_SURFACE),
        ("Task", "pkg/tasks/task.py:0", EXCLUDED_SURFACE),
        ("Task", "src/lib.rs:3", EXCLUDED_SURFACE),
        ("Task", "pkg/task.pyc:3", EXCLUDED_SURFACE),
        ("Task", ["pkg/tasks/task.py:4"], EXCLUDED_SURFACE),
    ], ids=["no-surface", "surface-without-excluded", "no-extraction", "null-extraction", "extraction-not-an-object",
            "extraction-without-excluded", "no-ast-grep", "truncated", "fallback", "outside-scope", "dotted", "no-defined-at", "empty", "no-line",
            "line-zero", "other-language", "compiled", "not-a-string"])
    def test_anything_short_of_that_stays_medium(self, name, defined_at, surface):
        stale = [{"name": name, "fabricated": False, "source": None, "defined_at": defined_at}]
        records = mod.from_coverage({"branch": "enumerated", "missing": [], "stale": [name]},
                                    surface=surface, stale=stale)
        assert brief(records) == [("Medium", "stale-documentation", f"Stale documentation: {name}", "SKILL.md",
                                   name)]

    def test_a_fabricated_name_stays_critical_whatever_its_defined_at(self):
        stale = [{"name": "ghost", "fabricated": True, "source": "src/a.py:3", "defined_at": "src/b.py:1"}]
        records = mod.from_coverage({"branch": "enumerated", "missing": [], "stale": ["ghost"]},
                                    surface=self.EXCLUDED_SURFACE, stale=stale)
        assert brief(records) == [("Critical", "fabricated-signature", "Fabricated signature: ghost", "src/a.py:3",
                                   "ghost")]

    # #678: a homonym classify-stale cannot settle is decided by the skill's own citations.
    HOMONYM = {"name": "Task", "fabricated": False, "source": None, "defined_at": None,
               "declared_in": ["pkg/models/Task.py:9", "pkg/tasks/task.py:24"], "reason": "no-entry"}

    def _homonym(self, tmp_path: Path, skill_md: str, refs: str | None = None, item: dict | None = None,
                 name: str = "Task", skill: bool = True) -> dict:
        skill_dir = tmp_path / "skill"
        (skill_dir / "references").mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_bytes(skill_md.encode("utf-8"))
        if refs is not None:
            (skill_dir / "references" / "api.md").write_bytes(refs.encode("utf-8"))
        [record] = mod.from_coverage({"branch": "enumerated", "missing": [], "stale": [name]},
                                     surface=self.EXCLUDED_SURFACE, stale=[(item or self.HOMONYM) | {"name": name}],
                                     skill_dir=str(skill_dir) if skill else None)
        return record

    @pytest.mark.parametrize("skill_md, refs", [
        ("# demo\n\n`Task(fn)` wraps a step. `[AST:pkg/tasks/task.py:L24]`\n", None),
        ("# demo\n\nSee references.\n", "# API\n\n- `Task(fn)` wraps a step `[SRC:./pkg/tasks/task.py:L24-30]`\n"),
        ("# demo\n\n`Task(fn)` `[AST:pkg/tasks/task.py:L24]` and `[AST:pkg/tasks/__init__.py:L1]`\n", None),
        ("# demo\n\n`Task` `[AST:pkg/tasks/task.py:L24]`\nPlain text.\n`Other` `[AST:pkg/models/Task.py:L9]`\n",
         None),
        ("# demo\n\n### `Task`\n\n`[AST:pkg/tasks/task.py:L24]`\n", None),
        ("# demo\n\n`Task` `[AST:pkg/tasks/task.py:L24]` `[AST:pkg/models/Task.py]`\n", None),
    ], ids=["skill-md", "references-src-range", "a-cited-file-that-declares-nothing", "the-other-on-a-line-without-it",
            "a-heading-then-its-citation", "a-citation-with-no-line-is-ignored"])
    def test_a_homonym_the_skill_cites_once_is_a_documented_extra(self, tmp_path: Path, skill_md: str,
                                                                 refs: str | None):
        record = self._homonym(tmp_path, skill_md, refs)
        assert brief([record]) == [("Info", "observation", "Documented extra: Task", "pkg/tasks/task.py:24", "Task")]
        assert record["issue"].endswith("the source still declares; of the 2 files that declare it, the skill "
                                        "cites only `pkg/tasks/task.py`")

    def test_a_nested_references_file_counts(self, tmp_path: Path):
        (tmp_path / "skill" / "references" / "api").mkdir(parents=True)
        (tmp_path / "skill" / "references" / "api" / "tasks.md").write_bytes(
            b"# Tasks\n\n`Task(fn)` `[SRC:pkg/tasks/task.py:L24]`\n")
        record = self._homonym(tmp_path, "# demo\n")
        assert brief([record]) == [("Info", "observation", "Documented extra: Task", "pkg/tasks/task.py:24", "Task")]
        assert record["issue"].endswith("the source still declares; of the 2 files that declare it, the skill "
                                        "cites only `pkg/tasks/task.py`")

    @pytest.mark.parametrize("skill_md, kwargs", [
        ("# demo\n\n`Task` `[AST:pkg/tasks/task.py:L24]` `[AST:pkg/models/Task.py:L9]`\n", {}),
        ("# demo\n\n`Task` `[AST:pkg/tasks/__init__.py:L1]`\n", {}),
        ("# demo\n\n`Task`\nPlain text.\nSee `[AST:pkg/tasks/task.py:L24]`\n", {}),
        ("# demo\n\n### `Task`\n\n`[AST:pkg/tasks/task.py:L24]` `[AST:pkg/models/Task.py:L9]`\n", {}),
        ("# demo\n\nSee `[AST:pkg/tasks/Task.py:L3]` and `[AST:pkg/models/Task.py:L9]`\n", {}),
        ("# demo\n\n`Task` `[AST:pkg/tasks/task.py:L24]`\n", {"skill": False}),
        ("# demo\n\n`Task` `[AST:pkg/tasks/task.py:L24]`\n", {"item": HOMONYM | {"declared_in": ["pkg/tasks/task.py:24"]}}),
        ("# demo\n\n`Task` `[AST:pkg/tasks/task.py:L24]`\n", {"item": HOMONYM | {"declared_in": "pkg/tasks/task.py:24"}}),
        ("# demo\n\n`Task` `[AST:pkg/tasks/task.py:L24]`\n", {"item": HOMONYM | {"declared_in": [
            "pkg/models/Task.py:9", "pkg/tasks/task.py"]}}),
        ("# demo\n\n`Task` `[AST:pkg/tasks/task.py:L24]`\n", {"item": HOMONYM | {"declared_in": None}}),
        ("# demo\n\n`Rescoped` `[AST:pkg/tasks/task.py:L24]`\n", {"name": "Rescoped"}),
    ], ids=["both-cited", "neither-cited", "cited-two-lines-on", "both-on-the-next-line", "named-only-in-a-citation",
            "no-skill-dir",
            "one-file", "not-a-list", "an-item-without-a-line", "no-declared-in", "rescoped"])
    def test_any_other_homonym_stays_medium(self, tmp_path: Path, skill_md: str, kwargs: dict):
        record = self._homonym(tmp_path, skill_md, **kwargs)
        assert (record["severity"], record["category"]) == ("Medium", "stale-documentation"), record

    @pytest.mark.parametrize("excluded, message", [
        (["Rescoped"], "'excluded' must be an object"),
        ({"outsideScope": "Rescoped"}, "'excluded.outsideScope' must be a list"),
    ])
    def test_a_malformed_excluded_is_invalid_input(self, excluded, message):
        """Read once a stale name that is not fabricated needs it: no stale name, or a fabricated one alone,
        never reads it."""
        ghost = {"name": "ghost", "fabricated": True, "source": "src/a.py:3"}
        for extraction in ({"status": "ok"}, None):
            surface = self.SURFACE | {"extraction": extraction, "excluded": excluded}
            with pytest.raises(mod.AdapterError, match=re.escape(message)):
                mod.from_coverage({"branch": "enumerated", "missing": [], "stale": ["Task"]},
                                  surface=surface, stale=[{"name": "Task", "fabricated": False}])
            assert mod.from_coverage({"branch": "enumerated", "missing": ["fetchData"], "stale": []},
                                     surface=surface, stale=[])[0]["category"] == "missing-export"
            [record] = mod.from_coverage({"branch": "enumerated", "missing": [], "stale": ["ghost"]},
                                         surface=surface, stale=[ghost])
            assert record["category"] == "fabricated-signature"

    def test_the_citation_scan_is_the_verifiers(self, tmp_path: Path):
        """The skill citations the homonym pick reads, and the files it reads them in, are the verifier's."""
        path = SCRIPT.parents[2] / "shared" / "scripts" / "skf-verify-provenance-completeness.py"
        text = SCRIPT.read_text(encoding="utf-8")
        for name in ("_SKILL_CITATION_RE", "skill_markdown_files"):
            assert f"Keep identical to {name} in skf-verify-provenance-completeness.py." in text, name
        pin = importlib.util.spec_from_file_location("skf_pin_verify_provenance_citations", path)
        verifier = importlib.util.module_from_spec(pin)
        pin.loader.exec_module(verifier)
        assert (mod._SKILL_CITATION_RE.pattern, mod._SKILL_CITATION_RE.flags) == (
            verifier._SKILL_CITATION_RE.pattern, verifier._SKILL_CITATION_RE.flags)
        skill = tmp_path / "skill"
        for rel in ("SKILL.md", "references/b.md", "references/a.md", "references/deep/c.md", "references/x.txt",
                    "notes.md"):
            (skill / rel).parent.mkdir(parents=True, exist_ok=True)
            (skill / rel).write_bytes(b"# x\n")
        assert mod.skill_markdown_files(skill) == verifier.skill_markdown_files(skill)
        assert [p.relative_to(skill).as_posix() for p in mod.skill_markdown_files(skill)] == [
            "SKILL.md", "references/a.md", "references/b.md", "references/deep/c.md"]

    def test_the_defined_at_extensions_are_the_verifiers(self):
        """`_DEFINED_AT_RE` takes the files classify-stale reads a `defined_at` in, and no other."""
        path = SCRIPT.parents[2] / "shared" / "scripts" / "skf-verify-provenance-completeness.py"
        note = "# Keep identical to PYTHON_EXTENSIONS | TSJS_EXTENSIONS in skf-verify-provenance-completeness.py."
        assert note in SCRIPT.read_text(encoding="utf-8")
        pin = importlib.util.spec_from_file_location("skf_pin_verify_provenance", path)
        verifier = importlib.util.module_from_spec(pin)
        pin.loader.exec_module(verifier)
        assert mod._DEFINED_AT_EXTENSIONS == verifier.PYTHON_EXTENSIONS | verifier.TSJS_EXTENSIONS
        for ext in mod._DEFINED_AT_EXTENSIONS:
            assert mod._DEFINED_AT_RE.match(f"pkg/m{ext}:7"), ext
        assert not mod._DEFINED_AT_RE.match("pkg/m.rb:7")

    @pytest.mark.parametrize("branch", ["scalar", "stack"])
    def test_a_missing_count_is_one_gap(self, branch: str):
        records = mod.from_coverage({"branch": branch, "denominator": 10, "documented": 7, "missing": [],
                                     "missingCount": 3, "numeratorSource": "lookup"}, metadata="pkg/metadata.json")
        assert brief(records) == [("Medium", "missing-export", "3 of 10 exports not documented",
                                   "pkg/metadata.json", None)]

    def test_a_verified_numerator_names_each_absent_export(self):
        cov = {"branch": "scalar", "denominator": 4, "documented": 2, "missing": [], "missingCount": 2,
               "numeratorSource": "verified"}
        records = mod.from_coverage(
            cov, numerator={"inflated": True, "absent": ["alpha", "beta"]},
            provenance={"entries": [{"export_name": "alpha", "source_file": "src/a.ts", "source_line": 7},
                                    {"export_name": "alpha", "source_file": "src/z.ts", "source_line": 1}]})
        assert brief(records) == [("Medium", "missing-export", "Missing export: alpha", "src/a.ts:7", "alpha"),
                                  ("Medium", "missing-export", "Missing export: beta", "metadata.json", "beta")]
        with pytest.raises(mod.AdapterError, match="--numerator"):
            mod.from_coverage(cov)

    def test_nothing_to_record(self):
        assert mod.from_coverage({"branch": "docsOnly", "missing": [], "stale": [], "incomplete": [{}]}) == []
        assert mod.from_coverage({"branch": "scalar", "missingCount": 0, "denominator": 3}) == []

    @pytest.mark.parametrize("cov, options, message", [
        ({"missing": []}, {}, "reconcile-coverage.py"),
        ({"branch": "sideways"}, {}, "unknown branch"),
        ({"branch": "enumerated", "missing": "x"}, {}, "'missing' must be a list"),
        ({"branch": "enumerated", "missing": []}, {"stale": {"name": "x"}}, "classify-stale"),
        ({"branch": "enumerated", "missing": []}, {"surface": {"sets": {}}}, "--surface"),
        # a Critical gap is never downgraded for want of its citation
        ({"branch": "enumerated", "missing": [], "stale": ["ghost"]},
         {"stale": [{"name": "ghost", "fabricated": True, "source": None}]}, "'ghost' is fabricated with no source"),
    ], ids=["no-branch", "unknown-branch", "missing-not-a-list", "stale-not-a-list", "surface-shape",
            "fabricated-without-source"])
    def test_a_wrong_shape_is_refused(self, cov, options, message):
        with pytest.raises(mod.AdapterError, match=message):
            mod.from_coverage(cov, **options)


class TestCountAdapters:
    def test_guards(self):
        surface = {"inputs": {"metadata": "pkg/metadata.json", "brief": "data/skill-brief.yaml"}, "guards": {
            "deflation": {"fires": True, "rederived": 40, "pct": 60.0, "effectiveDenominator": 25},
            "inflation": {"fires": True, "scopeIncludeUnion": 50, "pct": 100.0, "provenanceEntries": 25},
            "umbrella": {"umbrella": False}}}
        records = mod.from_guards(surface)
        assert brief(records) == [
            ("Medium", "metadata-drift",
             "denominator deflation: effective_denominator below source public surface without tier_a_include",
             "pkg/metadata.json", None),
            ("Medium", "denominator-inflation",
             "denominator inflation: coarse scope.include union exceeds authored surface",
             "data/skill-brief.yaml", None),
        ]
        assert "40 exports, 60.0% above `stats.effective_denominator` (25)" in records[0]["issue"]
        assert "`scope.tier_a_include`" in records[1]["remediation"]
        surface["guards"]["umbrella"]["umbrella"] = True
        umbrella = mod.from_guards(surface, "other/metadata.json")[1]["remediation"]
        assert umbrella.startswith("Set `stats.effective_denominator` in `other/metadata.json`")
        assert mod.from_guards({"inputs": {}, "guards": None}) == []
        assert mod.from_guards({"inputs": {}, "guards": {"deflation": {"fires": False}}}) == []

    def test_the_guards_say_when_no_tier_a_glob_matches_a_file(self):
        """#695: the guards fire on a brief whose tier A globs all match no file. The titles (the dedupe
        key) stay; the issue says no glob matches instead of the brief having none, and the fix edits the
        globs instead of adding them."""
        surface = {"inputs": {"metadata": "pkg/metadata.json", "brief": "data/skill-brief.yaml"}, "guards": {
            "deflation": {"fires": True, "rederived": 40, "pct": 60.0, "effectiveDenominator": 25},
            "inflation": {"fires": True, "scopeIncludeUnion": 50, "pct": 100.0, "provenanceEntries": 25},
            "staleScope": {"fires": False, "unmatchedTierAInclude": ["src/old/**"]},
            "umbrella": {"umbrella": False}}}
        deflation, inflation = mod.from_guards(surface)
        assert [deflation["title"], inflation["title"]] == [
            "denominator deflation: effective_denominator below source public surface without tier_a_include",
            "denominator inflation: coarse scope.include union exceeds authored surface"]
        assert deflation["issue"] == (
            "the re-derived surface counts 40 exports, 60.0% above `stats.effective_denominator` (25), and no "
            "`scope.tier_a_include` glob in the brief matches a file")
        assert inflation["issue"] == (
            "the `scope.include` union counts 50 exports, 100.0% above the 25 provenance entries, and no "
            "`scope.tier_a_include` glob in the brief matches a file")
        assert deflation["remediation"].endswith(
            "or edit `scope.tier_a_include` in the brief so its globs match the files of the authored tier the "
            "smaller count measures.")
        assert inflation["remediation"] == (
            "Edit `scope.tier_a_include` in `data/skill-brief.yaml` so its globs match the files of the authored "
            "surface: the denominator then counts it instead of the coarse `scope.include` union.")
        # Without the key (a surface from before #695) the text is the one a brief with no tier A glob gets.
        del surface["guards"]["staleScope"]["unmatchedTierAInclude"]
        assert [r["issue"].endswith("and the brief has no `scope.tier_a_include`")
                for r in mod.from_guards(surface)] == [True, True]

    def test_a_stale_brief_scope_is_one_gap_at_the_brief(self):
        """#677: a scope.include glob that matches no file, and the root exports the surface restored."""
        stale = {"applicable": True, "fires": True, "unmatchedInclude": ["cognee/pipelines.py"],
                 "restored": [{"name": "Task", "file": "cognee/pipelines/task.py", "line": 2},
                              {"name": "run_pipeline", "file": "cognee/pipelines/run.py", "line": 4}]}
        surface = {"inputs": {"brief": "data/cognee/skill-brief.yaml"}, "guards": {"staleScope": stale}}
        records = mod.from_guards(surface)
        assert brief(records) == [("Medium", "brief-scope-stale",
                                   "stale brief scope: scope.include globs match no source file",
                                   "data/cognee/skill-brief.yaml", None)]
        # Each restored export comes with its file, the one the remediation may add to scope.exclude.
        assert records[0]["issue"] == (
            "the `scope.include` glob `cognee/pipelines.py` matches no file in the source tested; the `all` set "
            "restores 2 root exports, defined in files no include glob covers: `Task` in "
            "`cognee/pipelines/task.py`, `run_pipeline` in `cognee/pipelines/run.py`")
        # update-skill never rewrites an include glob: the fix is a hand edit of the brief.
        assert records[0]["remediation"] == (
            "Edit `scope.include` in `data/cognee/skill-brief.yaml` by hand so each glob matches the files it "
            "meant in this version of the source (update-skill does not rewrite an include glob), and add to "
            "`scope.exclude` any restored file the brief meant to leave out.")
        # One restored export and two globs: each count takes its own grammatical number.
        stale.update(unmatchedInclude=["cognee/pipelines.py", "docs/**"], restored=stale["restored"][:1])
        assert mod.from_guards(surface)[0]["issue"] == (
            "the `scope.include` globs `cognee/pipelines.py`, `docs/**` match no file in the source tested; the "
            "`all` set restores 1 root export, defined in a file no include glob covers: `Task` in "
            "`cognee/pipelines/task.py`")
        # Without --brief the surface records no brief path: the gap cites the bare file name.
        stale["restored"] = []
        record = mod.from_guards({"inputs": {}, "guards": {"staleScope": stale}})[0]
        assert record["source"] == "skill-brief.yaml" and record["issue"].endswith("; no root export was restored")
        stale["fires"] = False
        assert mod.from_guards(surface) == []
        stale.update(fires=True, unmatchedInclude="cognee/pipelines.py")
        with pytest.raises(mod.AdapterError, match="'unmatchedInclude' must be a list"):
            mod.from_guards(surface)

    def test_a_stale_tier_a_glob_is_named_in_the_same_gap(self):
        """#695: a scope.tier_a_include glob that matches no file, alone or beside a stale include glob,
        is one Medium brief-scope-stale gap at the brief."""
        stale = {"applicable": True, "fires": True, "unmatchedInclude": [],
                 "unmatchedTierAInclude": ["cognee/modules/observability/trace_context/**"], "restored": []}
        surface = {"inputs": {"brief": "data/cognee/skill-brief.yaml"}, "guards": {"staleScope": stale}}
        records = mod.from_guards(surface)
        assert brief(records) == [("Medium", "brief-scope-stale",
                                   "stale brief scope: scope.tier_a_include globs match no source file",
                                   "data/cognee/skill-brief.yaml", None)]
        assert records[0]["issue"] == (
            "the `scope.tier_a_include` glob `cognee/modules/observability/trace_context/**` matches no file in "
            "the source tested, so it counts no name")
        assert records[0]["remediation"] == (
            "Edit `scope.tier_a_include` in `data/cognee/skill-brief.yaml` by hand so each glob matches the files "
            "it meant in this version of the source (update-skill does not rewrite a tier A glob).")
        # Two tier A globs take the plural.
        stale["unmatchedTierAInclude"].append("cognee/old/**")
        assert mod.from_guards(surface)[0]["issue"] == (
            "the `scope.tier_a_include` globs `cognee/modules/observability/trace_context/**`, `cognee/old/**` "
            "match no file in the source tested, so they count no name")
        # Beside a stale include glob: one gap, the include clauses first, as the runner's warnings are.
        stale.update(unmatchedInclude=["cognee/pipelines.py"], unmatchedTierAInclude=["cognee/old/**"],
                     restored=[{"name": "Task", "file": "cognee/pipelines/task.py", "line": 2}])
        records = mod.from_guards(surface)
        assert brief(records) == [(
            "Medium", "brief-scope-stale",
            "stale brief scope: scope.include and scope.tier_a_include globs match no source file",
            "data/cognee/skill-brief.yaml", None)]
        assert records[0]["issue"] == (
            "the `scope.include` glob `cognee/pipelines.py` matches no file in the source tested; the `all` set "
            "restores 1 root export, defined in a file no include glob covers: `Task` in "
            "`cognee/pipelines/task.py`; the `scope.tier_a_include` glob `cognee/old/**` matches no file in the "
            "source tested, so it counts no name")
        assert records[0]["remediation"] == (
            "Edit `scope.include` and `scope.tier_a_include` in `data/cognee/skill-brief.yaml` by hand so each "
            "glob matches the files it meant in this version of the source (update-skill does not rewrite an "
            "include or tier A glob), and add to `scope.exclude` any restored file the brief meant to leave out.")
        # An empty tier A list leaves the include-only gap as #677 wrote it.
        stale["unmatchedTierAInclude"] = []
        assert mod.from_guards(surface)[0]["title"] == "stale brief scope: scope.include globs match no source file"
        stale["unmatchedTierAInclude"] = "cognee/old/**"
        with pytest.raises(mod.AdapterError, match="'unmatchedTierAInclude' must be a list"):
            mod.from_guards(surface)

    def test_a_rerun_records_the_stale_scope_gap_once(self, tmp_path):
        surface = tmp_path / "surface.json"
        surface.write_text(json.dumps({"inputs": {"brief": "skill-brief.yaml"}, "guards": {"staleScope": {
            "fires": True, "unmatchedInclude": ["a.py"], "restored": [{"name": "x", "file": "a/x.py"}]}}}))
        ledger = tmp_path / "test-findings-r.json"
        first = run("append", "--ledger", str(ledger), "--stage", "coverage-check", "--from", "guards",
                    "--input", str(surface))
        second = run("append", "--ledger", str(ledger), "--stage", "coverage-check", "--from", "guards",
                     "--input", str(surface))
        assert json.loads(first.stdout)["appended"] == ["GAP-001"]
        assert json.loads(second.stdout)["duplicates"] == ["GAP-001"]

    def test_numerator(self):
        records = mod.from_numerator({"inflated": True, "declared": 10, "verified": 7,
                                      "absent": ["a", "b", "c"]}, "pkg/metadata.json")
        assert brief(records) == [
            ("High", "numerator-inflation",
             "numerator inflation: 3 of 10 declared exports absent from SKILL.md/references",
             "pkg/metadata.json", None)]
        assert records[0]["issue"].endswith("`a`, `b`, `c`")
        assert mod.from_numerator({"inflated": False, "skipped": True}) == []
        with pytest.raises(mod.AdapterError):
            mod.from_numerator({"declared": 3})

    def test_metadata_coherence(self):
        records = mod.from_metadata_coherence({"findings": [
            {"severity": "Medium", "title": "metadata drift: barrel export counts diverge", "detail": "12 vs 9"},
            {"severity": "Info", "title": "multi-denominator reporting: barrel vs documented surface",
             "detail": "barrel=9, documented=30"},
        ]}, "pkg/metadata.json")
        assert [(r["severity"], r["category"], r["source"], r["issue"]) for r in records] == [
            ("Medium", "metadata-drift", "pkg/metadata.json", "12 vs 9"),
            ("Info", "multi-denominator", "pkg/metadata.json", "barrel=9, documented=30")]
        assert mod.from_metadata_coherence({"skipped": True, "findings": []}) == []
        with pytest.raises(mod.AdapterError, match="neither Medium nor Info"):
            mod.from_metadata_coherence({"findings": [{"severity": "High", "title": "x"}]})


class TestProvenanceAndCoherenceAdapters:
    def test_provenance_line(self):
        records = mod.from_provenance_line({"stale": [
            {"export_name": "search", "source_file": "lib/api.py", "source_line": 25,
             "reason": "line-not-definition", "definition_lines": [26, 31]},
            {"export_name": "fetch", "source_file": "lib/api.py", "source_line": 40,
             "reason": "line-not-definition", "definition_lines": []},
            {"export_name": "gone", "source_file": "lib/old.py", "source_line": 3, "reason": "file-missing"},
        ]})
        assert brief(records) == [
            ("Low", "provenance-line", "Provenance line is not the definition of search", "lib/api.py:25", "search"),
            ("Info", "provenance-unverified", "Provenance line not verified for fetch", "lib/api.py:40", "fetch"),
        ]
        assert records[0]["remediation"].startswith(
            "Set the provenance `source_line` of `search` in `lib/api.py` to its definition line (26, 31)")
        assert "check by hand" in records[1]["issue"]

    def test_coherence(self):
        records = mod.from_coherence({"invalidReferences": [
            {"source": "scan", "line": 4, "target": "references/gone.md", "status": "missing",
             "canonical": "/s/references/gone.md", "root": "skill", "issues": []},
            {"source": "judged", "line": 9, "target": "Options", "status": "inaccurate", "canonical": None,
             "root": None, "issues": ["type_match: false"]},
            {"source": "scan", "line": None, "target": "../../etc/passwd", "status": "escapes",
             "canonical": "/etc/passwd", "root": None, "issues": []},
        ]})
        assert brief(records) == [
            ("Critical", "broken-reference", "coherence: broken reference: references/gone.md", "SKILL.md:4", None),
            ("High", "inaccurate-reference", "coherence: inaccurate reference: Options", "SKILL.md:9", None),
            ("High", "reference-escape",
             "coherence: reference escapes skill/source sandbox: ../../etc/passwd → /etc/passwd",
             "SKILL.md", None),
        ]
        assert records[1]["issue"] == "type_match: false"
        assert mod.from_coherence({"invalidReferences": []}) == []
        with pytest.raises(mod.AdapterError, match="unknown status"):
            mod.from_coherence({"invalidReferences": [{"status": "odd"}]})


def scan(*args: str) -> dict:
    proc = subprocess.run([sys.executable, str(SCANNER), *args], capture_output=True, text=True,
                          encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


class TestStructureAdapter:
    def test_the_scanner_results(self, tmp_path: Path):
        skill = tmp_path / "skill"
        (skill / "scripts").mkdir(parents=True)
        (skill / "SKILL.md").write_bytes(
            b"---\nname: demo\n---\n# demo\n\n## Usage Examples\n\n```\nrun()\n```\n\n"
            b"| a | b |\n|---|---|\n| 1 |\n\n```bash\n# API\n")
        required = scan("scan", str(skill / "SKILL.md"), "--required-sections")
        structure = scan("scan", str(skill / "SKILL.md"))
        usage = {"scope": {}, "exports": [], "zero_usage": [{"name": "fetchData", "kind": "function"}]}
        records = mod.from_structure([required, structure, usage], served=["usage"])
        assert brief(records) == [
            ("High", "structural", "naive-coherence: missing required section: description", "SKILL.md", None),
            ("High", "structural", "naive-coherence: missing required section: api_surface", "SKILL.md", None),
            ("High", "structural", "naive-coherence: unbalanced code fence (unclosed block)", "SKILL.md", None),
            ("Medium", "structural", "naive-coherence: opening code fence at line 8 missing language tag",
             "SKILL.md:8", None),
            ("Medium", "structural", "naive-coherence: table row at line 14 has 1 columns; header has 2",
             "SKILL.md:14", None),
            ("Medium", "scripts-assets",
             "naive-coherence: scripts/assets directory exists but Scripts & Assets section missing",
             "SKILL.md", None),
            ("Medium", "structural",
             "naive-coherence: exported function `fetchData` is not referenced in any usage-family section or "
             "reference file", "SKILL.md", "fetchData"),
        ]

    def test_the_frontmatter_description_satisfies_its_family(self):
        required = {family: {"satisfied": False, "tried": []} for family in mod.FAMILIES}
        required["frontmatter_description"] = True
        assert [r["title"] for r in mod.from_structure([required], served=["api_surface"])] == [
            "naive-coherence: missing required section: usage"]

    def test_the_contextual_reference_check(self, tmp_path: Path):
        skill = tmp_path / "skill"
        (skill / "assets").mkdir(parents=True)
        (skill / "SKILL.md").write_bytes(b"# demo\n\nSee [guide](references/guide.md).\n")
        references = scan("reference-check", str(skill / "SKILL.md"))
        assert brief(mod.from_structure([references])) == [
            ("Medium", "scripts-assets",
             "coherence: scripts/assets directory exists but Scripts & Assets section missing", "SKILL.md", None)]

    def test_an_unknown_shape_is_refused(self):
        with pytest.raises(mod.AdapterError, match="--input #2"):
            mod.from_structure([{"unbalanced_fences": False}, {"invalidReferences": []}])

    def test_the_titles_are_the_prose_finding_texts(self):
        """§2's finding texts go into the Coherence Analysis and the script's titles into the ledger: one
        wording for both."""
        text = COHERENCE_STEP.read_text(encoding="utf-8")
        texts = {t.replace("\\`", "`") for t in re.findall(r"`(naive-coherence: (?:[^`\\]|\\`)+)`", text)}
        values = {"{family}": "usage", "{entry.line}": "7", "{entry.actual_cols}": "1",
                  "{entry.expected_cols}": "2", "{kind}": "function", "{name}": "go"}
        for key, value in values.items():
            texts = {t.replace(key, value) for t in texts}
        required = {family: {"satisfied": family != "usage", "tried": []} for family in mod.FAMILIES}
        scan_result = {"unbalanced_fences": True, "fence_count": 3, "bare_opening_fences": [{"line": 7}],
                       "table_drift": [{"line": 7, "expected_cols": 2, "actual_cols": 1}],
                       "scripts_assets": {"missing": True, "folders": ["scripts"]}}
        usage = {"zero_usage": [{"name": "go", "kind": "function"}]}
        titles = {r["title"] for r in mod.from_structure([required, scan_result, usage])}
        assert len(titles) == 6 and titles <= texts, sorted(titles - texts)


class TestAppendFrom:
    def test_a_rerun_records_each_gap_once(self, ledger: Path, tmp_path: Path):
        result = write_json(tmp_path / "coherence.json", {"invalidReferences": [
            {"line": 3, "target": "references/x.md", "status": "missing", "issues": []}]})
        first = json.loads(from_file(ledger, "coherence-check", "coherence", result).stdout)
        again = json.loads(from_file(ledger, "coherence-check", "coherence", result).stdout)
        assert (first["appended"], again["appended"], again["duplicates"]) == (["GAP-001"], [], ["GAP-001"])
        assert json.loads(ledger.read_bytes())["stages"] == ["coherence-check"]

    def test_no_gap_still_records_the_stage(self, ledger: Path, tmp_path: Path):
        result = write_json(tmp_path / "numerator.json", {"inflated": False, "skipped": True})
        proc = from_file(ledger, "coverage-check", "numerator", result)
        assert proc.returncode == 0, proc.stdout
        assert json.loads(ledger.read_bytes()) == {"schema_version": 1, "run_id": RUN_ID,
                                                   "stages": ["coverage-check"], "records": []}

    @pytest.mark.parametrize("kind, inputs, options, message", [
        ("coherence", 1, {"metadata": "m.json"}, "--from coherence does not read --metadata"),
        ("coverage", 1, {"served": "usage"}, "--from coverage does not read --served"),
        ("numerator", 2, {}, "--from numerator reads one --input file"),
        ("structure", 0, {}, "--from structure reads one or more --input files"),
    ], ids=["stray-metadata", "stray-served", "two-inputs", "no-input"])
    def test_a_call_its_kind_does_not_read_is_refused(self, ledger: Path, tmp_path: Path, kind, inputs, options,
                                                      message):
        result = write_json(tmp_path / "result.json", {"inflated": False})
        proc = from_file(ledger, "coverage-check", kind, *([result] * inputs), **options)
        assert proc.returncode == 2
        out = json.loads(proc.stdout)
        assert (out["code"], out["error"]) == ("INVALID_INPUT", message)
        assert not ledger.exists()

    def test_an_adapter_option_needs_from(self, ledger: Path, tmp_path: Path):
        records = write_json(tmp_path / "records.json", [record()])
        proc = run("append", "--ledger", str(ledger), "--stage", "coverage-check", "--input", str(records),
                   "--surface", str(records))
        assert proc.returncode == 2
        assert json.loads(proc.stdout)["error"] == "--surface work only with --from"

    def test_a_result_that_is_not_its_kind_is_refused(self, ledger: Path, tmp_path: Path):
        proc = from_file(ledger, "coverage-check", "coverage", write_json(tmp_path / "x.json", ["not", "it"]))
        assert proc.returncode == 2 and json.loads(proc.stdout)["code"] == "INVALID_INPUT"
        broken = tmp_path / "broken.json"
        broken.write_bytes(b"{")
        proc = from_file(ledger, "coverage-check", "coverage", broken)
        assert proc.returncode == 2 and "is not JSON" in json.loads(proc.stdout)["error"]
        assert not ledger.exists()

    def test_plain_append_reads_each_input(self, ledger: Path, tmp_path: Path):
        one = write_json(tmp_path / "one.json", [record(title="one")])
        two = write_json(tmp_path / "two.json", {"records": [record(title="two")]})
        proc = run("append", "--ledger", str(ledger), "--stage", "coverage-check", "--input", str(one),
                   "--input", str(two))
        assert json.loads(proc.stdout)["appended"] == ["GAP-001", "GAP-002"]


def prose_calls(path: Path, start: str, end: str) -> list[str]:
    """The fenced `uv run {gapLedgerScript} append` calls between two markers,
    every bracketed group kept, without the heredoc's."""
    text = path.read_text(encoding="utf-8")
    section = text[text.index(start):text.index(end, text.index(start))]
    calls = [line.strip() for line in section.splitlines()
             if line.strip().startswith("uv run {gapLedgerScript} append") and "<<" not in line]
    return [OPTIONAL_GROUP.sub(lambda m: " " + m.group(1), call) for call in calls]


def run_prose(call: str, values: dict[str, str]) -> subprocess.CompletedProcess:
    rest = call.removeprefix("uv run {gapLedgerScript} ")
    for key, value in values.items():
        rest = rest.replace(key, value)
    assert not re.search(r"\{\w+\}|<\w+>", rest), rest
    return run(*shlex.split(rest))


class TestTheProseCalls:
    """Each `append` the two stages write, run as written over the files their scripts write."""

    def test_coverage_check_records_every_script_gap(self, ledger: Path, tmp_path: Path):
        run_dir, skill = tmp_path / "run", tmp_path / "skill"
        skill.mkdir()
        (skill / "SKILL.md").write_bytes(b"# demo\n\n`oldName()` still documented.\n\n`Task(fn)` wraps a step.\n")
        write_json(run_dir / "signature-gaps.json", [record(severity="Critical", category="signature-mismatch",
                                                             title="Signature mismatch: helper", export="helper")])
        write_json(run_dir / "coverage.json", {"branch": "enumerated", "missing": ["Options", "fetchData"],
                                               "stale": ["oldName", "ghost", "Task"]})
        write_json(run_dir / "surface.json", TestCoverageAdapter.EXCLUDED_SURFACE | {"guards": {
            "deflation": {"fires": True, "rederived": 9, "pct": 50.0, "effectiveDenominator": 6},
            "inflation": {"fires": False}, "umbrella": {"umbrella": False}}})
        write_json(run_dir / "signatures.json", {"missingTypes": ["Options"]})
        write_json(run_dir / "numerator.json", {"inflated": True, "declared": 4, "verified": 3, "absent": ["x"]})
        # #678: Task, which the source still declares, is a documented extra
        write_json(run_dir / "stale.json", [{"name": "ghost", "fabricated": True, "source": "src/g.ts:2"},
                                            {"name": "Task", "fabricated": False, "source": None,
                                             "defined_at": "src/task.ts:4"}])
        write_json(run_dir / "metadata-coherence.json", {"findings": [
            {"severity": "Info", "title": "multi-denominator reporting", "detail": "barrel=3"}]})
        write_json(run_dir / "provenance-verify.json", {"stale": [
            {"export_name": "fetchData", "source_file": "src/fetch.ts", "source_line": 11,
             "reason": "line-not-definition", "definition_lines": [12]}]})
        provenance = write_json(tmp_path / "provenance-map.json", {"entries": []})
        values = {"{ledgerFile}": ledger.as_posix(), "{run_dir}": run_dir.as_posix(),
                  "{resolved_skill_package}": skill.as_posix(), "{forge_provenance_map}": provenance.as_posix()}
        calls = prose_calls(COVERAGE_STEP, "### 5b. Record the Coverage Gaps", "### 6.")
        assert [re.search(r"--from (\S+)", c).group(1) if "--from" in c else None for c in calls] == [
            None, "coverage", "guards", "numerator", "metadata-coherence", "provenance-line"]
        for call in calls:
            proc = run_prose(call, values)
            assert proc.returncode == 0, (call, proc.stdout)
        assert {(r["severity"], r["category"]) for r in ledger_records(ledger)} == {
            ("Critical", "signature-mismatch"), ("Medium", "missing-type"), ("Medium", "missing-export"),
            ("Medium", "stale-documentation"), ("Critical", "fabricated-signature"), ("Medium", "metadata-drift"),
            ("High", "numerator-inflation"), ("Info", "multi-denominator"), ("Low", "provenance-line"),
            ("Info", "observation")}
        stale = next(r for r in ledger_records(ledger) if r["category"] == "stale-documentation")
        assert (stale["source"], stale["export"]) == ("SKILL.md:3", "oldName")
        extra = next(r for r in ledger_records(ledger) if r["category"] == "observation")
        assert (extra["title"], extra["source"], extra["export"]) == ("Documented extra: Task", "src/task.ts:4", "Task")
        assert extra["issue"].startswith("`SKILL.md:5` documents `Task`")

    def test_coherence_check_records_each_mode(self, ledger: Path, tmp_path: Path):
        run_dir, skill = tmp_path / "run", tmp_path / "skill"
        (skill / "scripts").mkdir(parents=True)
        (skill / "SKILL.md").write_bytes(b"# demo\n\n## Overview\n\nDoes it.\n\n## Usage Examples\n\n"
                                         b"```python\nrun()\n```\n")
        for name, args in (("required-sections", ("--required-sections",)), ("structure", ())):
            write_json(run_dir / f"{name}.json", scan("scan", str(skill / "SKILL.md"), *args))
        write_json(run_dir / "usage-scope.json", {"zero_usage": []})
        write_json(run_dir / "coherence.json", {"invalidReferences": [
            {"line": 5, "target": "Options", "status": "inaccurate", "issues": ["not exported"]}]})
        write_json(run_dir / "references.json", scan("reference-check", str(skill / "SKILL.md")))
        values = {"{ledgerFile}": ledger.as_posix(), "{run_dir}": run_dir.as_posix(), "<family>": "usage"}
        calls = prose_calls(COHERENCE_STEP, "### 6. Write the Coherence Analysis Section", "### 7.")
        assert len(calls) == 3
        for call in calls:
            proc = run_prose(call, values)
            assert proc.returncode == 0, (call, proc.stdout)
        # `## Usage Examples` serves usage (the --served judgment); no heading lists the exports
        assert [r["title"] for r in ledger_records(ledger)] == [
            "naive-coherence: missing required section: api_surface",
            "naive-coherence: scripts/assets directory exists but Scripts & Assets section missing",
            "coherence: inaccurate reference: Options",
            "coherence: scripts/assets directory exists but Scripts & Assets section missing",
        ]
