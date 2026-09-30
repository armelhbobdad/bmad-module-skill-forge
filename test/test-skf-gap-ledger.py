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
"""

from __future__ import annotations

import doctest
import importlib.util
import json
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
