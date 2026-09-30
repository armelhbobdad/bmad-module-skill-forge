#!/usr/bin/env python3
"""Tests for skf-previous-report.py (skf-verify-stack init.md §1).

Covers the collision check against both files a run writes (the timestamped
report and the -latest copy, compared as files so a link still matches), the
pick of the newest earlier report of the project, the reports it never picks
(this run's own, -latest, another project's whose slug extends this one, one
it cannot read), the not-found path (a path it cannot read included), usage
errors, the CLI exit codes, and the init.md prose that calls the helper, asks
again on an interactive collision and maps a headless one to the exit 5 halt.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILL = REPO_ROOT / "src" / "skf-verify-stack"
SCRIPT_PATH = SKILL / "scripts" / "skf-previous-report.py"
INIT = SKILL / "references" / "init.md"
EXIT_CODES = SKILL / "references" / "exit-codes.md"

spec = importlib.util.spec_from_file_location("skf_previous_report", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
resolve = mod.resolve

SLUG = "my-app"
NOW = "20260930-120000"


def _report(folder: Path, suffix: str, slug: str = SLUG, body: str = "---\nschemaVersion: \"1.0\"\n---\n") -> Path:
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


def test_exit_codes_name_both_files_for_the_collision():
    row = next(line for line in EXIT_CODES.read_text(encoding="utf-8").splitlines() if line.startswith("| 5 "))
    assert "`previous-report-collision`" in row
    assert "`{outputFile}`" in row and "`{outputFileLatest}`" in row
