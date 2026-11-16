#!/usr/bin/env python3
"""test/fixtures/health-check-shared.json, run through skf-health-check-seen.py.

UltraCode Goal (armelhbobdad/bmad-module-ultracode-goal) keeps a byte-identical
copy of the fixture, and its own adapter runs the same rows through
health_check_fp.py, so the two health-check helpers cannot drift apart
unnoticed: the hash formula with both repositories' golden fingerprints, the
defect-key and section-slug rules, the seen verdicts with their opening lines,
and the record rules. A change to the fixture lands in one pull request per
repository: the sha256 pin below fails on a one-sided edit, and the scheduled
health-check-fixture-drift.yaml, which compares the two copies, is red between
their merges.

Every row is written in terms both helpers share:

  fingerprint   {module, severity, workflow, step_file, section_slug,
                defect_key, tuple, fp, legacy_fp}: tuple is fp's sha1 input
                and legacy_fp the hash without "|defect_key". Every row is
                recomputed with the helper's _sha7; a "skf" row also runs
                `fingerprint` (a "ucg" row is UltraCode Goal's to run).
  defect_key    {name, key}: "" when the name yields no word.
  section_slug  {heading, slug}: "" when the heading yields no slug.
  seen          {name, cache, fp, legacy_fp, repo, gh, expect: {status,
                matched_on, opening_line}}. cache is {"raw": <the file's text,
                as UTF-8, a byte order mark written as a \\ufeff escape>} or
                null for no file; repo is null for no --repo;
                gh is what `gh issue view` answers, null for a failed call,
                and left out when no call may happen. The row's `seen` is this
                helper's `lookup`, and its `status` this helper's `verdict`.
  record        {name, cache_before, args, expect}. args follow `record`
                (the adapter adds --cache), cache_before is as seen's cache,
                and expect is {written, record, cache_after, set_aside}, with
                cache_after the JSON object the cache then holds and set_aside
                whether a corrupt cache was renamed, or {refused: true}: the
                call fails and the cache bytes are unchanged, whatever its
                exit code and output (the helpers differ there).

No row carries a `defect_slug`, which only UltraCode Goal's helper carries over.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "test" / "fixtures" / "health-check-shared.json"
HELPER = REPO_ROOT / "src" / "shared" / "scripts" / "skf-health-check-seen.py"
DRIFT_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "health-check-fixture-drift.yaml"
# The repository whose copy of the fixture must stay byte-identical, and the branch the drift check reads.
OTHER_REPO = "armelhbobdad/bmad-module-ultracode-goal"
OTHER_REF = "main"

# A change to the fixture lands in one pull request per repository: update this pin in each repository's adapter.
FIXTURE_SHA256 = "883221532296af334b3772582c636106414789d1a03cfb4026246ffdfcc1c27f"

SECTIONS = ("about", "fingerprint", "defect_key", "section_slug", "seen", "record")
STATUSES = ("unseen", "handled", "regression", "possible-regression", "unrecognized")


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _rows(section: str) -> list[dict]:
    return _fixture()[section]


def _ids(section: str) -> list[str]:
    key = {"fingerprint": "fp", "defect_key": "name", "section_slug": "heading"}.get(section, "name")
    return [repr(row[key]) if section in ("defect_key", "section_slug") else row[key] for row in _rows(section)]


def _load():
    """The helper as a fresh module, so a function patched for one row never leaks into another."""
    spec = importlib.util.spec_from_file_location("skf_health_check_seen_shared_fixture", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _main(module, capsys, argv: list[str]) -> tuple[int, str]:
    """main(argv)'s exit code and stdout; an argparse refusal is its SystemExit code."""
    try:
        code = module.main(argv)
    except SystemExit as exc:
        code = exc.code
    return code, capsys.readouterr().out


def _write_cache(path: Path, cache: dict | None) -> bytes | None:
    """Write a row's cache to path; its bytes, or None for a row with no cache file."""
    if cache is None:
        return None
    data = cache["raw"].encode("utf-8")
    path.write_bytes(data)
    return data


# --- the file ----------------------------------------------------------------------------


