#!/usr/bin/env python3
"""test/fixtures/health-check-shared.json, run through skf-health-check-seen.py.

UltraCode Goal (armelhbobdad/bmad-module-ultracode-goal) keeps a byte-identical
copy of the fixture, and its own adapter runs the same rows through
health_check_fp.py, so the two health-check helpers cannot drift apart
unnoticed: the hash formula with both repositories' golden fingerprints, the
defect-key and section-slug rules, the seen verdicts with their opening lines,
and the record rules. A change to the fixture lands in one pull request per
repository. The sha256 pin below catches an accidental edit; a deliberate one
updates the pin here and makes the same change, pin included, in the other
repository. The scheduled health-check-fixture-drift.yaml, which compares the
two copies, is red between the two merges.

Every row is written in terms both helpers share, and a row that only one
helper can run is tagged with its `module`. Each section's rows hold exactly
the keys below (the optional ones in brackets), so a misspelled key fails:

  fingerprint   {module, severity, workflow, step_file, [step_file_arg],
                section_slug, defect_key, tuple, fp, legacy_fp}: tuple is fp's
                sha1 input and legacy_fp the hash without "|defect_key". Every
                row is recomputed with the helper's _sha7; a "skf" row also
                runs `fingerprint` (a "ucg" row is UltraCode Goal's to run).
                step_file_arg, on a "skf" row alone, is the --step-file this
                helper's `fingerprint` is given in place of step_file, a bare
                name or any path that it reads as step_file; UltraCode Goal's
                takes a stage instead.
  defect_key    {name, key}: "" when the name yields no word.
  section_slug  {heading, slug}: "" when the heading yields no slug.
  seen          {name, cache, fp, legacy_fp, repo, [gh, gh_url], expect:
                {status, matched_on, opening_line, record}}. cache is
                {"raw": <the file's text, as UTF-8, a byte order mark written
                as a \\ufeff escape>}, {"base64": <the file's bytes, for bytes
                that are not UTF-8>} or null for no file; repo is null for no
                --repo; gh is what `gh issue view` answers (its `state` and
                `stateReason` alone), null for a failed call, and gh_url the
                issue URL it must be asked about, both left out when no call
                may happen. record is the record the verdict was read from,
                null for none. The row's `seen` is this helper's `lookup`,
                and its `status` this helper's `verdict`.
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

import base64
import binascii
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

# The pin catches an accidental edit of the fixture. A deliberate one lands in one pull request per repository, each
# updating this pin in its adapter: the pin alone cannot tell a one-sided edit, which the drift check catches.
FIXTURE_SHA256 = "b193cb6debc173bb7fcd86f692a703c24036df5895f800bba651055ae0e0c0a0"

SECTIONS = ("about", "fingerprint", "defect_key", "section_slug", "seen", "record")
STATUSES = ("unseen", "handled", "regression", "possible-regression", "unrecognized")

# Each section's row keys: those every row holds, and those a row may hold besides.
ROW_KEYS = {
    "fingerprint": (("module", "severity", "workflow", "step_file", "section_slug", "defect_key", "tuple", "fp",
                     "legacy_fp"), ("step_file_arg",)),
    "defect_key": (("name", "key"), ()),
    "section_slug": (("heading", "slug"), ()),
    "seen": (("name", "cache", "fp", "legacy_fp", "repo", "expect"), ("gh", "gh_url")),
    "record": (("name", "cache_before", "args", "expect"), ()),
}
SEEN_EXPECT = ("status", "matched_on", "opening_line", "record")
# What a seen row's gh answer may hold: the fields `gh issue view --json state,stateReason` prints.
GH_KEYS = ("state", "stateReason")
RECORD_EXPECT = ("written", "record", "cache_after", "set_aside")
# The options a record row's args may give `record` (the adapter adds --cache): a misspelled one would fail the call,
# and pass as a refusal.
RECORD_OPTIONS = ("--fp", "--issue-url", "--action", "--date", "--regression")


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _rows(section: str) -> list[dict]:
    return _fixture()[section]


def _row_id(section: str, row: dict) -> str:
    key = {"fingerprint": "fp", "defect_key": "name", "section_slug": "heading"}.get(section, "name")
    return repr(row.get(key)) if section in ("defect_key", "section_slug") else str(row.get(key))


def _ids(section: str) -> list[str]:
    return [_row_id(section, row) for row in _rows(section)]


def _cache_problems(field: str, cache) -> list[str]:
    """What breaks a cache's form: null, {"raw": text} or {"base64": bytes that are not UTF-8}."""
    if cache is None:
        return []
    if not isinstance(cache, dict) or len(cache) != 1 or not isinstance(next(iter(cache.values())), str):
        return [f"{field} is not null, {{'raw': text}} or {{'base64': bytes}}"]
    [(form, value)] = cache.items()
    if form == "raw":
        return []
    if form != "base64":
        return [f"unknown key {form!r} in {field}"]
    try:
        raw = base64.b64decode(value, validate=True)
    except binascii.Error:
        return [f"{field} base64 does not decode"]
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return []
    return [f"{field} base64 holds UTF-8, which is written as raw"]


