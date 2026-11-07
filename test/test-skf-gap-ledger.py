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
    failed write leaves no temp file, a lock file Windows refuses to open
    while it is being removed is retried until the lock deadline and then
    LEDGER_LOCKED naming the refusal, and a refusal off Windows, with
    nothing at the lock path or with a folder there is WRITE_FAILED
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
  - an inflated `scope.include` union (#795): when the inflation guard
    fires on the set the barrel branch counts, its undocumented names are
    one Medium `denominator-inflation` gap at the brief listing at most 50
    of them; a stale name the brief scopes out (#796) is a Medium
    `stale-documentation` gap naming its file and the brief
  - a stale name's issue (#923): every kind opens with the line that
    documents the name, in SKILL.md or a reference file, else with `the
    skill`, never a bare `SKILL.md`, while a fabricated name's Source stays
    the file its provenance cites
  - the line that documents a stale name (#922, #966, #972): the first
    that writes it as an export (its floor origin, else a heading or an
    export table's first cell, else a code span that is the name or opens
    its call, else a fenced declaration, else a whole quoted string in a
    fenced block such as an `__all__` item), in SKILL.md or any reference
    file, nested ones included; never the frontmatter, a bare word, a span
    that holds the name among other words, a quoted string in prose or
    holding other words, a fence in an HTML comment or a data block; an
    unreadable input is skipped, and the floor is read once
  - an aliased name's provenance line (#911): with --stale, an unverified
    line of a name classify-stale marks `aliased` names the alias and asks
    to record the rename if no other entry already has its `export_name`,
    the renamed name else a phrase standing for it, else to cite the
    alias; an alias of `default` only cites the alias line; any other
    record keeps its text, and a --stale that is not a list is refused
"""

from __future__ import annotations

import doctest
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import textwrap
import time
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


def refuse_lock_open(monkeypatch: pytest.MonkeyPatch, times: int | None = None) -> list[str]:
    """Make opening a `.skf-lock` file raise PermissionError, as Windows does
    while the append that held it is removing it: the first `times` opens, or
    every open when `times` is None. Other opens go through. Returns the lock
    paths opened, refused or not. A retry that outlives its deadline fails the
    test after a few hundred opens instead of hanging it."""
    real_open = mod.os.open
    calls: list[str] = []

    def flaky_open(path, flags, *args, **kwargs):
        if os.fspath(path).endswith(".skf-lock"):
            calls.append(os.fspath(path))
            if len(calls) > 300:
                raise AssertionError(f"{len(calls)} opens of {os.fspath(path)}: the retry ignores its deadline")
            if times is None or len(calls) <= times:
                raise PermissionError(13, "Permission denied", os.fspath(path))
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(mod.os, "open", flaky_open)
    return calls


def pending_lock_file(ledger: Path) -> Path:
    """The ledger's lock file, left in place as a file whose removal is pending."""
    lock = ledger.with_name(ledger.name + ".skf-lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_bytes(b"")
    return lock


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

    def test_a_lock_file_windows_refuses_for_a_moment_is_retried(
        self, ledger: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        # Windows refuses to open the lock file while the append that held it
        # is removing it; the append retries.
        source = tmp_path / "records.json"
        source.write_text(json.dumps([record(title="retried")]), encoding="utf-8")
        pending_lock_file(ledger)
        monkeypatch.setattr(mod, "_IS_WINDOWS", True)
        calls = refuse_lock_open(monkeypatch, times=2)
        args = ["append", "--ledger", str(ledger), "--stage", "coverage-check", "--input", str(source)]
        assert mod.main(args) == 0
        assert json.loads(capsys.readouterr().out)["appended"] == ["GAP-001"]
        assert len(calls) == 3
        assert [r["title"] for r in json.loads(ledger.read_text(encoding="utf-8"))["records"]] == ["retried"]
        assert sorted(p.name for p in ledger.parent.iterdir()) == [ledger.name]

    def test_a_lock_file_windows_keeps_refusing_is_ledger_locked(
        self, ledger: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        append(ledger, "coverage-check", [record(title="before")])
        before = ledger.read_bytes()
        source = tmp_path / "records.json"
        source.write_text(json.dumps([record(title="after")]), encoding="utf-8")
        lock = pending_lock_file(ledger)
        monkeypatch.setattr(mod, "_IS_WINDOWS", True)
        monkeypatch.setattr(mod, "LOCK_TIMEOUT_SECONDS", 0.2)
        calls = refuse_lock_open(monkeypatch)
        args = ["append", "--ledger", str(ledger), "--stage", "coherence-check", "--input", str(source)]
        started = time.monotonic()
        assert mod.main(args) == 1
        assert time.monotonic() - started >= 0.2
        out = json.loads(capsys.readouterr().out)
        assert out["code"] == "LEDGER_LOCKED"
        assert out["error"].startswith(f"another append held {lock} for more than 0.2 s (last open refused: ")
        assert "Permission denied" in out["error"]
        assert len(calls) > 1
        assert ledger.read_bytes() == before
        assert sorted(p.name for p in ledger.parent.iterdir()) == sorted([ledger.name, lock.name])

    def test_a_refused_lock_file_off_windows_is_a_write_failure(
        self, ledger: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        source = tmp_path / "records.json"
        source.write_text(json.dumps([record()]), encoding="utf-8")
        pending_lock_file(ledger)
        monkeypatch.setattr(mod, "_IS_WINDOWS", False)
        calls = refuse_lock_open(monkeypatch)
        args = ["append", "--ledger", str(ledger), "--stage", "coverage-check", "--input", str(source)]
        assert mod.main(args) == 1
        assert json.loads(capsys.readouterr().out)["code"] == "WRITE_FAILED"
        assert len(calls) == 1
        assert not ledger.exists()

    def test_a_refusal_with_no_lock_file_is_a_write_failure(
        self, ledger: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        # Nothing at the lock path: the folder refuses the new file (an ACL, a
        # read-only folder), which no wait cures. One more open at once tells
        # it from a removal that ended just now.
        source = tmp_path / "records.json"
        source.write_text(json.dumps([record()]), encoding="utf-8")
        monkeypatch.setattr(mod, "_IS_WINDOWS", True)
        calls = refuse_lock_open(monkeypatch)
        args = ["append", "--ledger", str(ledger), "--stage", "coverage-check", "--input", str(source)]
        assert mod.main(args) == 1
        out = json.loads(capsys.readouterr().out)
        assert out["code"] == "WRITE_FAILED" and "Permission denied" in out["error"]
        assert len(calls) == 2
        assert not ledger.exists()

    def test_a_refusal_with_a_folder_at_the_lock_path_is_a_write_failure(
        self, ledger: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        source = tmp_path / "records.json"
        source.write_text(json.dumps([record()]), encoding="utf-8")
        ledger.with_name(ledger.name + ".skf-lock").mkdir(parents=True)
        monkeypatch.setattr(mod, "_IS_WINDOWS", True)
        calls = refuse_lock_open(monkeypatch)
        args = ["append", "--ledger", str(ledger), "--stage", "coverage-check", "--input", str(source)]
        assert mod.main(args) == 1
        out = json.loads(capsys.readouterr().out)
        assert out["code"] == "WRITE_FAILED" and "Permission denied" in out["error"]
        assert len(calls) == 1
        assert not ledger.exists()

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

    # #795: the inflation guard fired and the barrel branch counts the `scope.include` union it measured.
    INFLATED_SURFACE = SURFACE | {
        "inputs": {"metadata": "pkg/metadata.json", "brief": "data/skill-brief.yaml"},
        "guards": {"inflation": {"applicable": True, "fires": True, "pct": 140.0, "scopeIncludeUnion": 120,
                                 "provenanceEntries": 50}},
        "denominator": {"clause": "stratified-scope", "branch": "barrel", "surfaceSet": "scope.include",
                        "ladderStep": 1, "absentSet": None, "rebuild": None}}

    @pytest.mark.parametrize("clause", ["stratified-scope", "multi-entry"])
    def test_an_inflated_union_is_one_summary_gap_at_the_brief(self, clause: str):
        surface = self.INFLATED_SURFACE | {"denominator": self.INFLATED_SURFACE["denominator"] | {"clause": clause}}
        [record] = mod.from_coverage({"branch": "enumerated", "missing": ["fetchData", "Options", "fromMeta"],
                                      "stale": []},
                                     surface=surface, signatures={"missingTypes": ["Options"]},
                                     metadata="pkg/metadata.json")
        assert brief([record]) == [("Medium", "denominator-inflation",
                                    "undocumented names in the inflated scope.include union",
                                    "data/skill-brief.yaml", None)]
        # the union's size, and each name with the file and line the surface records for it, a type marked so
        assert record["issue"] == (
            "the inflation guard fired: the `scope.include` union the denominator counts (120 names) sweeps in names "
            "outside the authored surface, and SKILL.md and references/ do not document 3 of them: `fetchData` "
            "(`src/fetch.ts:12`), `Options` (a type, `src/types.ts:3`), `fromMeta`")
        # it defers to the guard's own gap at the same brief, which says how to correct the denominator
        assert record["remediation"] == (
            "Correct the denominator first, as the denominator-inflation gap for `data/skill-brief.yaml` says; then "
            "re-run Test Skill, and the names the corrected denominator counts that the skill does not document "
            "come back as gaps.")
        # with no brief named, the default one; with no union count, no size
        [record] = mod.from_coverage({"branch": "enumerated", "missing": ["fetchData"], "stale": []},
                                     surface=surface | {"inputs": {}, "guards": {"inflation": {"fires": True}}})
        assert record["source"] == "skill-brief.yaml"
        assert record["issue"].startswith("the inflation guard fired: the `scope.include` union the denominator "
                                          "counts sweeps in names")

    @pytest.mark.parametrize("change", [
        {"guards": {"inflation": {"applicable": True, "fires": False, "pct": 10.0}}},
        {"guards": None},
        {"denominator": {"clause": "standard-barrel", "branch": "barrel", "surfaceSet": "all", "absentSet": None}},
        # a set the surface lacked: the barrel counts `all` in its place
        {"denominator": {"clause": "stratified-scope", "branch": "barrel", "surfaceSet": "all",
                         "absentSet": "scope.include"}},
        # no tier A rung: these clauses count `scope.include` whatever tier A list the brief has
        {"denominator": {"clause": "specific-modules", "branch": "barrel", "surfaceSet": "scope.include",
                         "ladderStep": 2, "absentSet": None}},
        {"denominator": {"clause": "empty-barrel", "branch": "barrel", "surfaceSet": "scope.include",
                         "ladderStep": None, "absentSet": None}},
    ], ids=["not-fired", "no-guards", "another-set", "absent-set", "specific-modules", "empty-barrel"])
    def test_without_an_inflated_union_each_missing_name_is_its_own_gap(self, change: dict):
        records = mod.from_coverage({"branch": "enumerated", "missing": ["fetchData", "Options"], "stale": []},
                                    surface=self.INFLATED_SURFACE | change, metadata="pkg/metadata.json")
        assert brief(records) == [
            ("Medium", "missing-export", "Missing export: fetchData", "src/fetch.ts:12", "fetchData"),
            ("Medium", "missing-export", "Missing export: Options", "src/types.ts:3", "Options"),
        ]
        # nothing missing: no summary gap either
        assert mod.from_coverage({"branch": "enumerated", "missing": [], "stale": []},
                                 surface=self.INFLATED_SURFACE) == []

    def test_the_tier_a_clauses_are_the_loaders(self):
        """`_TIER_A_CLAUSES` holds the clauses whose ladder in load-coverage-inputs.py has a tier A rung."""
        note = ("# Keep identical to the CLAUSE_LADDERS clauses with a `tier_a_include` rung in "
                "load-coverage-inputs.py.")
        assert note in SCRIPT.read_text(encoding="utf-8")
        pin = importlib.util.spec_from_file_location("skf_pin_load_coverage_inputs",
                                                     SCRIPT.parent / "load-coverage-inputs.py")
        loader = importlib.util.module_from_spec(pin)
        pin.loader.exec_module(loader)
        assert mod._TIER_A_CLAUSES == {c for c, ladder in loader.CLAUSE_LADDERS.items() if "tier_a_include" in ladder}

    def test_the_summary_gap_lists_at_most_fifty_names(self):
        names = [f"name{i:02d}" for i in range(60)]
        [record] = mod.from_coverage({"branch": "enumerated", "missing": names, "stale": []},
                                     surface=self.INFLATED_SURFACE)
        listed = re.findall(r"`(name\d\d)`", record["issue"])
        assert listed == names[:50]
        assert "do not document 60 of them: `name00`, " in record["issue"]
        assert record["issue"].endswith("`name49`, and 10 more")

    def test_the_append_cli_records_the_summary_gap(self, ledger: Path, tmp_path: Path):
        cov = write_json(tmp_path / "run" / "coverage.json",
                         {"branch": "enumerated", "missing": ["fetchData", "Options"], "stale": []})
        surface = write_json(tmp_path / "run" / "surface.json", self.INFLATED_SURFACE)
        signatures = write_json(tmp_path / "run" / "signatures.json", {"missingTypes": ["Options"]})
        for _ in range(2):  # a rerun records it once
            proc = from_file(ledger, "coverage-check", "coverage", cov, surface=surface, signatures=signatures,
                             metadata="pkg/metadata.json")
            assert proc.returncode == 0, proc.stdout
        assert brief(ledger_records(ledger)) == [("Medium", "denominator-inflation",
                                                  "undocumented names in the inflated scope.include union",
                                                  "data/skill-brief.yaml", None)]
        assert ledger_records(ledger)[0]["issue"].endswith(
            "do not document 2 of them: `fetchData` (`src/fetch.ts:12`), `Options` (a type, `src/types.ts:3`)")

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
        # #923: each issue opens with the line that documents the name, else the skill, never a bare SKILL.md
        assert [r["issue"] for r in records] == [
            "the skill documents `ghost`, which the source API surface lacks and the cited file does not define",
            "`references/api.md:3` documents `get`, which the enumerated source API surface lacks",
            "the skill documents `nowhere`, which the enumerated source API surface lacks",
        ]

    def test_without_classify_stale_every_stale_name_is_medium(self):
        records = mod.from_coverage({"branch": "enumerated", "missing": [], "stale": ["ghost"]})
        assert brief(records) == [("Medium", "stale-documentation", "Stale documentation: ghost", "SKILL.md",
                                   "ghost")]
        # without the skill package, the issue names no file
        assert records[0]["issue"] == "the skill documents `ghost`, which the enumerated source API surface lacks"

    def test_a_stale_name_written_in_a_reference_file_names_that_line(self, ledger: Path, tmp_path: Path):
        """#923: the issue opens with the line its Source cites, in references/, as the CLI writes it."""
        skill = tmp_path / "skill"
        (skill / "references").mkdir(parents=True)
        (skill / "SKILL.md").write_bytes(b"# demo\n\nSee references.\n")
        (skill / "references" / "connectors.md").write_bytes(b"# Connectors\n\n`ColumnDef(name)` names a column.\n")
        coverage = write_json(tmp_path / "coverage.json", {"branch": "enumerated", "missing": [],
                                                           "stale": ["ColumnDef"]})
        proc = from_file(ledger, "coverage-check", "coverage", coverage, skill_dir=skill)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        [record] = ledger_records(ledger)
        assert brief([record]) == [("Medium", "stale-documentation", "Stale documentation: ColumnDef",
                                    "references/connectors.md:3", "ColumnDef")]
        assert record["issue"] == ("`references/connectors.md:3` documents `ColumnDef`, which the enumerated source "
                                   "API surface lacks")
        assert record["remediation"] == ("Check `ColumnDef` against the source and update or remove its documentation "
                                         "at references/connectors.md:3: the enumerated source surface does not "
                                         "export it.")

    def test_a_fabricated_names_issue_names_the_line_that_documents_it(self, tmp_path: Path):
        """#923: the issue names the line that writes the name, here in references/, while the Source stays the
        file its provenance cites; without the skill package the issue names no file."""
        skill = tmp_path / "skill"
        (skill / "references").mkdir(parents=True)
        (skill / "SKILL.md").write_bytes(b"# demo\n\nSee references.\n")
        (skill / "references" / "api.md").write_bytes(b"# API\n\nThe calls.\n\n`ghost(key)` reads a key.\n")
        cov = {"branch": "enumerated", "missing": [], "stale": ["ghost"]}
        stale = [{"name": "ghost", "fabricated": True, "source": "src/a.py:3", "reason": "not-defined"}]
        [record] = mod.from_coverage(cov, stale=stale, skill_dir=str(skill))
        assert brief([record]) == [("Critical", "fabricated-signature", "Fabricated signature: ghost", "src/a.py:3",
                                    "ghost")]
        assert record["issue"] == ("`references/api.md:5` documents `ghost`, which the source API surface lacks and "
                                   "the cited file does not define")
        assert record["remediation"] == ("Remove `ghost` from SKILL.md and references/, or correct it to the export "
                                         "the source defines: no file its provenance cites defines it "
                                         "(`src/a.py:3`).")
        [record] = mod.from_coverage(cov, stale=stale)
        assert record["source"] == "src/a.py:3"
        assert record["issue"] == ("the skill documents `ghost`, which the source API surface lacks and the cited "
                                   "file does not define")

    # #678: a stale name classify-stale finds declared is a documented extra, given a surface built from an
    # extraction (the only input that fills `excluded.outsideScope`).
    # A row as load-coverage-inputs.py writes it: the brief's exclude glob scopes the file out (#796).
    EXCLUDED = {"outsideScope": [{"name": "Rescoped", "file": "pkg/old/r.py", "line": 2, "entry": "pkg/__init__.py",
                                  "excludeGlob": "pkg/old/**", "outsideInclude": False}], "nestedEntries": []}
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

    BRIEFED_SURFACE = EXCLUDED_SURFACE | {"inputs": {"metadata": "pkg/metadata.json",
                                                 "brief": "data/skill-brief.yaml"}}
    RESCOPED = [{"name": "Rescoped", "fabricated": False, "source": None, "defined_at": "pkg/old/r.py:2"}]
    NARROW = ("narrow `pkg/old/**` so it no longer matches that file (to remove the glob instead, record a "
              "`demoted-exclude` scope-expansion amendment in the brief)")

    def _rescoped(self, *rows: dict, skill_dir: str | None = None) -> dict:
        surface = self.BRIEFED_SURFACE | {"excluded": {"outsideScope": list(rows), "nestedEntries": []}}
        [record] = mod.from_coverage({"branch": "enumerated", "missing": [], "stale": ["Rescoped"]},
                                     surface=surface, stale=self.RESCOPED, skill_dir=skill_dir)
        return record

    def test_a_name_an_exclude_glob_scopes_out_points_at_the_brief(self, tmp_path: Path):
        """#796: an entry point exports it from a file the brief's exclude glob matches: the gap names that file,
        the glob and the brief, not a source that lacks the name."""
        [record] = mod.from_coverage({"branch": "enumerated", "missing": [], "stale": ["Rescoped"]},
                                     surface=self.BRIEFED_SURFACE, stale=self.RESCOPED)
        assert brief([record]) == [("Medium", "stale-documentation", "Stale documentation: Rescoped", "SKILL.md",
                                    "Rescoped")]
        # no line documents it without the skill package: the issue names no file (#923)
        assert record["issue"] == ("the skill documents `Rescoped`, which the entry point `pkg/__init__.py` "
                                   "exports and `pkg/old/r.py:2` defines, a file `data/skill-brief.yaml` scopes out "
                                   "(`excluded.outsideScope`)")
        assert record["remediation"] == (
            "Decide whether `Rescoped` belongs on the surface: `data/skill-brief.yaml` scopes out `pkg/old/r.py:2`, "
            "where it is defined, since its `scope.exclude` glob `pkg/old/**` matches that file. To keep its "
            f"documentation, {self.NARROW}; else remove the documentation of `Rescoped` at SKILL.md.")
        assert "the enumerated source surface does not export it" not in record["remediation"]
        # with the skill package, the line that documents it; with no brief named, the default one
        skill = tmp_path / "skill"
        skill.mkdir()
        (skill / "SKILL.md").write_bytes(b"# demo\n\n`Rescoped()` runs.\n")
        [record] = mod.from_coverage({"branch": "enumerated", "missing": [], "stale": ["Rescoped"]},
                                     surface=self.EXCLUDED_SURFACE, stale=self.RESCOPED, skill_dir=str(skill))
        assert record["source"] == "SKILL.md:3" and record["issue"].startswith("`SKILL.md:3` documents `Rescoped`")
        assert "`skill-brief.yaml` scopes out" in record["remediation"]
        assert record["remediation"].endswith("remove the documentation of `Rescoped` at SKILL.md:3.")

    def test_a_name_no_include_glob_covers_points_at_the_brief(self):
        row = {"name": "Rescoped", "file": "lib/r.py", "line": None, "entry": None, "excludeGlob": None,
               "outsideInclude": True}
        record = self._rescoped(row)
        # no line: the file alone; no entry point named: any
        assert record["issue"] == ("the skill documents `Rescoped`, which an entry point exports and `lib/r.py` "
                                   "defines, a file `data/skill-brief.yaml` scopes out (`excluded.outsideScope`)")
        assert record["remediation"] == (
            "Decide whether `Rescoped` belongs on the surface: `data/skill-brief.yaml` scopes out `lib/r.py`, where "
            "it is defined, since no `scope.include` glob covers that file. To keep its documentation, widen "
            "`scope.include` to cover that file; else remove the documentation of `Rescoped` at SKILL.md.")
        # both: the include glob and the exclude glob
        record = self._rescoped(row | {"file": "pkg/old/r.py", "line": 2, "excludeGlob": "pkg/old/**"})
        assert record["remediation"] == (
            "Decide whether `Rescoped` belongs on the surface: `data/skill-brief.yaml` scopes out `pkg/old/r.py:2`, "
            "where it is defined, since no `scope.include` glob covers that file and its `scope.exclude` glob "
            "`pkg/old/**` matches it. To keep its documentation, widen `scope.include` to cover that file and "
            f"{self.NARROW}; else remove the documentation of `Rescoped` at SKILL.md.")

    @pytest.mark.parametrize("row", [
        # a file no recipe reads, or one a --files-from list leaves out: the brief covers it
        {"name": "Rescoped", "file": "pkg/old/r.py", "line": 2, "entry": None, "excludeGlob": None,
         "outsideInclude": False},
        # an older surface's row, which says nothing of the brief
        {"name": "Rescoped", "file": "pkg/old/r.py"},
        {"name": "Rescoped", "file": None, "line": None, "entry": None, "excludeGlob": "pkg/old/**",
         "outsideInclude": True},
        {"name": "Rescoped", "file": "", "excludeGlob": "pkg/old/**"},
    ], ids=["not-the-briefs-doing", "an-older-row", "no-file", "an-empty-file"])
    def test_a_scoped_out_row_the_brief_does_not_explain_keeps_the_generic_gap(self, row: dict):
        record = self._rescoped(row)
        assert brief([record]) == [("Medium", "stale-documentation", "Stale documentation: Rescoped", "SKILL.md",
                                    "Rescoped")]
        assert record["remediation"] == ("Check `Rescoped` against the source and update or remove its "
                                         "documentation at SKILL.md: the enumerated source surface does not export "
                                         "it.")

    def test_a_later_duplicate_row_that_names_the_file_wins(self):
        record = self._rescoped({"name": "Rescoped", "file": None, "excludeGlob": None, "outsideInclude": False},
                                {"name": "Rescoped", "file": "pkg/old/r.py", "line": None, "excludeGlob": None,
                                 "outsideInclude": False},
                                {"name": "Rescoped", "file": "pkg/old/r.py", "line": 2, "excludeGlob": "pkg/old/**",
                                 "outsideInclude": False},
                                {"name": "Rescoped", "file": "pkg/other.py", "line": 9, "excludeGlob": "pkg/other.py",
                                 "outsideInclude": False})
        assert "scopes out `pkg/old/r.py:2`, where it is defined" in record["remediation"]
        assert record["issue"].endswith("`pkg/old/r.py:2` defines, a file `data/skill-brief.yaml` scopes out "
                                        "(`excluded.outsideScope`)")

    def test_a_fabricated_name_stays_critical_whatever_its_defined_at(self):
        stale = [{"name": "ghost", "fabricated": True, "source": "src/a.py:3", "defined_at": "src/b.py:1"}]
        records = mod.from_coverage({"branch": "enumerated", "missing": [], "stale": ["ghost"]},
                                    surface=self.EXCLUDED_SURFACE, stale=stale)
        assert brief(records) == [("Critical", "fabricated-signature", "Fabricated signature: ghost", "src/a.py:3",
                                   "ghost")]

    @pytest.mark.parametrize("kind", ["fabricated", "stale-documentation", "scoped-out", "documented-extra"])
    @pytest.mark.parametrize("written, subject", [
        (None, "the skill"),
        ("", "the skill"),
        ("SKILL.md", "`SKILL.md:3`"),
        ("references/connectors.md", "`references/connectors.md:3`"),
    ], ids=["no-skill-dir", "written-nowhere", "in-skill-md", "in-references"])
    def test_no_stale_names_issue_opens_with_a_bare_skill_md(self, tmp_path: Path, kind: str, written: str | None,
                                                             subject: str):
        """#923: every kind of stale-name gap opens its issue with the line that documents the name, else with
        the skill, whatever its Source."""
        category, name, tail, inputs = {
            "fabricated": ("fabricated-signature", "ghost", "the cited file does not define",
                           {"stale": [{"name": "ghost", "fabricated": True, "source": "src/a.py:3"}]}),
            "stale-documentation": ("stale-documentation", "nowhere", "the enumerated source API surface lacks", {}),
            "scoped-out": ("stale-documentation", "Rescoped", "scopes out (`excluded.outsideScope`)",
                           {"surface": self.BRIEFED_SURFACE, "stale": self.RESCOPED}),
            "documented-extra": ("observation", "Task", "the source still declares",
                                 {"surface": self.EXCLUDED_SURFACE, "stale": [
                                     {"name": "Task", "fabricated": False, "source": None,
                                      "defined_at": "pkg/tasks/task.py:4"}]}),
        }[kind]
        skill = None
        if written is not None:
            skill = tmp_path / "skill"
            (skill / "references").mkdir(parents=True)
            (skill / "SKILL.md").write_bytes(b"# demo\n\nSee references.\n")
            if written:
                (skill / written).write_bytes(f"# Doc\n\n`{name}(x)` is documented here.\n".encode("utf-8"))
        [record] = mod.from_coverage({"branch": "enumerated", "missing": [], "stale": [name]},
                                     skill_dir=str(skill) if skill else None, **inputs)
        assert record["category"] == category and record["issue"].endswith(tail), record
        assert record["issue"].startswith(f"{subject} documents `{name}`, which "), record
        assert not record["issue"].startswith("SKILL.md documents")

    # #922: the line that documents a stale name is the first that writes it as an export. oms-uitripled's
    # shape: the frontmatter, a shell line and a heading write `add` as a word; the reference declares it.
    UITRIPLED_SKILL = ("---\nname: demo\ndescription: Use `add` to install, as \"npx shadcn@latest add x\" does.\n"
                       "---\n# demo\n\n```bash\nnpx uitripled add x\n```\n\n## CLI (`uitripled add`)\n\n"
                       "Run `uitripled add` to install.\n")
    UITRIPLED_CATALOG = ("# Catalog\n\n## Standalone CLI internals (`uitripled add`)\n\n```ts\n"
                         "export async function add(name: string): Promise<void>\n```\n")
    SEE = "# demo\n\nSee references.\n"
    # #966: oms-cocoindex's shape, names written only as quoted items of a fenced `__all__` list
    EXPORT_LIST = ("# Connectors\n\n```python\n__all__ = [\n    \"ColumnDef\", \"ManagedConnection\",\n"
                   "    'connect',\n]\n```\n")

    @staticmethod
    def _skill_package(root: Path, files: dict[str, str | bytes]) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        for rel, text in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))
        return root

    @pytest.mark.parametrize("files, name, expected", [
        ({"SKILL.md": UITRIPLED_SKILL, "references/catalog.md": UITRIPLED_CATALOG}, "add", "references/catalog.md:6"),
        # the floor first: a whole-span heading of a top-level reference before SKILL.md's unheaded fence
        ({"SKILL.md": "# demo\n\n```python\ndef get():\n    pass\n```\n",
          "references/api.md": "# API\n\n### `get(key)`\n\nReads a key.\n"}, "get", "references/api.md:3"),
        # a heading of an earlier file before an unheaded fenced declaration (#972)
        ({"SKILL.md": "# demo\n\n## get\n\nReads a key.\n",
          "references/a.md": "# A\n\n```python\ndef get():\n    pass\n```\n"}, "get", "SKILL.md:3"),
        # a nested reference: a fenced declaration, or a row of a table whose first column names exports
        ({"SKILL.md": SEE, "references/integrations/x.md": "# X\n\n```ts\nexport function get(key: string) {}\n```\n"},
         "get", "references/integrations/x.md:4"),
        ({"SKILL.md": SEE,
          "references/integrations/x.md": "# X\n\n| Function | Purpose |\n| --- | --- |\n| `get(key)` | Reads. |\n"},
         "get", "references/integrations/x.md:5"),
        # in one tier the first file wins, then the lowest line: a plain first cell before a heading's span
        ({"SKILL.md": "# demo\n\nSee below.\n\n## get\n", "references/a.md": "## get\n"}, "get", "SKILL.md:5"),
        ({"SKILL.md": "# demo\n\n| Function | Purpose |\n| --- | --- |\n| get | Reads. |\n\n## Reading with `get`\n"},
         "get", "SKILL.md:5"),
        # no export-shaped line: a paragraph, a list item, a table cell or a paragraph's next line whose code
        # span is the name, or the name and its parameters
        ({"SKILL.md": "# demo\n\nThe store has `get`.\n"}, "get", "SKILL.md:3"),
        ({"SKILL.md": "# demo\n\nThe calls:\n\n- Call `get(key)` to read.\n"}, "get", "SKILL.md:5"),
        ({"SKILL.md": "# demo\n\n| Option | Meaning |\n| --- | --- |\n| `cache` | read by `get` |\n"}, "get",
         "SKILL.md:5"),
        ({"SKILL.md": "# demo\n\nThe store reads a key\nwith `get(key)`.\n"}, "get", "SKILL.md:4"),
        # an export-shaped line of a later file before a code span of an earlier one
        ({"SKILL.md": "# demo\n\n`get(key)` reads.\n", "references/api.md": "# API\n\n## get\n"}, "get",
         "references/api.md:3"),
        # a table whose header's first cell does not name exports: its first cell is a code span, not a heading
        ({"SKILL.md": "# demo\n\n| Option | Meaning |\n| --- | --- |\n| `get` | an option |\n",
          "references/api.md": "# API\n\n## get\n"}, "get", "references/api.md:3"),
        # a Svelte block's `export let` is a component prop, not a declaration
        ({"SKILL.md": "# demo\n\n```svelte\nexport let get = 1;\n```\n",
          "references/api.md": "# API\n\n`get` reads.\n"}, "get", "references/api.md:3"),
        # a name with two floor origins is cited at the first
        ({"SKILL.md": "# demo\n\n### `get(key)`\n", "references/api.md": "# API\n\n### `get(key)`\n"}, "get",
         "SKILL.md:3"),
        # a dotted name's code spans: the lowest line wins, a paragraph before a later heading
        ({"SKILL.md": "# demo\n\nCall `Task.run(x)`.\n\n## `Task.run`\n"}, "Task.run", "SKILL.md:3"),
        # #966: a name written only as a quoted item of a fenced `__all__` list, double or single quotes
        ({"SKILL.md": SEE, "references/connectors.md": EXPORT_LIST}, "ManagedConnection",
         "references/connectors.md:5"),
        ({"SKILL.md": SEE, "references/connectors.md": EXPORT_LIST}, "connect", "references/connectors.md:6"),
        # a quoted string after an apostrophe, and in an untagged, a Svelte and a shell fence
        ({"SKILL.md": SEE, "references/a.md": "# A\n\n```python\n# don't use 'add' here\n```\n"}, "add",
         "references/a.md:4"),
        ({"SKILL.md": SEE, "references/a.md": "# A\n\n```\nnames = ['add']\n```\n"}, "add", "references/a.md:4"),
        ({"SKILL.md": SEE, "references/a.md": "# A\n\n```svelte\nconst names = ['add'];\n```\n"}, "add",
         "references/a.md:4"),
        ({"SKILL.md": SEE, "references/a.md": "# A\n\n```bash\nnpx uitripled \"add\" x\n```\n"}, "add",
         "references/a.md:4"),
        # #972: a connector author's own def in an unheaded fence, the export's heading in a reference
        ({"SKILL.md": ("# demo\n\n```python\n_P = register_provider(\"my_db\", Handler())\n\n"
                       "async def mount_table_target(db_key, *, table_name):\n    pass\n```\n"),
          "references/target-state.md": "# Target state\n\n## mount_table_target\n\nMounts a table.\n"},
         "mount_table_target", "references/target-state.md:3"),
        # #972: in one file, a later code span before an earlier fenced def
        ({"SKILL.md": SEE,
          "references/target-state.md": ("# Target state\n\n```python\nasync def mount_table_target(db_key):\n"
                                         "    pass\n```\n\n"
                                         "Connectors expose helpers like `mount_table_target(...)`.\n")},
         "mount_table_target", "references/target-state.md:8"),
        # a fenced declaration of a later file before a quoted string of an earlier one
        ({"SKILL.md": "# demo\n\n```python\n__all__ = [\"get\"]\n```\n",
          "references/a.md": "# A\n\n```python\ndef get():\n    pass\n```\n"}, "get", "references/a.md:4"),
        # oms-uitripled's `add`: the call in a list item after the export's declaration
        ({"SKILL.md": UITRIPLED_SKILL,
          "references/catalog.md": UITRIPLED_CATALOG + "\n- `add(name)` installs an item.\n"}, "add",
         "references/catalog.md:9"),
    ], ids=["issue-922", "floor-first", "heading-before-fence", "nested-fence", "nested-table-row", "first-file",
            "lowest-line", "paragraph-span", "list-item-call", "table-cell-span", "continuation-line",
            "export-shaped-before-span", "option-table-first-cell", "svelte-prop", "two-floor-origins",
            "dotted-lowest-line", "export-list-item", "export-list-single-quote", "quoted-after-apostrophe",
            "quoted-untagged-fence", "quoted-svelte-fence", "quoted-bash-fence", "connector-author-def",
            "span-after-def", "declaration-before-quoted", "uitripled-call-after-declaration"])
    def test_the_documenting_line_writes_the_name_as_an_export(self, tmp_path: Path, files: dict, name: str,
                                                               expected: str):
        skill = self._skill_package(tmp_path / "skill", files)
        assert mod._documenting_line(skill, name) == expected
        [record] = mod.from_coverage({"branch": "enumerated", "missing": [], "stale": [name]}, skill_dir=str(skill))
        assert (record["source"], record["issue"]) == (
            expected, f"`{expected}` documents `{name}`, which the enumerated source API surface lacks")
        assert record["remediation"].endswith(f"documentation at {expected}: the enumerated source surface does not "
                                              "export it.")

    def test_the_append_cli_cites_the_declaration_not_the_frontmatter(self, ledger: Path, tmp_path: Path):
        """#922 through `append --from coverage --skill-dir`: oms-uitripled's `add` was cited at its frontmatter;
        without --skill-dir the skill documents it, as before."""
        skill = self._skill_package(tmp_path / "skill", {"SKILL.md": self.UITRIPLED_SKILL,
                                                         "references/catalog.md": self.UITRIPLED_CATALOG})
        coverage = write_json(tmp_path / "coverage.json", {"branch": "enumerated", "missing": [], "stale": ["add"]})
        proc = from_file(ledger, "coverage-check", "coverage", coverage, skill_dir=skill)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        [record] = ledger_records(ledger)
        assert brief([record]) == [("Medium", "stale-documentation", "Stale documentation: add",
                                    "references/catalog.md:6", "add")]
        assert record["issue"] == ("`references/catalog.md:6` documents `add`, which the enumerated source API "
                                   "surface lacks")
        assert record["remediation"] == ("Check `add` against the source and update or remove its documentation at "
                                         "references/catalog.md:6: the enumerated source surface does not export it.")
        other = tmp_path / "2.0.0" / f"test-findings-{RUN_ID}.json"
        proc = from_file(other, "coverage-check", "coverage", coverage)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        [record] = ledger_records(other)
        assert (record["source"], record["issue"]) == (
            "SKILL.md", "the skill documents `add`, which the enumerated source API surface lacks")

    def test_a_name_written_only_as_a_word_documents_nothing(self, tmp_path: Path):
        """The frontmatter, a bare word, a code span that holds the name among other words or before a space, a
        heading that holds a span with the name among other words, a span in an HTML comment, a fence in one (its
        declaration or quoted string), a data block (json, yaml), an unquoted shell line, a quoted string in prose and
        a fenced quoted string that holds other words too never document `add`: the skill does, at `SKILL.md`."""
        skill = self._skill_package(tmp_path / "skill", {"SKILL.md": (
            "---\nname: demo\ndescription: Use `add` to install, as \"npx shadcn@latest add x\" does; "
            "pass \"add\" to it.\n---\n"
            "# demo\n\nRun add to install, or `uitripled add`. Pass \"add\" to it.\n\n## CLI (`uitripled add`)\n\n"
            "- `addAll()` and `add (x)` are other calls.\n\n<!-- `add` -->\n\n"
            "<!--\n```ts\nexport function add() {}\nconst names = [\"add\"];\n```\n-->\n\n"
            "```json\n{\"add\": 1}\n```\n\n```yaml\nnames: ['add']\n```\n\n"
            "```bash\nnpx uitripled add x\n```\n\n```python\nprint(\"add x\")\n```\n")})
        assert mod._documenting_line(skill, "add") is None
        [record] = mod.from_coverage({"branch": "enumerated", "missing": [], "stale": ["add"]}, skill_dir=str(skill))
        assert (record["source"], record["issue"]) == (
            "SKILL.md", "the skill documents `add`, which the enumerated source API surface lacks")
        assert record["remediation"] == ("Check `add` against the source and update or remove its documentation at "
                                         "SKILL.md: the enumerated source surface does not export it.")

    def test_an_input_that_cannot_be_read_is_skipped(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """No SKILL.md, or a reference that is not UTF-8, leaves the floor out and the other tiers answer; a file
        that cannot be read leaves those out and the floor answers. Nothing raises."""
        coverage = mod._sibling("load-coverage-inputs.py")
        fence = "```python\ndef put():\n    pass\n```\n"
        skill = self._skill_package(tmp_path / "no-skill-md", {"references/api.md": "# API\n\n" + fence})
        assert mod._documenting_line(skill, "put") == "references/api.md:4"
        [record] = mod.from_coverage({"branch": "enumerated", "missing": [], "stale": ["put"]}, skill_dir=str(skill))
        assert record["source"] == "references/api.md:4"

        skill = self._skill_package(tmp_path / "not-utf-8", {"SKILL.md": "# demo\n\n## Reading with `get`\n",
                                                              "references/bad.md": b"# Bad \xff\n\n" + fence.encode()})
        with pytest.raises(coverage.InputError):
            coverage.floor(str(skill))
        assert (mod._documenting_line(skill, "get"), mod._documenting_line(skill, "put")) == (
            "SKILL.md:3", "references/bad.md:4")

        def unreadable(root):
            raise PermissionError(13, "Permission denied", str(root))

        skill = self._skill_package(tmp_path / "unreadable", {
            "SKILL.md": "# demo\n\n### `get(key)`\n\n" + fence + "\n```python\n__all__ = [\"keep\"]\n```\n"})
        monkeypatch.setattr(mod._sibling("locate-export-segments.py"), "skill_files", unreadable)
        assert (mod._documenting_line(skill, "get"), mod._documenting_line(skill, "put")) == ("SKILL.md:3", None)
        assert mod._documenting_line(skill, "keep") is None

    def test_the_floor_is_read_once_per_call(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """The lines that document the stale names are read once, not once a name; without the skill package or
        a stale name, never."""
        coverage = mod._sibling("load-coverage-inputs.py")
        calls: list[str] = []
        real = coverage.floor

        def counted(skill_dir: str) -> dict:
            calls.append(skill_dir)
            return real(skill_dir)

        monkeypatch.setattr(coverage, "floor", counted)
        skill = self._skill_package(tmp_path / "skill", {
            "SKILL.md": "# demo\n\n### `get(key)`\n\n```python\ndef put():\n    pass\n```\n"})
        records = mod.from_coverage({"branch": "enumerated", "missing": [], "stale": ["get", "put", "nowhere"]},
                                    skill_dir=str(skill))
        assert [r["source"] for r in records] == ["SKILL.md:3", "SKILL.md:6", "SKILL.md"]
        assert calls == [str(skill)]
        mod.from_coverage({"branch": "enumerated", "missing": [], "stale": ["get"]})
        mod.from_coverage({"branch": "enumerated", "missing": [], "stale": []}, skill_dir=str(skill))
        assert calls == [str(skill)]

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

    # #791, #792: reconcile-coverage.py's scalar result over a named surface set lists its missing and stale names.
    SCALAR_OVER_SET = {"branch": "scalar", "denominator": 5, "documented": 3, "missing": [], "missingCount": 0,
                       "stale": ["phantomOne"], "staleCount": 1, "staleApplicable": True,
                       "numeratorSource": "surface", "surfaceSet": "tier_a_include"}

    def test_a_scalar_stale_name_is_classified_as_the_barrel_branchs(self, ledger: Path, tmp_path: Path):
        coverage = write_json(tmp_path / "coverage.json", self.SCALAR_OVER_SET)
        stale = write_json(tmp_path / "stale.json", [{"name": "phantomOne", "fabricated": True,
                                                       "source": "src/phantom.ts:3", "reason": "not-defined"}])
        proc = from_file(ledger, "coverage-check", "coverage", coverage, stale=stale)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert brief(ledger_records(ledger)) == [
            ("Critical", "fabricated-signature", "Fabricated signature: phantomOne", "src/phantom.ts:3", "phantomOne")]
        other = tmp_path / "2.0.0" / f"test-findings-{RUN_ID}.json"
        proc = from_file(other, "coverage-check", "coverage", coverage)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert brief(ledger_records(other)) == [
            ("Medium", "stale-documentation", "Stale documentation: phantomOne", "SKILL.md", "phantomOne")]

    def test_a_scalar_missing_name_is_one_gap_at_its_surface_file(self):
        cov = self.SCALAR_OVER_SET | {"missing": ["delta"], "missingCount": 1, "stale": [], "staleCount": 0}
        surface = {"exports": [{"name": "delta", "kind": "function", "file": "src/index.ts", "line": 4}]}
        records = mod.from_coverage(cov, surface=surface, metadata="pkg/metadata.json")
        assert brief(records) == [("Medium", "missing-export", "Missing export: delta", "src/index.ts:4", "delta")]

    def test_a_scalar_lookup_over_all_keeps_the_count_gap_beside_its_stale_names(self):
        """Over `all` (or a set the surface does not trust) the lookup counts: the count gap, or the verified
        numerator's absent names, and the stale names still classified against `all`."""
        cov = self.SCALAR_OVER_SET | {"missingCount": 2, "numeratorSource": "lookup"}
        cov.pop("surfaceSet")
        records = mod.from_coverage(cov, metadata="pkg/metadata.json")
        assert brief(records) == [
            ("Medium", "missing-export", "2 of 5 exports not documented", "pkg/metadata.json", None),
            ("Medium", "stale-documentation", "Stale documentation: phantomOne", "SKILL.md", "phantomOne")]
        verified = cov | {"numeratorSource": "verified"}
        records = mod.from_coverage(verified, numerator={"inflated": True, "absent": ["alpha"]},
                                    metadata="pkg/metadata.json")
        assert brief(records) == [
            ("Medium", "missing-export", "Missing export: alpha", "pkg/metadata.json", "alpha"),
            ("Medium", "stale-documentation", "Stale documentation: phantomOne", "SKILL.md", "phantomOne")]

    @pytest.mark.parametrize("missing, missing_count, residual", [
        (["delta"], 3, ["2 of 5 exports not documented beyond the tier_a_include set"]),
        (["delta", "epsilon"], 1, []),
        (["delta"], 1, []),
    ], ids=["count-above-the-names", "count-below-the-names", "count-equal"])
    def test_a_counted_set_adds_a_residual_count_gap_only_above_its_names(self, missing, missing_count, residual):
        """A stored count larger than the set leaves exports no name lists: one count gap for the rest. A set
        larger than the stored count lists more names than the count: no residual."""
        cov = self.SCALAR_OVER_SET | {"missing": missing, "missingCount": missing_count, "stale": [],
                                      "surfaceSetSize": 3}
        records = mod.from_coverage(cov, metadata="pkg/metadata.json")
        assert [r["title"] for r in records] == [f"Missing export: {n}" for n in missing] + residual
        if residual:
            [gap] = records[len(missing):]
            assert (gap["severity"], gap["category"], gap["source"]) == ("Medium", "missing-export",
                                                                         "pkg/metadata.json")
            assert "beyond the 3 names of the `tier_a_include` set" in gap["remediation"]
            assert "the other 2 are exports the count holds beyond the set's names" in gap["issue"]

    @pytest.mark.parametrize("clause, summarized", [("stratified-scope", True), ("multi-entry", True),
                                                    ("specific-modules", False)])
    def test_a_counted_set_over_an_inflated_union_takes_the_barrel_branchs_summary(self, clause, summarized):
        """#795's gate is the surface's, whichever branch counts the set: a counted `scope.include` set the
        inflation guard measured, on a clause a tier A list corrects, is one summary gap at the brief in place of
        a gap per name, and the residual count gap still covers the names the set does not list."""
        surface = self.INFLATED_SURFACE | {"denominator": {"clause": clause, "branch": "scalar",
                                                           "surfaceSet": "scope.include", "setCounted": True}}
        cov = self.SCALAR_OVER_SET | {"missing": ["fetchData", "Options"], "missingCount": 3, "stale": [],
                                      "surfaceSet": "scope.include", "surfaceSetSize": 4}
        records = mod.from_coverage(cov, surface=surface, signatures={"missingTypes": ["Options"]},
                                    metadata="pkg/metadata.json")
        if summarized:
            assert [(r["category"], r["title"], r["source"]) for r in records] == [
                ("denominator-inflation", "undocumented names in the inflated scope.include union",
                 "data/skill-brief.yaml"),
                ("missing-export", "1 of 5 exports not documented beyond the scope.include set", "pkg/metadata.json")]
        else:
            assert [r["title"] for r in records] == ["Missing export: fetchData", "Missing type: Options",
                                                     "1 of 5 exports not documented beyond the scope.include set"]

    def test_a_scalar_stale_name_the_brief_scopes_out_points_at_the_brief(self):
        """#796's wording holds on the scalar branch too."""
        surface = self.BRIEFED_SURFACE | {"excluded": {"outsideScope": [
            {"name": "Rescoped", "file": "pkg/old/r.py", "line": 2, "entry": "pkg/__init__.py",
             "excludeGlob": "pkg/old/**", "outsideInclude": False}], "nestedEntries": []}}
        [record] = mod.from_coverage(self.SCALAR_OVER_SET | {"stale": ["Rescoped"]}, surface=surface,
                                     stale=self.RESCOPED)
        assert brief([record]) == [("Medium", "stale-documentation", "Stale documentation: Rescoped", "SKILL.md",
                                    "Rescoped")]
        assert record["remediation"].startswith(
            "Decide whether `Rescoped` belongs on the surface: `data/skill-brief.yaml` scopes out `pkg/old/r.py:2`")

    def test_a_counted_set_records_through_the_coverage_call(self, ledger: Path, tmp_path: Path):
        """§5b's coverage call on a scalar run: --surface gives each missing name its file, --signatures turns a
        missing type into `missing-type`, and a classify-stale item the source still declares is a documented
        extra."""
        cov = self.SCALAR_OVER_SET | {"missing": ["delta", "Options"], "missingCount": 2,
                                      "stale": ["phantomOne", "Task"], "staleCount": 2}
        surface = {"exports": [{"name": "delta", "kind": "function", "file": "src/index.ts", "line": 4},
                               {"name": "Options", "kind": "interface", "file": "src/types.ts", "line": 2}],
                   "extraction": {"status": "ok"}, "excluded": {"outsideScope": [], "nestedEntries": []}}
        stale = [{"name": "phantomOne", "fabricated": True, "source": "src/phantom.ts:3", "reason": "not-defined"},
                 {"name": "Task", "fabricated": False, "source": None, "defined_at": "src/tasks/task.ts:12",
                  "reason": "no-entry"}]
        proc = from_file(ledger, "coverage-check", "coverage", write_json(tmp_path / "coverage.json", cov),
                         surface=write_json(tmp_path / "surface.json", surface),
                         signatures=write_json(tmp_path / "signatures.json",
                                               {"missingTypes": ["Options"], "comparedNames": []}),
                         stale=write_json(tmp_path / "stale.json", stale), metadata="pkg/metadata.json")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert brief(ledger_records(ledger)) == [
            ("Medium", "missing-export", "Missing export: delta", "src/index.ts:4", "delta"),
            ("Medium", "missing-type", "Missing type: Options", "src/types.ts:2", "Options"),
            ("Critical", "fabricated-signature", "Fabricated signature: phantomOne", "src/phantom.ts:3", "phantomOne"),
            ("Info", "observation", "Documented extra: Task", "src/tasks/task.ts:12", "Task"),
        ]

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
        # #788: on an umbrella barrel both gaps still name the brief's tier A list, never a stored count set by hand
        surface["guards"]["umbrella"]["umbrella"] = True
        deflation, inflation = (r["remediation"] for r in mod.from_guards(surface, "other/metadata.json"))
        assert deflation == inflation == (
            "Add `scope.tier_a_include` to `data/skill-brief.yaml`, listing the files that define the authored names "
            "rather than the root barrel, an umbrella of re-exports: the `scope.include` union is itself inflated, "
            "so neither it nor the smaller stored count measures the authored surface. Then re-run Create Skill to "
            "recount `stats.effective_denominator` in `other/metadata.json` from the tier A set: it stores that "
            "count when `effective_denominator_decision.store` holds and the brief's `scope.notes` documents the "
            "stratification, and otherwise drops the stored count.")
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
        # #788: both guards fire, so both name the one fix, the brief's tier A list
        assert deflation["remediation"] == inflation["remediation"]
        assert inflation["remediation"].startswith(
            "Edit `scope.tier_a_include` in `data/skill-brief.yaml` so its globs list the files that define the "
            "authored names: the `scope.include` union is itself inflated")
        # Without the key (a surface from before #695) the text is the one a brief with no tier A glob gets.
        del surface["guards"]["staleScope"]["unmatchedTierAInclude"]
        assert [r["issue"].endswith("and the brief has no `scope.tier_a_include`")
                for r in mod.from_guards(surface)] == [True, True]

    @pytest.mark.parametrize("tier_a, unmatched, clause, verb", [
        ([], [], "the brief has no `scope.tier_a_include`", "Add"),
        (["src/old/**"], ["src/old/**"], "no `scope.tier_a_include` glob in the brief matches a file", "Edit"),
        (["src/old/**", "src/util/index.ts"], ["src/old/**"],
         "no `scope.tier_a_include` glob in the brief counts a public name", "Edit"),
        (["src/vendor/**"], [], "no `scope.tier_a_include` glob in the brief counts a public name", "Edit"),
    ], ids=["no-glob", "every-glob-stale", "stale-and-nameless", "excluded-only"])
    def test_the_guards_say_which_tier_a_globs_count_no_name(self, tier_a, unmatched, clause, verb):
        """#712: `guards.tierAInclude` (the brief's tier A globs) tells a brief with none from one whose globs
        all match no file and from one whose globs match files that define no public name. Titles stay."""
        surface = {"inputs": {"metadata": "pkg/metadata.json", "brief": "data/skill-brief.yaml"}, "guards": {
            "deflation": {"fires": True, "rederived": 40, "pct": 60.0, "effectiveDenominator": 25},
            "inflation": {"fires": True, "scopeIncludeUnion": 50, "pct": 100.0, "provenanceEntries": 25},
            "staleScope": {"fires": bool(unmatched), "unmatchedInclude": [], "unmatchedTierAInclude": unmatched,
                           "restored": []},
            "tierAInclude": tier_a, "umbrella": {"umbrella": False}}}
        deflation, inflation, *stale = mod.from_guards(surface)
        assert [deflation["title"], inflation["title"]] == [
            "denominator deflation: effective_denominator below source public surface without tier_a_include",
            "denominator inflation: coarse scope.include union exceeds authored surface"]
        assert deflation["issue"] == (
            f"the re-derived surface counts 40 exports, 60.0% above `stats.effective_denominator` (25), and {clause}")
        assert inflation["issue"].endswith(f", and {clause}")
        assert inflation["remediation"].startswith(f"{verb} `scope.tier_a_include`")
        assert deflation["remediation"] == inflation["remediation"], "#788: both guards name one fix"
        assert len(stale) == (1 if unmatched else 0)

    def test_a_stored_zero_reads_as_a_count_against_zero(self):
        """#712: the deflation guard fires on a stored `stats.effective_denominator` of 0 with no percentage
        (`pct` null), so the issue gives the count against 0, never `None%`."""
        surface = {"inputs": {"metadata": "pkg/metadata.json"}, "guards": {
            "deflation": {"applicable": True, "fires": True, "rederived": 62, "pct": None, "effectiveDenominator": 0},
            "staleScope": {"fires": False, "unmatchedTierAInclude": ["cognee/modules/observability/trace_context/**"]},
            "tierAInclude": ["cognee/modules/observability/trace_context/**"]}}
        [record] = mod.from_guards(surface)
        assert (record["severity"], record["category"]) == ("Medium", "metadata-drift")
        assert record["issue"] == (
            "the re-derived surface counts 62 exports against a `stats.effective_denominator` of 0, and no "
            "`scope.tier_a_include` glob in the brief matches a file")
        assert "None" not in record["issue"]
        # a 0 measures no tier, so the fix counts it again instead of setting it to the re-derived surface
        assert record["remediation"] == (
            "Edit `scope.tier_a_include` in the brief so its globs match the files that define the authored tier, "
            "then re-run Create Skill so `stats.effective_denominator` in `pkg/metadata.json` is counted again.")
        del surface["guards"]["staleScope"], surface["guards"]["tierAInclude"]
        [record] = mod.from_guards(surface)
        assert record["remediation"] == (
            "Check `scope.include` in the brief, then re-run Create Skill so `stats.effective_denominator` in "
            "`pkg/metadata.json` is counted again.")

    @pytest.mark.parametrize("umbrella", [True, False], ids=["umbrella", "no-umbrella"])
    @pytest.mark.parametrize("tier_a, verb", [([], "Add"), (["src/old/**"], "Edit")], ids=["no-tier-a", "stale-tier-a"])
    def test_both_guards_name_the_brief_tier_a_list(self, umbrella, tier_a, verb):
        """#788: deflation and inflation fire on the same `scope.include` union, and their fixes disagreed: raise
        the stored count to the union the other calls coarse, or, on an umbrella barrel, set it by hand, which
        Update Skill's recount drops. Both now name one fix, the brief's tier A list, and say the union is itself
        inflated; on an umbrella barrel the list names the defining files, not the barrel."""
        surface = {"inputs": {"metadata": "pkg/metadata.json", "brief": "data/skill-brief.yaml"}, "guards": {
            "deflation": {"applicable": True, "basis": "scope.include", "fires": True, "rederived": 40, "pct": 60.0,
                          "effectiveDenominator": 25},
            "inflation": {"fires": True, "scopeIncludeUnion": 50, "pct": 100.0, "provenanceEntries": 25},
            "staleScope": {"fires": False, "unmatchedTierAInclude": tier_a},
            "tierAInclude": tier_a, "umbrella": {"umbrella": umbrella}}}
        deflation, inflation = mod.from_guards(surface)
        assert [deflation["category"], inflation["category"]] == ["metadata-drift", "denominator-inflation"]
        for record in (deflation, inflation):
            assert "Set `stats.effective_denominator`" not in record["remediation"]
            assert record["remediation"].startswith(f"{verb} `scope.tier_a_include`")
            assert "the files that define the authored names" in record["remediation"]
            assert "the `scope.include` union is itself inflated" in record["remediation"]
            assert ("rather than the root barrel, an umbrella of re-exports" in record["remediation"]) is umbrella
        assert deflation["remediation"] == inflation["remediation"]

    @pytest.mark.parametrize("guards", [
        {"deflation": {"fires": True, "pct": 60.0, "rederived": 40, "effectiveDenominator": 25}},
        {"deflation": {"fires": True, "pct": None, "rederived": 40, "effectiveDenominator": 0}},
        {"inflation": {"fires": True, "scopeIncludeUnion": 50, "pct": 100.0, "provenanceEntries": 25}},
        {"deflation": {"fires": True, "basis": "tier_a_include", "pct": 50.0, "rederived": 3,
                       "effectiveDenominator": 2}},
        {"deflation": {"fires": True, "pct": 60.0, "rederived": 40, "effectiveDenominator": 25},
         "inflation": {"fires": True, "scopeIncludeUnion": 50, "pct": 100.0, "provenanceEntries": 25}},
    ], ids=["deflation", "stored-zero", "inflation", "tier-a-drift", "both"])
    @pytest.mark.parametrize("umbrella", [True, False], ids=["umbrella", "no-umbrella"])
    @pytest.mark.parametrize("tier_a", [[], ["src/old/**"]], ids=["no-tier-a", "tier-a"])
    def test_no_remediation_sets_the_stored_count_by_hand(self, guards, umbrella, tier_a):
        """#788, #803: Update Skill's recount drops a `stats.effective_denominator` set by hand, so no guard's fix,
        in any branch, asks a person to set it."""
        surface = {"inputs": {"metadata": "pkg/metadata.json"},
                   "guards": {**guards, "tierAInclude": tier_a, "umbrella": {"umbrella": umbrella}}}
        records = mod.from_guards(surface)
        assert records
        for record in records:
            assert not re.search(r"\b[Ss]et `stats\.effective_denominator`", record["remediation"]), record

    STORES = ("when `effective_denominator_decision.store` holds and the brief's `scope.notes` documents the "
              "stratification, and otherwise drops the stored count")

    @pytest.mark.parametrize("denominator, extraction, until", [
        ({"branch": "barrel", "surfaceSet": "tier_a_include"}, None,
         " Until then Test Skill counts the `tier_a_include` set as the denominator."),
        ({"branch": "barrel", "surfaceSet": "scope.include"}, None,
         " Until then Test Skill counts the `scope.include` set as the denominator."),
        ({"branch": "scalar", "surfaceSet": "tier_a_include"}, {"status": "incomplete"},
         " Until then the stored count stays the denominator: the extraction is incomplete, so the tier A set can "
         "miss names."),
        (None, None, ""),
    ], ids=["tier-a-rung", "specific-modules", "incomplete-below", "no-denominator"])
    @pytest.mark.parametrize("pct, stored, words", [(50.0, 2, "50.0% above"), (-57.14, 7, "57.14% below")],
                             ids=["above", "below"])
    def test_a_tier_a_basis_fire_is_denominator_drift_to_recount(self, pct, stored, words, denominator, extraction,
                                                                 until):
        """#813: a stored count the brief's tier A set disagrees with beyond the threshold, either way, is stale:
        a Medium `metadata-drift` gap with its own title, giving the tier A count, the pct and the stored count,
        that asks Create Skill to recount (Update Skill may write no metadata.json) under the rule it stores the
        count by, and names what `denominator` counts until then."""
        surface = {"inputs": {"metadata": "pkg/metadata.json", "brief": "data/skill-brief.yaml"}, "guards": {
            "deflation": {"applicable": True, "basis": "tier_a_include", "effectiveDenominator": stored,
                          "rederived": 3, "pct": pct, "fires": True},
            "inflation": {"applicable": False, "fires": False}, "tierAInclude": ["src/index.ts"],
            "umbrella": {"umbrella": False}}, "denominator": denominator, "extraction": extraction}
        [record] = mod.from_guards(surface)
        assert brief([record]) == [
            ("Medium", "metadata-drift",
             "denominator drift: effective_denominator disagrees with the brief's tier_a_include set",
             "pkg/metadata.json", None)]
        assert record["issue"] == (
            f"the brief's `scope.tier_a_include` set counts 3 exports, {words} `stats.effective_denominator` "
            f"({stored})")
        assert record["remediation"] == (
            "Re-run Create Skill to recount `stats.effective_denominator` in `pkg/metadata.json`: it stores the "
            f"runner's count of the brief's `scope.tier_a_include` set {self.STORES}.{until}")
        assert "Update Skill" not in record["remediation"]

    @pytest.mark.parametrize("tier_a, fix", [
        ([], "or add `scope.tier_a_include` to the brief to name the authored tier the smaller count measures."),
        (["src/old/**"], "or edit `scope.tier_a_include` in the brief so its globs match the files of the authored "
                         "tier the smaller count measures."),
    ], ids=["no-tier-a-list", "tier-a-list"])
    def test_a_deflation_alone_asks_create_skill_to_recount_or_the_brief_to_name_its_tier(self, tier_a, fix):
        """#788: deflation on the `scope.include` basis with inflation off: recount through Create Skill, or name
        the authored tier in the brief, never a stored count set by hand."""
        surface = {"inputs": {"metadata": "pkg/metadata.json", "brief": "data/skill-brief.yaml"}, "guards": {
            "deflation": {"applicable": True, "basis": "scope.include", "fires": True, "rederived": 40, "pct": 60.0,
                          "effectiveDenominator": 25},
            "inflation": {"applicable": True, "fires": False}, "tierAInclude": tier_a,
            "umbrella": {"umbrella": True}}}
        [record] = mod.from_guards(surface)
        assert record["title"] == (
            "denominator deflation: effective_denominator below source public surface without tier_a_include")
        assert record["remediation"] == (
            "Re-run Create Skill to recount `stats.effective_denominator` in `pkg/metadata.json` from the public "
            f"surface the source re-derives (it stores that count {self.STORES}), {fix}")

    @pytest.mark.parametrize("umbrella", [True, False], ids=["umbrella", "no-umbrella"])
    @pytest.mark.parametrize("tier_a, fix", [
        ([], "Add `scope.tier_a_include` to `data/skill-brief.yaml`, listing the files of the authored "
             "surface{umbrella}, so the denominator counts it instead of the coarse `scope.include` union."),
        (["src/old/**"], "Edit `scope.tier_a_include` in `data/skill-brief.yaml` so its globs match the files of "
                         "the authored surface{umbrella}: the denominator then counts it instead of the coarse "
                         "`scope.include` union."),
    ], ids=["no-tier-a-list", "tier-a-list"])
    def test_an_inflation_alone_names_the_umbrella_only_on_an_umbrella_barrel(self, tier_a, fix, umbrella):
        """#788: inflation with deflation off names the files of the authored surface, rather than the root
        barrel exactly when that barrel is an umbrella of re-exports."""
        surface = {"inputs": {"metadata": "pkg/metadata.json", "brief": "data/skill-brief.yaml"}, "guards": {
            "deflation": {"applicable": True, "basis": "scope.include", "fires": False},
            "inflation": {"fires": True, "scopeIncludeUnion": 50, "pct": 100.0, "provenanceEntries": 25},
            "tierAInclude": tier_a, "umbrella": {"umbrella": umbrella}}}
        [record] = mod.from_guards(surface)
        assert record["category"] == "denominator-inflation"
        assert record["remediation"] == fix.format(
            umbrella=" rather than the root barrel, an umbrella of re-exports" if umbrella else "")

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
        # #734: either arm of the signature may have fired, so the gap names both and sets no count by hand
        assert records[0]["issue"].startswith("a declared count (`stats.exports_documented`, or the provenance "
                                              "map's distinct entry names) equals `stats.effective_denominator`")
        assert records[0]["remediation"] == ("Document the absent exports in SKILL.md or references/: the skill "
                                             "documents 7 of its 10 declared exports.")
        assert mod.from_numerator({"inflated": False, "skipped": True}) == []
        with pytest.raises(mod.AdapterError):
            mod.from_numerator({"declared": 3})

    def test_metadata_coherence(self):
        records = mod.from_metadata_coherence({"findings": [
            {"severity": "Medium", "title": "metadata drift \u2014 barrel export counts diverge", "detail": "12 vs 9"},
            {"severity": "Medium", "title": "metadata drift \u2014 documented-surface export counts diverge",
             "detail": "stats.exports_documented=40, provenance named-exports=30"},
            {"severity": "Info", "title": "multi-denominator reporting: barrel vs documented surface",
             "detail": "barrel=9, documented=30"},
        ]}, "pkg/metadata.json")
        assert [(r["severity"], r["category"], r["source"], r["issue"]) for r in records] == [
            ("Medium", "metadata-drift", "pkg/metadata.json", "12 vs 9"),
            ("Medium", "metadata-drift", "pkg/metadata.json",
             "stats.exports_documented=40, provenance named-exports=30"),
            ("Info", "multi-denominator", "pkg/metadata.json", "barrel=9, documented=30")]
        # #803: update-skill routes no metadata-drift gap (it recounts these counts each time it writes the skill),
        # so the barrel fix names the workflow that rebuilds exports[] from the source
        barrel, documented = records[0]["remediation"], records[1]["remediation"]
        assert barrel.startswith("Re-run Create Skill, which rebuilds `exports[]` and `stats.exports_public_api` in "
                                 "`pkg/metadata.json` from the source.")
        assert "Update Skill does not repair this drift" in barrel and "adding or dropping only the names" in barrel
        # a documented-surface divergence is the `Type::method` entries the named count leaves out: a re-run of
        # Create Skill would reproduce it, so its fix says when no count is wrong
        assert documented.startswith("No count in `pkg/metadata.json` needs a fix when `stats.exports_documented` "
                                     "and the `confidence_distribution` sum agree")
        assert "`Type::method` entries" in documented and "Re-run Create Skill" not in documented
        for text in (barrel, documented):
            assert "applies it" not in text and "metadata update" not in text
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
            {"export_name": "Stories", "source_file": "x.tsx", "source_line": 99, "reason": "line-out-of-bounds"},
            {"export_name": "odd", "source_file": "lib/api.py", "source_line": "L7", "reason": "line-invalid"},
            {"export_name": "flag", "source_file": "lib/api.py", "source_line": True, "reason": "line-invalid"},
            {"export_name": "real", "source_file": "lib/api.py", "source_line": 3.0, "reason": "line-invalid"},
            {"export_name": "skipped", "source_file": "lib/api.py", "source_line": 1, "reason": "no-such-reason"},
        ]})
        assert brief(records) == [
            ("Low", "provenance-line", "Provenance line is not the definition of search", "lib/api.py:25", "search"),
            ("Info", "provenance-unverified", "Provenance line not verified for fetch", "lib/api.py:40", "fetch"),
            # #832: a citation that does not resolve is a gap too, at the file:line the map records
            ("Low", "provenance-line", "Provenance file is missing for gone", "lib/old.py:3", "gone"),
            ("Low", "provenance-line", "Provenance line is out of range for Stories", "x.tsx:99", "Stories"),
            # a line that is not a number gives no line to cite: the Source is the file alone
            ("Info", "provenance-unverified", "Provenance line not verified for odd", "lib/api.py", "odd"),
            ("Info", "provenance-unverified", "Provenance line not verified for flag", "lib/api.py", "flag"),
            ("Info", "provenance-unverified", "Provenance line not verified for real", "lib/api.py", "real"),
        ]
        assert records[0]["remediation"].startswith(
            "Set the provenance `source_line` of `search` in `lib/api.py` to its definition line (26, 31)")
        assert "check by hand" in records[1]["issue"]
        gone, oob, invalid = records[2:5]
        # update-skill cannot point an entry at another file: the fix says so, and pins no definition line
        assert gone["remediation"].startswith("Set the provenance `source_file` and `source_line` of `gone`")
        assert "does not repair this" in gone["remediation"] and "definition line (" not in gone["remediation"]
        # an existing file that cannot be read is `file-missing` too
        assert "has no readable file `lib/old.py`" in gone["issue"]
        assert "applies this when the file defines it on one line" in oob["remediation"]
        assert "definition line (" not in oob["remediation"] and "past its end" in oob["issue"]
        assert "not a line number" in invalid["issue"] and "check by hand" in invalid["issue"]
        for record in records:
            assert record["title"].endswith(record["export"]), record

    # #911: `Entry` is cited at the `API_Entry` declaration a multi-line `export type { ... }` list in
    # `pkg/root.ts` renames to it, which classify-stale marks `aliased`
    ALIAS_VERIFY = {"stale": [
        {"export_name": "Entry", "source_file": "pkg/api.ts", "source_line": 1, "reason": "line-not-definition",
         "definition_lines": []},
        {"export_name": "fetch", "source_file": "lib/api.py", "source_line": 40, "reason": "line-not-definition",
         "definition_lines": []}]}
    ALIASED = {"name": "Entry", "fabricated": False, "source": "pkg/api.ts:1", "defined_at": "pkg/root.ts:2",
               "declared_in": ["pkg/root.ts:2"], "reason": "aliased", "entries": [], "renames": "API_Entry"}

    def test_an_aliased_name_names_its_alias(self):
        """#911: an aliased name's unverified line leads with recording the rename and names the alias line, in
        its remediation and its issue; the gap's title, Source, severity and category stay, and every other
        record keeps today's text."""
        plain = mod.from_provenance_line(self.ALIAS_VERIFY)
        records = mod.from_provenance_line(self.ALIAS_VERIFY, [self.ALIASED])
        assert brief(records) == brief(plain) == [
            ("Info", "provenance-unverified", "Provenance line not verified for Entry", "pkg/api.ts:1", "Entry"),
            ("Info", "provenance-unverified", "Provenance line not verified for fetch", "lib/api.py:40", "fetch")]
        assert records[0]["remediation"] == (
            "`Entry` is an alias of `API_Entry`, which a cited file declares; the source declares the alias at "
            "`pkg/root.ts:2`, and no line of `pkg/api.ts` defines `Entry`. If no other entry already has "
            "`export_name` `API_Entry`, record the rename in this provenance entry: set `export_name` to `API_Entry`, add `reexported_as` `Entry`, cite the line that declares "
            "`API_Entry` and move the citations of `Entry` to that line. Or cite the alias: set `source_file` to "
            "`pkg/root.ts` and `source_line` to `2`, and move the citations of `Entry` there.")
        assert records[0]["issue"] == (
            "no line of `pkg/api.ts` defines `Entry`: the source declares it only as the alias at `pkg/root.ts:2`")
        # a folded variant's issue keeps its base sentence
        folded = {"stale": [self.ALIAS_VERIFY["stale"][0] | {"folded_to": "Ent"}]}
        [record] = mod.from_provenance_line(folded, [self.ALIASED])
        assert record["issue"] == (
            "no line of `pkg/api.ts` defines `Entry`: the source declares it only as the alias at "
            "`pkg/root.ts:2`. `Entry` is a bookkeeping variant `pkg/api.ts` never names, checked against its base "
            "`Ent`.")
        assert records[1] == plain[1]
        # without --stale, today's advice
        assert plain[0]["remediation"] == ("Open `pkg/api.ts` and confirm that line 1 defines `Entry`; if another "
                                           "line does, set the provenance `source_line` to it.")
        # with no string `renames`, a phrase stands for the renamed name
        for unnamed in ({k: v for k, v in self.ALIASED.items() if k != "renames"}, self.ALIASED | {"renames": None},
                        self.ALIASED | {"renames": ""}):
            [record, _] = mod.from_provenance_line(self.ALIAS_VERIFY, [unnamed])
            assert record["remediation"] == (
                "`Entry` is an alias of a name a cited file declares; the source declares the alias at "
                "`pkg/root.ts:2`, and no line of `pkg/api.ts` defines `Entry`. If no other entry already has that name as its `export_name`, record "
                "the rename in this provenance entry: set `export_name` to a name a cited file declares, add "
                "`reexported_as` `Entry`, cite the line that declares a name a cited file declares and move the "
                "citations of `Entry` to that line. Or cite the alias: set `source_file` to `pkg/root.ts` and "
                "`source_line` to `2`, and move the citations of `Entry` there.")

    def test_an_alias_of_default_cites_the_alias_line_alone(self):
        """#911 (amended in review): the map keys on `export_name`, so it holds one `default` entry at most and a
        barrel of `export { default as X }` lines cannot record each rename. An alias of `default` leads with
        citing the alias line, split at its last colon, and never suggests recording the rename."""
        stale = [self.ALIASED | {"renames": "default", "defined_at": "pkg/a:b/root.ts:12"}]
        [record, _] = mod.from_provenance_line(self.ALIAS_VERIFY, stale)
        assert record["remediation"] == (
            "`Entry` is an alias of `default`, which a cited file declares; the source declares the alias at "
            "`pkg/a:b/root.ts:12`, and no line of `pkg/api.ts` defines `Entry`. Cite the alias: set `source_file` to `pkg/a:b/root.ts` and `source_line` to `12`, and move "
            "the citations of `Entry` there.")
        for gone in ("record the rename", "reexported_as", "set `export_name`"):
            assert gone not in record["remediation"].lower(), gone
        assert record["issue"] == (
            "no line of `pkg/api.ts` defines `Entry`: the source declares it only as the alias at "
            "`pkg/a:b/root.ts:12`")

    @pytest.mark.parametrize("renames", ["defaults", "Default", "_Impl"])
    def test_an_alias_of_another_name_guards_the_rename(self, renames: str):
        """#911 (amended in review): any L but `default` leads with recording the rename, only if no other entry
        already has `export_name` L (the map keys on it), and gives citing the alias line as the other option."""
        [record, _] = mod.from_provenance_line(self.ALIAS_VERIFY, [self.ALIASED | {"renames": renames}])
        assert record["remediation"] == (
            f"`Entry` is an alias of `{renames}`, which a cited file declares; the source declares the alias at "
            f"`pkg/root.ts:2`, and no line of `pkg/api.ts` defines `Entry`. If no other entry already has "
            f"`export_name` `{renames}`, record the rename in this provenance entry: set `export_name` to `{renames}`, add `reexported_as` `Entry`, cite the line that "
            f"declares `{renames}` and move the citations of `Entry` to that line. Or cite the alias: set "
            "`source_file` to `pkg/root.ts` and `source_line` to `2`, and move the citations of `Entry` there.")

    def test_a_chain_alias_names_the_declared_name_not_the_line_s_rename(self):
        """#954: classify-stale follows a rename chain, so `renames` is the name the cited file declares where
        the chain ends, not the name the `defined_at` line renames: `pkg/__init__.py:1` reads `from .impl import
        _Impl as Impl`, and `pkg/impl/__init__.py` renames the cited `_CoreImpl` to `_Impl`. The head says only
        what holds for a chain: `Impl` is an alias of `_CoreImpl`, declared at the line, which renames
        `_Impl`."""
        verify = {"stale": [{"export_name": "Impl", "source_file": "pkg/impl/_core.py", "source_line": 1,
                             "reason": "line-not-definition", "definition_lines": []}]}
        chain = {"name": "Impl", "fabricated": False, "source": "pkg/impl/_core.py:1",
                 "defined_at": "pkg/__init__.py:1", "declared_in": ["pkg/__init__.py:1"], "reason": "aliased",
                 "entries": [], "renames": "_CoreImpl"}
        [record] = mod.from_provenance_line(verify, [chain])
        assert record["remediation"] == (
            "`Impl` is an alias of `_CoreImpl`, which a cited file declares; the source declares the alias at "
            "`pkg/__init__.py:1`, and no line of `pkg/impl/_core.py` defines `Impl`. If no other entry already "
            "has `export_name` `_CoreImpl`, record the rename in this provenance entry: set `export_name` to "
            "`_CoreImpl`, add `reexported_as` `Impl`, cite the line that declares `_CoreImpl` and move the "
            "citations of `Impl` to that line. Or cite the alias: set `source_file` to `pkg/__init__.py` and "
            "`source_line` to `1`, and move the citations of `Impl` there.")
        assert "renames `_CoreImpl`" not in record["remediation"]

    @pytest.mark.parametrize("stale", [
        [],
        [ALIASED | {"name": "Other"}],
        [ALIASED | {"reason": "defined"}],
        [ALIASED | {"defined_at": None}],
        [ALIASED | {"defined_at": ""}],
        [ALIASED | {"defined_at": "pkg/root.ts"}],
        [{k: v for k, v in ALIASED.items() if k != "name"}],
        ["Entry"],
    ], ids=["empty", "another-name", "not-aliased", "no-defined-at", "empty-defined-at", "defined-at-without-a-line",
            "no-name", "not-an-item"])
    def test_a_name_classify_stale_does_not_alias_keeps_todays_text(self, stale: list):
        assert mod.from_provenance_line(self.ALIAS_VERIFY, stale) == mod.from_provenance_line(self.ALIAS_VERIFY)

    def test_an_aliased_name_with_a_definition_line_or_another_reason_keeps_todays_text(self):
        """Only an unverified line names the alias: a line verify pins, and every other reason, keep their text."""
        verify = {"stale": [
            {"export_name": "Entry", "source_file": "pkg/api.ts", "source_line": 1, "reason": "line-not-definition",
             "definition_lines": [3]},
            {"export_name": "Entry", "source_file": "pkg/gone.ts", "source_line": 1, "reason": "file-missing"},
            {"export_name": "Entry", "source_file": "pkg/api.ts", "source_line": 99, "reason": "line-out-of-bounds"},
            {"export_name": "Entry", "source_file": "pkg/api.ts", "source_line": "x", "reason": "line-invalid"}]}
        assert mod.from_provenance_line(verify, [self.ALIASED]) == mod.from_provenance_line(verify)

    def test_a_stale_result_that_is_not_a_list_is_refused(self):
        with pytest.raises(mod.AdapterError, match=r"^--stale is not classify-stale JSON \(a list\)$"):
            mod.from_provenance_line(self.ALIAS_VERIFY, {})

    def test_the_append_reads_stale(self, ledger: Path, tmp_path: Path):
        """`--from provenance-line --stale` records the alias's remediation; a --stale file that is not
        classify-stale's list is INVALID_INPUT, with the coverage adapter's message, and writes nothing."""
        verify = write_json(tmp_path / "verify.json", self.ALIAS_VERIFY)
        bad = write_json(tmp_path / "bad.json", {})
        proc = from_file(ledger, "coverage-check", "provenance-line", verify, stale=bad)
        assert proc.returncode == 2
        out = json.loads(proc.stdout)
        assert (out["code"], out["error"]) == ("INVALID_INPUT", "--stale is not classify-stale JSON (a list)")
        assert not ledger.exists()
        proc = from_file(ledger, "coverage-check", "provenance-line", verify,
                         stale=write_json(tmp_path / "stale.json", [self.ALIASED]))
        assert proc.returncode == 0, proc.stdout
        [entry, fetch] = ledger_records(ledger)
        assert (entry["export"], entry["source"]) == ("Entry", "pkg/api.ts:1")
        assert entry["remediation"].startswith(
            "`Entry` is an alias of `API_Entry`, which a cited file declares; the source declares the alias at "
            "`pkg/root.ts:2`")
        assert fetch["remediation"].startswith("Open `lib/api.py` and confirm that line 40 defines `fetch`;")

    def test_a_fabricated_export_takes_no_provenance_line_gap(self, tmp_path: Path):
        """#832: an export the ledger already records as a fabricated signature no longer exists, so the append
        drops its provenance records; another export's, and a plain append, are kept."""
        ledger = tmp_path / "ledger.json"
        fabricated = write_json(tmp_path / "fabricated.json", [record(
            severity="Critical", category="fabricated-signature", title="Fabricated signature: gone",
            source="lib/old.py:3", export="gone")])
        assert run("append", "--ledger", str(ledger), "--stage", "coverage-check", "--input",
                   str(fabricated)).returncode == 0
        verify = write_json(tmp_path / "verify.json", {"stale": [
            {"export_name": "gone", "source_file": "lib/old.py", "source_line": 3, "reason": "file-missing"},
            {"export_name": "gone", "source_file": "lib/old.py", "source_line": "x", "reason": "line-invalid"},
            {"export_name": "search", "source_file": "lib/api.py", "source_line": 99,
             "reason": "line-out-of-bounds"}]})
        proc = from_file(ledger, "coverage-check", "provenance-line", verify)
        assert proc.returncode == 0, proc.stdout
        assert [(r["category"], r.get("export")) for r in ledger_records(ledger)] == [
            ("fabricated-signature", "gone"), ("provenance-line", "search")]
        assert mod.without_fabricated({"records": []}, [record(export="gone")]) == [record(export="gone")]

    def test_a_folded_variant_names_its_base(self):
        """#847: a bookkeeping variant verify checked against its base names the base in its issue, and its
        remediation still lists the definition lines update-skill's rule R5 reads."""
        records = mod.from_provenance_line({"stale": [
            {"export_name": "mockChannel_exact", "source_file": "code/mock.ts", "source_line": 1,
             "reason": "line-not-definition", "definition_lines": [3], "folded_to": "mockChannel"},
            {"export_name": "a11y_x", "source_file": "code/x.ts", "source_line": 2,
             "reason": "line-not-definition", "definition_lines": [], "folded_to": "x"},
            {"export_name": "search", "source_file": "lib/api.py", "source_line": 25,
             "reason": "line-not-definition", "definition_lines": [26]},
        ]})
        assert brief(records) == [
            ("Low", "provenance-line", "Provenance line is not the definition of mockChannel_exact", "code/mock.ts:1",
             "mockChannel_exact"),
            ("Info", "provenance-unverified", "Provenance line not verified for a11y_x", "code/x.ts:2", "a11y_x"),
            ("Low", "provenance-line", "Provenance line is not the definition of search", "lib/api.py:25", "search")]
        assert records[0]["issue"].endswith(
            "the lines that define it are 3. `mockChannel_exact` is a bookkeeping variant `code/mock.ts` never names, "
            "checked against its base `mockChannel`.")
        assert "checked against its base `x`" in records[1]["issue"]
        # the person confirms the line against the base the check read
        assert records[1]["remediation"].startswith("Open `code/x.ts` and confirm that line 2 defines `x`;")
        assert "bookkeeping variant" not in records[2]["issue"]
        manifest_path = SCRIPT.parent.parent.parent / "shared" / "scripts" / "skf-build-change-manifest.py"
        manifest_spec = importlib.util.spec_from_file_location("skf_manifest_for_gap_ledger", manifest_path)
        manifest = importlib.util.module_from_spec(manifest_spec)
        assert manifest_spec.loader is not None
        manifest_spec.loader.exec_module(manifest)
        assert manifest._pinned_lines(records[0]["remediation"]) == [3]

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
             "reason": "line-not-definition", "definition_lines": [12]},
            {"export_name": "Stories", "source_file": "src/stories.ts", "source_line": 4, "reason": "file-missing"},
            {"export_name": "ghost", "source_file": "src/g.ts", "source_line": 2, "reason": "file-missing"},
            {"export_name": "odd", "source_file": "src/fetch.ts", "source_line": "x", "reason": "line-invalid"}]})
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
            ("Info", "provenance-unverified"), ("Info", "observation")}
        # #832: a citation whose file the pinned source lacks is recorded, at the file:line the map records
        missing = next(r for r in ledger_records(ledger) if r["title"] == "Provenance file is missing for Stories")
        assert (missing["severity"], missing["source"], missing["export"]) == ("Low", "src/stories.ts:4", "Stories")
        # a name classify-stale found fabricated, recorded first, takes no provenance line gap for its gone file
        assert [r["category"] for r in ledger_records(ledger) if r.get("export") == "ghost"] == [
            "fabricated-signature"]
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