def test_the_fixture_is_pinned():
    digest = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert digest == FIXTURE_SHA256, (
        f"{FIXTURE.relative_to(REPO_ROOT)} changed: it is byte-identical in {OTHER_REPO}, so make the same change "
        f"there, then update FIXTURE_SHA256 in both adapters (now {digest})"
    )


def test_the_fixture_holds_its_sections_and_no_defect_slug():
    data = _fixture()
    assert tuple(data) == SECTIONS
    assert "byte-identical" in data["about"] and OTHER_REPO in data["about"]
    for section in SECTIONS[1:]:
        assert data[section], section
    for section in ("seen", "record"):
        names = [row["name"] for row in data[section]]
        assert len(set(names)) == len(names), section
    # This helper carries no defect_slug over, so no row may hold one.
    assert "defect_slug" not in FIXTURE.read_text(encoding="utf-8")


def test_each_byte_order_mark_is_an_escape_its_row_names():
    """A literal U+FEFF is invisible and an editor drops it silently: the file writes it as an escape."""
    text = FIXTURE.read_text(encoding="utf-8")
    assert "\ufeff" not in text
    assert "\\ufeff" in text
    rows = [(row["name"], row["cache"]) for row in _rows("seen")]
    rows += [(row["name"], row["cache_before"]) for row in _rows("record")]
    named = [(name, cache) for name, cache in rows if "byte order mark" in name]
    assert named
    for name, cache in named:
        assert cache is not None and cache["raw"].startswith("\ufeff"), name
    # No other row's cache opens with one.
    assert [name for name, cache in rows if cache and cache["raw"].startswith("\ufeff")] == [n for n, _ in named]


# --- fingerprint -------------------------------------------------------------------------


@pytest.mark.parametrize("row", _rows("fingerprint"), ids=_ids("fingerprint"))
def test_a_fingerprint_row(row, capsys):
    mod = _load()
    fields = ("severity", "workflow", "step_file", "section_slug", "defect_key")
    assert row["tuple"] == "|".join(row[field] for field in fields)
    assert row["fp"] == "fp-" + mod._sha7(row["tuple"])
    assert row["legacy_fp"] == "fp-" + mod._sha7(row["tuple"].rsplit("|", 1)[0])
    if row["module"] != "skf":
        return
    code, out = _main(mod, capsys, ["fingerprint", "--severity", row["severity"], "--workflow", row["workflow"],
                                    "--step-file", row["step_file"], f"--section={row['section_slug']}",
                                    f"--defect-key={row['defect_key']}"])
    assert code == 0, out
    payload = json.loads(out)
    keys = ("tuple", "fp", "legacy_fp", "step_file")
    assert {key: payload[key] for key in keys} == {key: row[key] for key in keys}


def test_both_repositories_goldens_are_rows():
    rows = _rows("fingerprint")
    assert {row["module"] for row in rows} == {"ucg", "skf"}
    hashes = {row["fp"] for row in rows} | {row["legacy_fp"] for row in rows}
    # UCG's gate golden and its keyless twin; Skill Forge's two defects of one section and their shared section hash.
    assert {"fp-4e6fb0f", "fp-3d74222", "fp-a54e7a6", "fp-ed2bb67", "fp-eb2d6f2"} <= hashes


# --- defect_key and section_slug -----------------------------------------------------------


@pytest.mark.parametrize("row", _rows("defect_key"), ids=_ids("defect_key"))
def test_a_defect_key_row(row):
    mod = _load()
    assert mod.defect_key(row["name"]) == row["key"]
    if row["key"]:
        assert mod.DEFECT_KEY_RE.fullmatch(row["key"])


@pytest.mark.parametrize("row", _rows("section_slug"), ids=_ids("section_slug"))
def test_a_section_slug_row(row):
    mod = _load()
    assert mod.section_slug(row["heading"]) == row["slug"]
    if row["slug"]:
        assert mod.SECTION_RE.fullmatch(row["slug"])


# --- seen ----------------------------------------------------------------------------------