def _row_problems(section: str, row: dict) -> list[str]:
    """Each key a row lacks or should not hold, by name, and each cache whose form is not one of the three."""
    required, optional = ROW_KEYS[section]
    problems = [f"no key {key!r}" for key in required if key not in row]
    problems += [f"unknown key {key!r}" for key in row if key not in required + optional]
    if section == "fingerprint" and "step_file_arg" in row and row.get("module") != "skf":
        problems.append("key 'step_file_arg' on a row that is not skf's: UltraCode Goal's fingerprint takes a stage")
    if section == "seen":
        if ("gh" in row) != ("gh_url" in row):
            problems.append("key 'gh' without 'gh_url', or 'gh_url' without 'gh'")
        gh = row.get("gh")
        if gh is not None and not isinstance(gh, dict):
            problems.append("gh is not null or an object")
        elif gh is not None:
            problems += [f"unknown key {key!r} in gh" for key in gh if key not in GH_KEYS]
        expect = row.get("expect") if isinstance(row.get("expect"), dict) else {}
        problems += [f"no key {key!r} in expect" for key in SEEN_EXPECT if key not in expect]
        problems += [f"unknown key {key!r} in expect" for key in expect if key not in SEEN_EXPECT]
        problems += _cache_problems("cache", row.get("cache"))
    if section == "record":
        expect = row.get("expect") if isinstance(row.get("expect"), dict) else {}
        if expect != {"refused": True}:
            problems += [f"no key {key!r} in expect" for key in RECORD_EXPECT if key not in expect]
            problems += [f"unknown key {key!r} in expect" for key in expect if key not in RECORD_EXPECT]
        problems += _cache_problems("cache_before", row.get("cache_before"))
        args = row.get("args") if isinstance(row.get("args"), list) else []
        problems += [f"unknown option {arg!r} in args" for arg in args
                     if isinstance(arg, str) and arg.startswith("--") and arg.split("=", 1)[0] not in RECORD_OPTIONS]
    return problems


def _check_row(section: str, row: dict) -> None:
    problems = _row_problems(section, row)
    assert not problems, f"{section} row {_row_id(section, row)}: {'; '.join(problems)}"


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
    data = base64.b64decode(cache["base64"]) if "base64" in cache else cache["raw"].encode("utf-8")
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


@pytest.mark.parametrize("section, row", [(section, row) for section in ROW_KEYS for row in _rows(section)],
                         ids=[f"{section}-{row_id}" for section in ROW_KEYS for row_id in _ids(section)])
def test_a_row_holds_its_sections_keys(section, row):
    """A misspelled key (`ghh` for `gh`) would leave a rule unrun: each row holds its section's keys, and no other."""
    _check_row(section, row)


