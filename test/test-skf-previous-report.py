#!/usr/bin/env python3
"""Tests for skf-previous-report.py (skf-verify-stack init.md §1).

Covers the collision check against both files a run writes (the timestamped
report and the -latest copy, compared as files so a link still matches), the
pick of the newest finished earlier report of the project (its stepsCompleted
lists synthesize and it passes the feasibility-report check, both read with the
shared report reader), the reports it never picks (this run's own, -latest,
another project's whose slug extends this one, one it cannot read, one a halted
run left unfinished or unchecked), the not-found path (a path it cannot read
included), the missing shared reader (exit 3), the installed layout, usage
errors, the CLI exit codes, and the init.md prose that calls the helper, asks
again on an interactive collision, maps a headless one to the exit 5 halt and
records the headless pick.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILL = REPO_ROOT / "src" / "skf-verify-stack"
SCRIPT_PATH = SKILL / "scripts" / "skf-previous-report.py"
READER_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-validate-feasibility-report.py"
INIT = SKILL / "references" / "init.md"
EXIT_CODES = SKILL / "references" / "exit-codes.md"

spec = importlib.util.spec_from_file_location("skf_previous_report", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
resolve = mod.resolve

SLUG = "my-app"
NOW = "20260930-120000"


# The body of a report that passes the feasibility-report check report.md §1
# runs: the five sections in their order, the canonical verdict table once.
CHECKED_BODY = (
    "## Executive Summary\n\n## Coverage Analysis\n\n## Integration Verdicts\n\n"
    "| lib_a | lib_b | verdict | rationale |\n|---|---|---|---|\n\n"
    "## Recommendations\n\n## Evidence Sources\n"
)
CHECKED_FRONTMATTER = "---\nschemaVersion: \"1.0\"\noverallVerdict: \"FEASIBLE\"\n"
# A report whose run finished: synthesize appended its step (synthesize.md §5),
# and the report passes the check.
FINISHED = (
    CHECKED_FRONTMATTER
    + "stepsCompleted: ['init', 'coverage', 'integrations', 'requirements', 'synthesize']\n---\n"
    + CHECKED_BODY
)
# A report a run left when it halted in its integrations step.
UNFINISHED = "---\nschemaVersion: \"1.0\"\nstepsCompleted: ['init', 'coverage']\n---\n"


def _report(folder: Path, suffix: str, slug: str = SLUG, body: str = FINISHED) -> Path:
    path = folder / f"feasibility-report-{slug}-{suffix}.md"
    path.write_bytes(body.encode("utf-8"))
    return path


def _posix(value):
    return Path(value).as_posix() if value is not None else None


def _can_symlink(tmp_path: Path) -> bool:
    try:
        (tmp_path / ".probe-link").symlink_to(tmp_path / ".probe-target")
    except (OSError, NotImplementedError):
        return False
    (tmp_path / ".probe-link").unlink()
    return True


# --- a given path --------------------------------------------------------------


def test_the_latest_copy_is_a_collision(tmp_path):
    # The file every run overwrites at init: comparing against it compares the
    # run with itself, so every finding would come out unchanged.
    latest = _report(tmp_path, "latest")
    _report(tmp_path, "20260101-080000")
    result, code = resolve(str(tmp_path), SLUG, NOW, str(latest))
    assert code == 1
    assert result["status"] == "collision"
    assert _posix(result["collidesWith"]) == latest.as_posix()
    assert result["previousReport"] is None
    assert _posix(result["outputFileLatest"]) == latest.as_posix()


def test_this_runs_own_report_is_a_collision(tmp_path):
    own = _report(tmp_path, NOW)
    result, code = resolve(str(tmp_path), SLUG, NOW, str(own))
    assert code == 1
    assert result["status"] == "collision"
    assert _posix(result["collidesWith"]) == own.as_posix()


def test_a_link_to_the_latest_copy_is_a_collision(tmp_path):
    latest = _report(tmp_path, "latest")
    other = tmp_path / "elsewhere"
    other.mkdir()
    hard = other / "backup.md"
    os.link(latest, hard)  # the same file under another name
    result, code = resolve(str(tmp_path), SLUG, NOW, str(hard))
    assert code == 1 and result["status"] == "collision"
    if _can_symlink(tmp_path):
        soft = other / "latest-link.md"
        soft.symlink_to(latest)
        result, code = resolve(str(tmp_path), SLUG, NOW, str(soft))
        assert code == 1 and result["status"] == "collision"


def test_another_spelling_of_the_latest_path_is_a_collision(tmp_path):
    latest = _report(tmp_path, "latest")
    sub = tmp_path / "sub"
    sub.mkdir()
    spelled = sub / ".." / latest.name  # a path string that differs
    result, code = resolve(str(tmp_path), SLUG, NOW, str(spelled))
    assert code == 1 and result["status"] == "collision"


def test_a_copy_of_the_latest_report_is_used(tmp_path):
    latest = _report(tmp_path, "latest")
    backup = tmp_path / "backup.md"
    backup.write_bytes(latest.read_bytes())
    result, code = resolve(str(tmp_path), SLUG, NOW, str(backup))
    assert code == 0
    assert result["status"] == "provided"
    assert result["previousReport"] == str(backup)
    assert result["previousTimestamp"] is None


def test_an_earlier_timestamped_report_is_used(tmp_path):
    _report(tmp_path, "latest")
    earlier = _report(tmp_path, "20260101-080000")
    result, code = resolve(str(tmp_path), SLUG, NOW, str(earlier))
    assert code == 0
    assert result["status"] == "provided"
    assert result["previousReport"] == str(earlier)
    assert result["previousTimestamp"] == "20260101-080000"
    assert result["collidesWith"] is None


def test_a_missing_path_is_not_found(tmp_path):
    _report(tmp_path, "20260101-080000")
    for given in (tmp_path / "nope.md", tmp_path):  # absent, and a folder
        result, code = resolve(str(tmp_path), SLUG, NOW, str(given))
        assert code == 0
        assert result["status"] == "not-found"
        assert result["previousReport"] is None
        assert result["provided"] == str(given)


def test_the_latest_path_before_any_run_is_not_found(tmp_path):
    # No run has written -latest yet, so the path names no file.
    latest = tmp_path / f"feasibility-report-{SLUG}-latest.md"
    result, code = resolve(str(tmp_path), SLUG, NOW, str(latest))
    assert code == 0 and result["status"] == "not-found"


def _deny_is_file(monkeypatch, denied: Path):
    """Make Path.is_file raise PermissionError for `denied`.

    Python 3.11 to 3.13 raise it for a path under a folder the user cannot
    search (3.14 returns False), as they do for an unreachable network path.
    """
    real_is_file = Path.is_file

    def is_file(self, *args, **kwargs):
        if self == denied:
            raise PermissionError(13, "Permission denied", str(self))
        return real_is_file(self, *args, **kwargs)

    monkeypatch.setattr(Path, "is_file", is_file)


def test_a_path_that_cannot_be_read_is_not_found(tmp_path, monkeypatch):
    # Not exit 1: the caller maps exit 1 to the previous-report-collision halt.
    locked = tmp_path / "locked" / f"feasibility-report-{SLUG}-20260101-080000.md"
    _deny_is_file(monkeypatch, locked)
    result, code = resolve(str(tmp_path), SLUG, NOW, str(locked))
    assert code == 0
    assert result["status"] == "not-found"
    assert result["previousReport"] is None
    assert result["collidesWith"] is None


# --- no path given ---------------------------------------------------------------


def test_the_newest_earlier_report_is_discovered(tmp_path):
    _report(tmp_path, "latest")
    _report(tmp_path, "20251231-235959")
    newest = _report(tmp_path, "20260930-115959")
    _report(tmp_path, "20260102-000000")
    result, code = resolve(str(tmp_path), SLUG, NOW)
    assert code == 0
    assert result["status"] == "discovered"
    assert _posix(result["previousReport"]) == newest.as_posix()
    assert result["previousTimestamp"] == "20260930-115959"
    assert result["provided"] is None


def test_discovery_skips_this_run_latest_and_other_projects(tmp_path):
    _report(tmp_path, "latest")
    _report(tmp_path, NOW)  # this run's own report
    # Another project whose slug starts with this one's: my-app-2.
    _report(tmp_path, "20260930-110000", slug="my-app-2")
    _report(tmp_path, "20260930-110000", slug="other")
    (tmp_path / f"feasibility-report-{SLUG}-2026-draft.md").write_bytes(b"x")
    (tmp_path / f"feasibility-report-{SLUG}-20260930-110000.md.bak").write_bytes(b"x")
    (tmp_path / f"feasibility-report-{SLUG}-20260930-100000.md").mkdir()  # a report name, not a file
    result, code = resolve(str(tmp_path), SLUG, NOW)
    assert code == 0
    assert result["status"] == "none"
    assert result["previousReport"] is None


def test_discovery_skips_a_name_linked_to_the_latest_copy(tmp_path):
    latest = _report(tmp_path, "latest")
    older = _report(tmp_path, "20260101-080000")
    os.link(latest, tmp_path / f"feasibility-report-{SLUG}-20260930-110000.md")
    result, code = resolve(str(tmp_path), SLUG, NOW)
    assert code == 0
    assert _posix(result["previousReport"]) == older.as_posix()


def test_discovery_skips_a_report_that_cannot_be_read(tmp_path, monkeypatch):
    older = _report(tmp_path, "20260101-080000")
    newest = _report(tmp_path, "20260930-110000")
    _deny_is_file(monkeypatch, newest)
    result, code = resolve(str(tmp_path), SLUG, NOW)
    assert code == 0
    assert result["status"] == "discovered"
    assert _posix(result["previousReport"]) == older.as_posix()


def test_nothing_to_discover(tmp_path):
    result, code = resolve(str(tmp_path / "missing"), SLUG, NOW)
    assert code == 0
    assert result["status"] == "none"
    assert _posix(result["outputFile"]) == (tmp_path / "missing" / f"feasibility-report-{SLUG}-{NOW}.md").as_posix()


# --- only a finished report is a baseline ------------------------------------------


def test_discovery_skips_a_report_a_halted_run_left(tmp_path):
    # The newest report stopped before synthesize: comparing against it would
    # measure the run against a partial analysis.
    finished = _report(tmp_path, "20260101-080000")
    _report(tmp_path, "20260930-110000", body=UNFINISHED)
    result, code = resolve(str(tmp_path), SLUG, NOW)
    assert code == 0
    assert result["status"] == "discovered"
    assert _posix(result["previousReport"]) == finished.as_posix()
    assert result["previousTimestamp"] == "20260101-080000"


def test_only_unfinished_reports_leave_nothing_to_discover(tmp_path):
    _report(tmp_path, "20260930-110000", body=UNFINISHED)
    _report(tmp_path, "20260930-100000", body="---\nschemaVersion: \"1.0\"\nstepsCompleted: []\n---\n")
    result, code = resolve(str(tmp_path), SLUG, NOW)
    assert code == 0
    assert result["status"] == "none"
    assert result["previousReport"] is None


@pytest.mark.parametrize(
    "steps, prefix, newline",
    [
        pytest.param("stepsCompleted:\n  - init\n  - coverage\n  - integrations\n  - requirements\n  - synthesize\n",
                     "", "\n", id="block-list"),
        pytest.param("stepsCompleted: [\"init\", \"synthesize\"]  # done\n", "", "\n", id="double-quoted-with-comment"),
        pytest.param("stepsCompleted: ['synthesize']\n", "\ufeff", "\n", id="byte-order-mark"),
        pytest.param("stepsCompleted: ['init', 'synthesize']\n", "", "\r\n", id="crlf"),
    ],
)
def test_a_finished_report_reads_in_any_list_form(tmp_path, steps, prefix, newline):
    body = prefix + (CHECKED_FRONTMATTER + steps + "---\n" + CHECKED_BODY).replace("\n", newline)
    finished = _report(tmp_path, "20260930-110000", body=body)
    result, code = resolve(str(tmp_path), SLUG, NOW)
    assert code == 0
    assert _posix(result["previousReport"]) == finished.as_posix()


@pytest.mark.parametrize(
    "body",
    [
        pytest.param("# no frontmatter\n", id="no-frontmatter"),
        pytest.param("---\nschemaVersion: \"1.0\"\n---\n", id="no-steps"),
        pytest.param("---\nstepsCompleted: synthesize\n---\n", id="scalar-not-a-list"),
        pytest.param("---\nstepsCompleted: ['synthesized']\n---\n", id="another-step"),
        pytest.param("---\nstepsCompleted: ['synthesize']\n", id="unclosed-frontmatter"),
    ],
)
def test_a_report_that_does_not_list_synthesize_is_skipped(tmp_path, body):
    older = _report(tmp_path, "20260101-080000")
    _report(tmp_path, "20260930-110000", body=body)
    result, code = resolve(str(tmp_path), SLUG, NOW)
    assert code == 0
    assert _posix(result["previousReport"]) == older.as_posix()


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(FINISHED.replace("## Evidence Sources\n", ""), id="missing-section"),
        pytest.param(FINISHED.replace("## Recommendations\n\n## Evidence Sources\n",
                                      "## Evidence Sources\n\n## Recommendations\n"), id="sections-out-of-order"),
        pytest.param(FINISHED.replace('schemaVersion: "1.0"', 'schemaVersion: "2.0"'), id="another-schema-version"),
        pytest.param(FINISHED.replace('"FEASIBLE"', '"PROBABLY"'), id="unknown-overall-verdict"),
        pytest.param(FINISHED.replace("|---|---|---|---|\n", "|---|---|---|---|\n| a | b | Fine | x |\n"),
                     id="unknown-pair-verdict"),
        pytest.param(FINISHED.replace("| lib_a | lib_b | verdict | rationale |\n|---|---|---|---|\n", ""),
                     id="no-verdict-table"),
    ],
)
def test_a_finished_report_that_fails_the_check_is_skipped(tmp_path, body):
    # synthesize ran, but report.md §1's check refused the report, so the run
    # never published it: the last report that passed is the baseline.
    checked = _report(tmp_path, "20260101-080000")
    _report(tmp_path, "20260930-110000", body=body)
    result, code = resolve(str(tmp_path), SLUG, NOW)
    assert code == 0
    assert result["status"] == "discovered"
    assert _posix(result["previousReport"]) == checked.as_posix()


def test_a_report_that_is_not_utf8_is_skipped(tmp_path):
    older = _report(tmp_path, "20260101-080000")
    (tmp_path / f"feasibility-report-{SLUG}-20260930-110000.md").write_bytes(b"---\nstepsCompleted: [\xff]\n---\n")
    result, code = resolve(str(tmp_path), SLUG, NOW)
    assert code == 0
    assert _posix(result["previousReport"]) == older.as_posix()


def test_a_given_unfinished_report_is_still_used(tmp_path):
    # The user named it: the delta says what it cannot compare.
    partial = _report(tmp_path, "20260930-110000", body=UNFINISHED)
    result, code = resolve(str(tmp_path), SLUG, NOW, str(partial))
    assert code == 0
    assert result["status"] == "provided"
    assert result["previousReport"] == str(partial)


def test_a_missing_shared_reader_stops_discovery(tmp_path, monkeypatch):
    _report(tmp_path, "20260101-080000")
    monkeypatch.setattr(mod, "SHARED_READER", tmp_path / "gone" / "skf-validate-feasibility-report.py")
    result, code = resolve(str(tmp_path), SLUG, NOW)
    assert code == 3
    assert result["status"] == "reader-missing"
    assert result["previousReport"] is None
    assert "skf-validate-feasibility-report.py" in result["error"]
    # A given path needs no reader.
    given = _report(tmp_path, "20260101-090000")
    result, code = resolve(str(tmp_path), SLUG, NOW, str(given))
    assert (code, result["status"]) == (0, "provided")


def test_the_reader_sits_in_the_shared_scripts_folder():
    assert mod.SHARED_READER == READER_PATH.resolve()


# --- CLI -------------------------------------------------------------------------


def _run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_collision_exits_1(tmp_path):
    latest = _report(tmp_path, "latest")
    proc = _run("--folder", str(tmp_path), "--slug", SLUG, "--timestamp", NOW, "--provided", str(latest))
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["status"] == "collision"


@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="needs POSIX folder permissions, which root bypasses",
)
def test_cli_a_path_under_a_folder_it_cannot_search_is_not_found(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    report = _report(locked, "20260101-080000")
    locked.chmod(0)
    try:
        proc = _run("--folder", str(tmp_path), "--slug", SLUG, "--timestamp", NOW, "--provided", str(report))
    finally:
        locked.chmod(0o700)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["status"] == "not-found"


def test_cli_discovery_and_blank_provided(tmp_path):
    earlier = _report(tmp_path, "20260101-080000")
    for extra in ([], ["--provided", ""], ["--provided", "  "]):
        proc = _run("--folder", str(tmp_path), "--slug", SLUG, "--timestamp", NOW, *extra)
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert out["status"] == "discovered"
        assert _posix(out["previousReport"]) == earlier.as_posix()


def _install(root: Path, with_reader: bool) -> Path:
    """Copy the helper into an installed layout, the shared reader beside it or not."""
    scripts = root / "_bmad" / "skf" / "skf-verify-stack" / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(SCRIPT_PATH, scripts / SCRIPT_PATH.name)
    if with_reader:
        shared = root / "_bmad" / "skf" / "shared" / "scripts"
        shared.mkdir(parents=True)
        shutil.copy2(READER_PATH, shared / READER_PATH.name)
    return scripts / SCRIPT_PATH.name


def test_cli_installed_layout_reads_the_shared_reader(tmp_path):
    script = _install(tmp_path / "project", with_reader=True)
    reports = tmp_path / "forge"
    reports.mkdir()
    finished = _report(reports, "20260101-080000")
    _report(reports, "20260930-110000", body=UNFINISHED)
    proc = subprocess.run(
        [sys.executable, str(script), "--folder", str(reports), "--slug", SLUG, "--timestamp", NOW],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["status"] == "discovered"
    assert _posix(out["previousReport"]) == finished.as_posix()


def test_cli_without_the_shared_reader_exits_3(tmp_path):
    script = _install(tmp_path / "project", with_reader=False)
    reports = tmp_path / "forge"
    reports.mkdir()
    _report(reports, "20260101-080000")
    proc = subprocess.run(
        [sys.executable, str(script), "--folder", str(reports), "--slug", SLUG, "--timestamp", NOW],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 3
    out = json.loads(proc.stdout)
    assert out["status"] == "reader-missing" and out["previousReport"] is None


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(["--slug", SLUG, "--timestamp", NOW], id="no-folder"),
        pytest.param(["--folder", "f", "--timestamp", NOW], id="no-slug"),
        pytest.param(["--folder", "f", "--slug", SLUG], id="no-timestamp"),
        pytest.param(["--folder", "f", "--slug", SLUG, "--timestamp", "2026-09-30"], id="bad-timestamp"),
        pytest.param(["--folder", "f", "--slug", "My App", "--timestamp", NOW], id="project-name-as-slug"),
        pytest.param(["--folder", "f", "--slug", "my--app", "--timestamp", NOW], id="doubled-hyphen"),
    ],
)
def test_cli_usage_errors_exit_2(args):
    proc = _run(*args)
    assert proc.returncode == 2
    assert proc.stdout == ""


# --- the init.md prose that calls it -------------------------------------------


def _init_text():
    return INIT.read_text(encoding="utf-8")


def test_init_binds_the_helper_and_calls_it_once():
    text = _init_text()
    assert "previousReportScript: 'scripts/skf-previous-report.py'" in text
    calls = [line for line in text.splitlines() if "{previousReportScript}" in line and "uv run" in line]
    assert calls == [
        (
            'uv run {previousReportScript} --folder "{outputFolderPath}" --slug "{project_slug}" '
            '--timestamp "{timestamp}" [--provided "<path>"]'
        )
    ]
    # The call fits the helper's parser, with and without the optional flag.
    parser = mod._build_parser()
    for words in (
        ["--folder", "f", "--slug", "x", "--timestamp", NOW],
        ["--folder", "f", "--slug", "x", "--timestamp", NOW, "--provided", "p"],
    ):
        parser.parse_args(words)


def test_init_maps_each_status_and_halts_exit_5_on_a_collision():
    text = _init_text()
    section = text[text.index("**Resolve the previous report"):text.index("### 2.")]
    for status in ("`collision`", "`not-found`", "`provided`", "`discovered`", "`none`"):
        assert status in section, status
    collision = section[section.index("`collision`"):section.index("`not-found`")]
    # Interactive: ask for another path and run the helper again. Headless,
    # where no one can answer: the exit 5 halt.
    assert "Interactive: wait for the answer, run the helper again" in collision
    headless = collision[collision.index("In headless"):]
    assert '(exit code 5, `halt_reason: "previous-report-collision"`)' in headless
    assert "`{outputFile}`" in section and "`{outputFileLatest}`" in section
    # The usage error (exit 2, no JSON) has its own branch.
    assert "When it prints no JSON (exit 2, a usage error)" in section
    # The discovery offer can cancel, as every prompt of the run can.
    discovered = section[section.index("`discovered`"):section.index("`none`")]
    assert "**[X]** cancel" in discovered and "(exit code 6)" in discovered
    # The file-identity procedure now lives in the helper, not in prose.
    assert "st_ino" not in text and "stat(2)" not in text
    assert "provide a backup copy" not in text


def test_init_skips_unfinished_reports_and_records_the_headless_pick():
    text = _init_text()
    section = text[text.index("**Resolve the previous report"):text.index("### 2.")]
    # Discovery takes only a finished report; what finished means is the
    # helper's rule (stepsCompleted lists synthesize, the report passes the
    # check), stated in its docstring and not again in prose.
    assert "the newest earlier report that finished" in section
    assert "stepsCompleted" not in section
    assert "lists `synthesize`" in mod.__doc__ and "read_report()" in mod.__doc__
    assert "§4 overwrites `{outputFile}` and `{outputFileLatest}`" not in section
    # The headless pick is recorded in the run sink, so the envelope lists it.
    discovered = section[section.index("`discovered`"):section.index("`none`")]
    assert '"gate": "init.previous-report"' in discovered
    assert ('uv run {emitEnvelopeHelper} record --workflow skf-verify-stack --run-dir "{run_dir}" '
            '--decision < "{run_dir}/decision.json"') in discovered
    # A missing shared reader halts as any helper that cannot run does.
    missing = section[section.index("`reader-missing` (exit 3)"):]
    assert '(exit code 3, `halt_reason: "resolution-failure"`) at phase `init:previous-report`' in missing


def test_exit_codes_name_both_files_for_the_collision():
    row = next(line for line in EXIT_CODES.read_text(encoding="utf-8").splitlines() if line.startswith("| 5 "))
    assert "`previous-report-collision`" in row
    assert "`{outputFile}`" in row and "`{outputFileLatest}`" in row