@pytest.mark.parametrize("row", _rows("seen"), ids=_ids("seen"))
def test_a_seen_row(row, tmp_path, capsys):
    mod = _load()
    cache = tmp_path / "seen.json"
    _write_cache(cache, row["cache"])
    calls = []

    def gh_issue_state(issue_url, timeout=None):
        calls.append(issue_url)
        if "gh" not in row:
            raise AssertionError(f"gh must not run for this row, got {issue_url!r}")
        return row["gh"]

    mod.gh_issue_state = gh_issue_state
    argv = ["lookup", "--fp", row["fp"], "--legacy-fp", row["legacy_fp"], "--cache", str(cache)]
    if row["repo"] is not None:
        argv += ["--repo", row["repo"]]
    code, out = _main(mod, capsys, argv)
    assert code == 0, out
    payload = json.loads(out)
    # This helper names the status `verdict`.
    assert {"status": payload["verdict"], "matched_on": payload["matched_on"],
            "opening_line": payload["opening_line"]} == row["expect"]
    assert len(calls) == (1 if "gh" in row else 0), calls


def test_the_seen_rows_cover_every_verdict_and_opening_line():
    rows = _rows("seen")
    assert set(STATUSES) == {row["expect"]["status"] for row in rows}
    assert {"fp", "legacy_fp", None} == {row["expect"]["matched_on"] for row in rows}
    lines = [row["expect"]["opening_line"] or "" for row in rows]
    for form in ("Regression of https://", "Regression of a previously resolved local finding (resolved ",
                 "Possibly a regression of https://", "Possibly a regression of a previously resolved local finding "
                 "in this section", ", closed as completed since its report on ", ", merged since its report on ",
                 "on an unrecorded date", "so it may be another defect in this section."):
        assert any(form in line for line in lines), form
    assert {None} == {row["expect"]["opening_line"] for row in rows
                      if row["expect"]["status"] in ("unseen", "handled", "unrecognized")}
    assert any(row["repo"] for row in rows) and any("gh" in row and row["gh"] is None for row in rows)


# --- record --------------------------------------------------------------------------------


@pytest.mark.parametrize("row", _rows("record"), ids=_ids("record"))
def test_a_record_row(row, tmp_path, capsys):
    mod = _load()
    cache = tmp_path / "seen.json"
    before = _write_cache(cache, row["cache_before"])
    code, out = _main(mod, capsys, ["record", *row["args"], "--cache", str(cache)])
    aside = sorted(tmp_path.glob("seen.json.corrupt-*"))
    expect = row["expect"]
    if expect == {"refused": True}:
        assert code not in (0, None), out
        assert (cache.read_bytes() if cache.exists() else None) == before
        assert aside == []
        return
    assert set(expect) == {"written", "record", "cache_after", "set_aside"}
    assert code == 0, out
    payload = json.loads(out)
    assert payload["written"] is expect["written"]
    assert payload["fp"] == row["args"][row["args"].index("--fp") + 1]
    assert payload["record"] == expect["record"]
    assert json.loads(cache.read_text(encoding="utf-8")) == expect["cache_after"]
    assert (payload["set_aside"] is not None) is expect["set_aside"]
    if expect["set_aside"]:
        assert [str(path) for path in aside] == [payload["set_aside"]]
        assert aside[0].read_bytes() == before
    else:
        assert aside == []
    if not expect["written"]:
        assert cache.read_bytes() == before


def test_the_record_rows_cover_every_rule():
    rows = _rows("record")
    expects = [row["expect"] for row in rows]
    assert any(e.get("written") is False for e in expects), "a resolved record is never downgraded"
    assert any(e.get("set_aside") for e in expects), "a corrupt cache is set aside"
    assert any(row["cache_before"] is None and e.get("written") for row, e in zip(rows, expects))
    assert any("--regression" in row["args"] for row in rows)
    assert sum(e == {"refused": True} for e in expects) >= 5


# --- the drift check -----------------------------------------------------------------------

COMPARE = "Compare the fixture with UltraCode Goal's copy"

needs_bash = pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None,
                                reason="the step script runs under bash, as on the Ubuntu runner")