def test_a_misspelled_key_fails_naming_the_row_and_the_key():
    [row] = [row for row in _rows("seen") if row["name"] == "an open issue"]
    misspelled = {("ghh" if key == "gh" else key): value for key, value in row.items()}
    with pytest.raises(AssertionError, match=r"seen row an open issue: .*unknown key 'ghh'"):
        _check_row("seen", misspelled)
    expect = {**row, "expect": {**row["expect"], "opening": None}}
    with pytest.raises(AssertionError, match=r"seen row an open issue: .*unknown key 'opening' in expect"):
        _check_row("seen", expect)
    fp_row = next(row for row in _rows("fingerprint") if row["module"] == "ucg")
    with pytest.raises(AssertionError, match=r"key 'step_file_arg' on a row that is not skf's"):
        _check_row("fingerprint", {**fp_row, "step_file_arg": "gate.md"})
    cache = {**row, "cache": {"base64": base64.b64encode(b"{}").decode("ascii")}}
    with pytest.raises(AssertionError, match=r"cache base64 holds UTF-8"):
        _check_row("seen", cache)
    # A misspelled field of the gh answer would read as a close with no reason.
    answer = {**row, "gh": {"state": "CLOSED", "stateReasn": "COMPLETED"}}
    with pytest.raises(AssertionError, match=r"seen row an open issue: .*unknown key 'stateReasn' in gh"):
        _check_row("seen", answer)
    # A misspelled option makes the call fail, so a refused row would pass whatever the rule.
    [refused] = [row for row in _rows("record") if row["name"] == "refused: no issue_url"]
    for wrong in (["--isue-url", "https://github.com/o/r/issues/1"], ["--isue-url=https://github.com/o/r/issues/1"]):
        with pytest.raises(AssertionError, match=r"record row refused: no issue_url: .*unknown option '--isue-url"):
            _check_row("record", {**refused, "args": [*refused["args"], *wrong]})


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
    assert [name for name, cache in rows if cache and cache.get("raw", "").startswith("\ufeff")] == [
        n for n, _ in named]


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
                                    "--step-file", row.get("step_file_arg", row["step_file"]),
                                    f"--section={row['section_slug']}",
                                    f"--defect-key={row['defect_key']}"])
    assert code == 0, out
    payload = json.loads(out)
    keys = ("tuple", "fp", "legacy_fp", "step_file")
    assert {key: payload[key] for key in keys} == {key: row[key] for key in keys}


def test_both_repositories_goldens_are_rows():
    rows = _rows("fingerprint")
    assert {row["module"] for row in rows} == {"ucg", "skf"}
    hashes = {row["fp"] for row in rows} | {row["legacy_fp"] for row in rows}
    # UCG's gate golden and its keyless twin; Skill Forge's two defects of one section and their shared section hash,
    # and its own stage's golden.
    assert {"fp-4e6fb0f", "fp-3d74222", "fp-a54e7a6", "fp-ed2bb67", "fp-eb2d6f2", "fp-9699f88"} <= hashes
    # Skill Forge's fingerprint reads a bare name, an install path and a Windows path as the hashed step file.
    args = [row["step_file_arg"] for row in rows if "step_file_arg" in row]
    assert any("/" not in arg and "\\" not in arg for arg in args)
    assert any(arg.startswith("_bmad/skf/") for arg in args)
    assert any("\\" in arg for arg in args)


# --- defect_key and section_slug -----------------------------------------------------------


@pytest.mark.parametrize("row", _rows("defect_key"), ids=_ids("defect_key"))
def test_a_defect_key_row(row):
    mod = _load()
    assert mod.defect_key(row["name"]) == row["key"]
    if row["key"]:
        assert mod.DEFECT_KEY_RE.fullmatch(row["key"])


def test_the_defect_key_rows_drop_every_known_extension():
    mod = _load()
    for ext in mod.KNOWN_EXTENSIONS:
        assert any(row["name"].lower().endswith(ext) and row["key"] and not row["key"].endswith(ext[1:])
                   for row in _rows("defect_key")), ext


def _trailing_edges(name: str, edges: str) -> str:
    """The run of whitespace and edge characters a name ends with."""
    end = len(name)
    while end and (name[end - 1].isspace() or name[end - 1] in edges):
        end -= 1
    return name[end:]


def test_the_defect_key_rows_trim_every_edge_character():
    """A leading edge character is dropped with the other characters that are not letters or digits whether trimmed
    or not, so only a trailing one pins the trim: each ends a row whose name yields a key."""
    mod = _load()
    for edge in mod._NAME_EDGES:
        assert any(edge in _trailing_edges(row["name"], mod._NAME_EDGES) and row["key"]
                   for row in _rows("defect_key")), edge


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
            "opening_line": payload["opening_line"], "record": payload["record"]} == row["expect"]
    # gh is asked about the row's issue, once, or never.
    assert calls == ([row["gh_url"]] if "gh" in row else [])


def test_the_seen_rows_cover_every_verdict_and_opening_line():
    rows = _rows("seen")
    assert set(STATUSES) == {row["expect"]["status"] for row in rows}
    # Bytes that are not UTF-8 are no cache: unseen, whatever records they spell.
    not_utf8 = [row for row in rows if row["cache"] and "base64" in row["cache"]]
    assert not_utf8 and {row["expect"]["status"] for row in not_utf8} == {"unseen"}
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
    assert any(e.get("set_aside") and "base64" in (row["cache_before"] or {}) for row, e in zip(rows, expects)), (
        "a cache that is not UTF-8 is set aside")
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