# Stands in for curl: writes what FAKE_CURL_MODE says to the --output file and prints the HTTP status
# --write-out asks for, logging its arguments.
FAKE_CURL = """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_CURL_LOG"
out=""
while [ $# -gt 0 ]; do
  case "$1" in
    --output) out="$2"; shift 2 ;;
    *) shift ;;
  esac
done
case "$FAKE_CURL_MODE" in
  same) cp "$FAKE_CURL_BODY" "$out"; printf '200' ;;
  differ) printf '{}\\n' > "$out"; printf '200' ;;
  missing) printf '404: Not Found' > "$out"; printf '404' ;;
  server) printf 'oops' > "$out"; printf '503' ;;
  down) echo "curl: (6) Could not resolve host" >&2; exit 6 ;;
esac
"""


def _drift() -> dict:
    # Only the drift check's tests read YAML: the rows run without PyYAML.
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(DRIFT_WORKFLOW.read_text(encoding="utf-8"))


def _compare_step() -> dict:
    [job] = _drift()["jobs"].values()
    [step] = [s for s in job["steps"] if s.get("name") == COMPARE]
    return step


def test_the_drift_check_is_a_daily_alarm_against_ultracode_goal_main():
    """A scheduled job, never a pull-request gate: it is red between the merges of the two pull requests."""
    workflow = _drift()
    assert set(workflow["on"]) == {"schedule", "workflow_dispatch"}
    assert [entry["cron"].split()[2:] for entry in workflow["on"]["schedule"]] == [["*", "*", "*"]]
    assert workflow["permissions"] == {"contents": "read"}
    assert _compare_step()["shell"] == "bash"
    env = _compare_step()["env"]
    assert env == {"OTHER_REPO": OTHER_REPO, "OTHER_REF": OTHER_REF,
                   "FIXTURE": FIXTURE.relative_to(REPO_ROOT).as_posix()}


def _run_compare(tmp_path: Path, mode: str) -> tuple[subprocess.CompletedProcess, list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(FAKE_CURL, encoding="utf-8")
    curl.chmod(0o755)
    script = tmp_path / "step.sh"
    script.write_text(_compare_step()["run"], encoding="utf-8")
    log = tmp_path / "curl.log"
    # TMPDIR keeps the step's mktemp file inside tmp_path, so a run leaves nothing behind.
    env = {**os.environ, **_compare_step()["env"], "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
           "FAKE_CURL_MODE": mode, "FAKE_CURL_BODY": str(FIXTURE), "FAKE_CURL_LOG": str(log), "TMPDIR": str(tmp_path)}
    # As Actions runs a step whose shell is bash: `bash --noprofile --norc -eo pipefail {0}`.
    proc = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)], cwd=REPO_ROOT, env=env,
                          capture_output=True, text=True, timeout=60)
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return proc, calls


@needs_bash
def test_the_drift_check_passes_on_equal_bytes(tmp_path):
    proc, calls = _run_compare(tmp_path, "same")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    [call] = calls
    assert f"https://raw.githubusercontent.com/{OTHER_REPO}/{OTHER_REF}/test/fixtures/health-check-shared.json" in call
    # The fake answers whatever it is asked, so pin what the step's branches rely on in real curl: the status on
    # stdout (--write-out), the body in a file (--output), and exit 0 on a 404 or a 503 (no --fail), without which
    # a missing copy would read as a failed fetch and its fix would never be named.
    words = call.split()
    assert "--write-out %{http_code}" in call and "--output" in words
    assert not {"--fail", "-f", "--fail-with-body"} & set(words)


@needs_bash
@pytest.mark.parametrize("mode, reason", [
    ("differ", "differs from"),
    ("missing", "has no test/fixtures/health-check-shared.json on main"),
    ("server", "answered HTTP 503"),
    ("down", "Could not fetch"),
])
def test_the_drift_check_fails_naming_the_reason_and_the_fix(tmp_path, mode, reason):
    proc, _ = _run_compare(tmp_path, mode)
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0, out
    assert reason in out
    if mode in ("differ", "missing"):
        # It names the step that brings the two copies back in step.
        assert "byte for byte" in out and "FIXTURE_SHA256" in out
