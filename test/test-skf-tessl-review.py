#!/usr/bin/env python3
"""Tests for skf-tessl-review.py (the optional Tessl Review) and its wiring.

The fixtures under test/fixtures/tessl-review/ are real tessl 0.111.0
outputs: `tessl review run --json` for a small demo skill, a published SKF
skill, a skill whose description holds an XML tag, and a run with
`--threshold 90` that exits 1 and still prints the full JSON; the answer of
`tessl review run --no-wait --json`, of `tessl review view --json` while the
review runs, and the stderr of `tessl review view` for a run id Tessl does
not know. No test runs the real tessl: FakeTessl stands in for `_run` and
keeps a fake clock, and the subprocess tests use a Python stand-in.
TestResolveTessl runs the real tessl lookup against stub commands on PATH.

The wiring tests pin the step-file prose that calls the helper and the
description angle-bracket check, since step files are otherwise untested.
Their slicers assert their markers, so a renamed heading fails loudly.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "src" / "shared" / "scripts"
HELPER = SCRIPTS / "skf-tessl-review.py"
VALIDATOR = SCRIPTS / "skf-validate-frontmatter.py"
GUARD = SCRIPTS / "skf-description-guard.py"
FIXTURES = REPO / "test" / "fixtures" / "tessl-review"

spec = importlib.util.spec_from_file_location("skf_tessl_review", HELPER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# What `tessl skill review <dir>` prints on stderr since tessl replaced the
# command (exit 1, nothing on stdout).
REMOVED_STUB = (
    "✘ No review ran. `tessl skill review` has been replaced by Tessl Review.\n"
    "\n"
    "Use:\n"
    "  - Review a skill: tessl review run <path>\n"
    "  - Improve a skill, replacing --optimize: tessl review fix <path>\n"
    "\n"
    "Both require signing in and a workspace, which the removed command did not.\n"
    "The flag-by-flag mapping is at\n"
    "https://docs.tessl.io/improving-your-skills/migrate-from-skill-review\n"
)
SIGNED_OUT_STDERR = "⚠ You are not logged in\n✘ Please authenticate with Tessl to continue. Run `tessl login` to sign up or log in.\n"
RUN_ID = "01a0e4bc-40c0-7143-87c5-5e24d93423d8"  # submit-pending.json and view-incomplete.json
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"  # view-unknown-run.stderr


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _review(name: str) -> dict:
    return mod.parse_review(json.loads(_fixture(name)))


def _completed(run_id: str = RUN_ID) -> str:
    """demo-skill.json as `tessl review view <run_id> --json` prints it once the review finished."""
    data = json.loads(_fixture("demo-skill.json"))
    data["reviewRunId"] = run_id
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# Parsing real reviews
# ---------------------------------------------------------------------------


class TestParseCapturedReviews:
    def test_demo_skill(self):
        r = _review("demo-skill.json")
        assert r["status"] == "reviewed"
        assert r["run_id"] == "01a0e451-eb06-77aa-96cd-2cd02537c61a"
        assert r["review_score"] == 72
        # tessl's own human output for this review prints 38% and 93%:
        # normalizedScore 0.375 and 0.925 round half up, not to even.
        assert (r["description_score"], r["content_score"]) == (38, 93)
        assert r["validation"] == {"passed": True, "errors": 0, "warnings": 0, "findings": []}
        assert len(r["description_suggestions"]) == 3 and r["content_suggestions"] == []
        assert r["summary"] == (
            "reviewed — score 72% (description 38%, content 93%, validation passed: 0 errors, 0 warnings)"
        )
        assert r["warnings"] == ["Tessl Review description score 38% is below 60%"]

    def test_published_skf_skill(self):
        r = _review("oms-uitripled.json")
        assert (r["review_score"], r["description_score"], r["content_score"]) == (86, 93, 73)
        assert any("MANUAL" in s for s in r["content_suggestions"])
        assert r["warnings"] == []

    def test_xml_tag_description_passes_tessl_validation(self):
        """Tessl Review has no angle-bracket rule: create-skill's own §6 check is needed."""
        r = _review("bad-description.json")
        assert (r["review_score"], r["description_score"], r["content_score"]) == (29, 0, 26)
        assert r["validation"]["passed"] is True and r["validation"]["warnings"] == 2
        assert [f["name"] for f in r["validation"]["findings"]] == ["relative_links", "referenced_paths_exist"]
        assert len(r["warnings"]) == 3

    def test_threshold_miss_still_reviewed(self):
        r = mod.classify(_fixture("below-threshold.json"), _fixture("below-threshold.stderr"), 1)
        assert r["status"] == "reviewed" and r["review_score"] == 86

    def test_run_that_did_not_complete_is_failed(self):
        data = json.loads(_fixture("demo-skill.json"))
        data["status"] = "failed"
        r = mod.parse_review(data)
        assert r["status"] == "failed" and "ended with status 'failed'" in r["summary"]

    @pytest.mark.parametrize("score", [None, "72", True, 101, -1])
    def test_bad_review_score_is_parse_failure(self, score):
        data = json.loads(_fixture("demo-skill.json"))
        if score is None:
            del data["review"]
        else:
            data["review"]["reviewScore"] = score
        assert mod.parse_review(data)["status"] == "parse-failure"

    def test_failed_judge_scores_are_null(self):
        data = json.loads(_fixture("demo-skill.json"))
        data["judges"]["content"]["success"] = False
        r = mod.parse_review(data)
        assert r["content_score"] is None and "content n/a" in r["summary"]


class TestReviewInProgress:
    """The answers of `review run --no-wait --json` and `review view --json` before the review ends."""

    def test_submit_answer_is_pending(self):
        r = mod.classify(_fixture("submit-pending.json"), "", 0, workspace="skill-forge")
        assert r["status"] == "pending" and r["run_id"] == RUN_ID and r["workspace"] == "skill-forge"
        assert r["summary"] == (f"no result yet — Tessl Review run {RUN_ID} has not finished in workspace "
                                f"skill-forge (tessl review view {RUN_ID})")
        assert r["warnings"] == [f"Tessl Review: {r['summary']}"]
        assert r["review_score"] is None and r["validation"] is None

    def test_view_while_running_is_pending(self):
        r = mod.classify(_fixture("view-incomplete.json"), "", 0, run_id=RUN_ID)
        assert r["status"] == "pending" and r["run_id"] == RUN_ID

    def test_finished_view_is_reviewed(self):
        r = mod.classify(_completed(), "", 0, run_id=RUN_ID, workspace="skill-forge")
        assert r["status"] == "reviewed" and r["run_id"] == RUN_ID and r["workspace"] == "skill-forge"

    def test_unknown_run_id_is_named(self):
        r = mod.classify("", _fixture("view-unknown-run.stderr"), 1, run_id=UNKNOWN_ID)
        assert r["status"] == "unknown-run" and r["run_id"] == UNKNOWN_ID
        assert r["detail"] == f'Could not find review run "{UNKNOWN_ID}".'
        assert r["summary"].startswith(f"no result — Tessl has no review run {UNKNOWN_ID}")

    def test_in_progress_without_a_run_id_is_parse_failure(self):
        assert mod.classify('{"status": "pending"}', "", 0)["status"] == "parse-failure"


class TestClassifyWithoutJson:
    @pytest.mark.parametrize("stdout, stderr, code, status", [
        ("", REMOVED_STUB, 1, "command-unavailable"),
        ("", "No command registered for `run`", 251, "command-unavailable"),
        ("To get started, enter an existing repository and run tessl init.\n", SIGNED_OUT_STDERR, 1, "signed-out"),
        ("", "Error: workspace 'nope' not found\n", 1, "failed"),
        ("", "boom\n", 3, "failed"),
        ("not json\n", "", 0, "parse-failure"),
    ])
    def test_status(self, stdout, stderr, code, status):
        r = mod.classify(stdout, stderr, code)
        assert r["status"] == status
        assert r["warnings"] == [f"Tessl Review: {r['summary']}"]
        assert "\n" not in r["summary"]

    def test_workspace_error_names_the_preference(self):
        r = mod.classify("", "Error: workspace 'nope' not found\n", 1)
        assert r["summary"].startswith("failed — Error: workspace 'nope' not found")
        assert "tessl_review_workspace" in r["summary"]


# ---------------------------------------------------------------------------
# The preference
# ---------------------------------------------------------------------------


class TestPreference:
    @pytest.mark.parametrize("body, state", [
        (None, "off"),
        ("headless_mode: false\n", "off"),
        ("tessl_review_workspace: ~\n", "off"),
        ("tessl_review_workspace: ''\n", "off"),
        ("tessl_review_workspace: false\n", "off"),
        (": not yaml: [\n", "off"),
        ("- a list\n", "off"),
        ("tessl_review_workspace: skill-forge\n", "on"),
        ("tessl_review_workspace: true\n", "invalid"),
        ("tessl_review_workspace: '--force'\n", "invalid"),
        ("tessl_review_workspace: 'a b'\n", "invalid"),
        ("tessl_review_workspace: 7\n", "invalid"),
        # cmd.exe parses an npm .cmd shim's command line on Windows.
        ("tessl_review_workspace: 'a&calc'\n", "invalid"),
        ("tessl_review_workspace: 'a|b'\n", "invalid"),
        ("tessl_review_workspace: 'a^b'\n", "invalid"),
        ("tessl_review_workspace: '%USERPROFILE%'\n", "invalid"),
        ("tessl_review_workspace: '\"a\"'\n", "invalid"),
    ])
    def test_states(self, tmp_path, body, state):
        prefs = tmp_path / "preferences.yaml"
        if body is not None:
            prefs.write_bytes(body.encode("utf-8"))
        got, workspace, _ = mod.load_workspace(prefs)
        assert got == state
        assert (workspace == "skill-forge") == (state == "on")

    @pytest.mark.parametrize("name", ["skill-forge", "Team.Forge_2", "7forge"])
    def test_workspace_names_that_are_on(self, tmp_path, name):
        prefs = tmp_path / "preferences.yaml"
        prefs.write_bytes(f"tessl_review_workspace: '{name}'\n".encode("utf-8"))
        assert mod.load_workspace(prefs) == ("on", name, None)

    def test_shipped_template_is_off(self):
        assert mod.load_workspace(REPO / "src" / "forger" / "preferences.yaml") == ("off", None, None)


# ---------------------------------------------------------------------------
# submit and collect against a fake tessl
# ---------------------------------------------------------------------------


def _skill(tmp_path: Path) -> Path:
    skill = tmp_path / "stage" / "demo-skill"
    (skill / "references").mkdir(parents=True)
    (skill / "scripts").mkdir()
    (skill / "SKILL.md").write_bytes(b"---\nname: demo-skill\ndescription: Demo. Use when testing.\n---\n# Demo\n")
    (skill / "references" / "full-api.md").write_bytes(b"# API\n")
    (skill / "scripts" / "run.py").write_bytes(b"print(1)\n")
    for private in ("metadata.json", "context-snippet.md", "provenance-map.json", "evidence-report.md"):
        (skill / private).write_bytes(b"{}\n")
    return skill


def _prefs(tmp_path: Path, body: str = "tessl_review_workspace: skill-forge\n") -> Path:
    prefs = tmp_path / "preferences.yaml"
    prefs.write_bytes(body.encode("utf-8"))
    return prefs


class FakeTessl:
    """Stands in for mod._run, records every call and keeps a fake clock.

    `submit` answers `review run`; `views` answers successive `review view`
    calls, the last one repeating. The answer "timeout" (for any call)
    stands for a call that hits its time limit: the clock moves by that
    limit plus `kill_seconds`, the time the kill takes (up to KILL_WAIT_SEC
    on POSIX, twice that on Windows, where taskkill runs first).
    """

    def __init__(self, version=(0, "0.111.0\n", ""), whoami=(0, "ok\n", ""), submit=None, views=None,
                 view_seconds=2.0, kill_seconds=0.0):
        self.version, self.whoami = version, whoami
        self.submit = submit if submit is not None else (0, _fixture("submit-pending.json"), "")
        self.views = list(views) if views is not None else [(0, _fixture("view-incomplete.json"), ""),
                                                           (0, _completed(), "")]
        self.view_seconds = view_seconds
        self.kill_seconds = kill_seconds
        self.clock = 0.0
        self.sleeps: list[float] = []
        self.calls: list[list[str]] = []
        self.cwds: list[str] = []
        self.timeouts: list[float] = []
        self.uploaded: list[str] = []
        self.bundle_name = None

    def now(self) -> float:
        return self.clock

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.clock += seconds

    def views_made(self) -> list[list[str]]:
        return [c for c in self.calls if c[1:3] == ["review", "view"]]

    def __call__(self, cmd, timeout, cwd):
        self.calls.append(cmd)
        self.cwds.append(cwd)
        self.timeouts.append(timeout)
        if cmd[1] in ("--version", "whoami"):
            answer, seconds = (self.version if cmd[1] == "--version" else self.whoami), 0.5
        elif cmd[1:3] == ["review", "run"]:
            bundle = Path(cmd[3])
            self.uploaded = sorted(p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file())
            self.bundle_name = bundle.name
            answer, seconds = self.submit, 7.0
        else:
            answer = self.views.pop(0) if len(self.views) > 1 else self.views[0]
            seconds = self.view_seconds
        if answer == "timeout":
            self.clock += timeout + self.kill_seconds
            return None, "", "", True
        self.clock += seconds
        return (*answer, False)


def _patch(monkeypatch, fake, base=("tessl",)):
    monkeypatch.setattr(mod, "resolve_tessl", lambda: list(base) if base else None)
    monkeypatch.setattr(mod, "_run", fake)
    monkeypatch.setattr(mod, "_now", fake.now)
    monkeypatch.setattr(mod, "_sleep", fake.sleep)


def _submit(monkeypatch, tmp_path, fake, prefs_body="tessl_review_workspace: skill-forge\n", base=("tessl",)):
    _patch(monkeypatch, fake, base)
    return mod.submit_review(_skill(tmp_path), _prefs(tmp_path, prefs_body))


def _collect(monkeypatch, fake, run_id=RUN_ID, base=("tessl",), **kwargs):
    _patch(monkeypatch, fake, base)
    return mod.collect_review(run_id, "skill-forge", **kwargs)


class TestSubmit:
    def test_off_runs_nothing_even_with_tessl_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TESSL_WORKSPACE", "skill-forge")
        fake = FakeTessl()
        r = _submit(monkeypatch, tmp_path, fake, prefs_body="headless_mode: true\n")
        assert r["status"] == "off" and fake.calls == [] and r["warnings"] == []
        assert r["summary"] == "off — set tessl_review_workspace in preferences.yaml to enable"

    def test_invalid_runs_nothing(self, monkeypatch, tmp_path):
        fake = FakeTessl()
        r = _submit(monkeypatch, tmp_path, fake, prefs_body="tessl_review_workspace: true\n")
        assert r["status"] == "invalid-config" and fake.calls == []

    def test_not_installed(self, monkeypatch, tmp_path):
        assert _submit(monkeypatch, tmp_path, FakeTessl(), base=None)["status"] == "not-installed"

    def test_version_probe_failure_is_not_installed(self, monkeypatch, tmp_path):
        r = _submit(monkeypatch, tmp_path, FakeTessl(version=(1, "", "npm error canceled")))
        assert r["status"] == "not-installed"

    def test_signed_out_never_uploads(self, monkeypatch, tmp_path):
        fake = FakeTessl(whoami=(1, "Run tessl login to log in\n", SIGNED_OUT_STDERR))
        r = _submit(monkeypatch, tmp_path, fake)
        assert r["status"] == "signed-out" and r["detail"] == "You are not logged in"
        assert all(c[1] != "review" for c in fake.calls)

    def test_whoami_failure_that_is_not_sign_in_is_failed(self, monkeypatch, tmp_path):
        fake = FakeTessl(whoami=(1, "", "TypeError: fetch failed\n"))
        r = _submit(monkeypatch, tmp_path, fake)
        assert r["status"] == "failed" and "fetch failed" in r["summary"]
        assert all(c[1] != "review" for c in fake.calls)

    @pytest.mark.parametrize("probe, command", [("version", "tessl --version"), ("whoami", "tessl whoami")])
    def test_probe_that_does_not_answer_is_failed_and_uploads_nothing(self, monkeypatch, tmp_path, probe, command):
        """A slow npm launcher is not a missing tessl, and an unanswered sign-in check is not a sign-in."""
        fake = FakeTessl(**{probe: "timeout"})
        r = _submit(monkeypatch, tmp_path, fake)
        assert r["status"] == "failed"
        assert r["summary"] == f"failed — {command} did not answer within {mod.PROBE_TIMEOUT_SEC} seconds"
        assert all(c[1] != "review" for c in fake.calls) and fake.bundle_name is None

    def test_submit_argv_upload_and_isolation(self, monkeypatch, tmp_path):
        fake = FakeTessl()
        r = _submit(monkeypatch, tmp_path, fake)
        assert r["status"] == "pending" and r["run_id"] == RUN_ID
        assert (r["exit_code"], r["workspace"], r["tessl_version"]) == (0, "skill-forge", "0.111.0")
        review_cmd = fake.calls[-1]
        assert review_cmd[1:3] == ["review", "run"]
        assert review_cmd[4:] == ["--workspace", "skill-forge", "--no-wait", "--json"]
        assert not {"--force", "-f", "--threshold", "--label", "--wait"} & set(review_cmd)
        assert fake.timeouts == [mod.PROBE_TIMEOUT_SEC, mod.PROBE_TIMEOUT_SEC, mod.SUBMIT_TIMEOUT_SEC]
        assert fake.views_made() == [] and fake.sleeps == [], "submit never waits for the review"
        assert fake.bundle_name == "demo-skill"
        assert fake.uploaded == ["SKILL.md", "references/full-api.md", "scripts/run.py"]
        assert len(set(fake.cwds)) == 1
        cwd = fake.cwds[0]
        assert os.path.abspath(cwd) != os.path.abspath(os.getcwd())
        assert Path(review_cmd[3]).parent == Path(cwd)
        assert not Path(cwd).exists(), "the copy and its temporary folder are removed once submit returns"

    def test_cached_answer_is_reviewed_at_once(self, monkeypatch, tmp_path):
        r = _submit(monkeypatch, tmp_path, FakeTessl(submit=(0, _fixture("demo-skill.json"), "")))
        assert r["status"] == "reviewed" and r["review_score"] == 72 and r["workspace"] == "skill-forge"

    def test_nonzero_exit_with_json_is_reviewed(self, monkeypatch, tmp_path):
        fake = FakeTessl(submit=(1, _fixture("below-threshold.json"), _fixture("below-threshold.stderr")))
        r = _submit(monkeypatch, tmp_path, fake)
        assert r["status"] == "reviewed" and r["exit_code"] == 1

    def test_removed_review_command_is_named(self, monkeypatch, tmp_path):
        r = _submit(monkeypatch, tmp_path, FakeTessl(submit=(1, "", REMOVED_STUB)))
        assert r["status"] == "command-unavailable"
        assert r["warnings"] == [f"Tessl Review: {r['summary']}"]

    def test_submit_that_does_not_answer_is_failed(self, monkeypatch, tmp_path):
        r = _submit(monkeypatch, tmp_path, FakeTessl(submit="timeout"))
        assert r["status"] == "failed" and r["run_id"] is None
        assert f"did not answer within {mod.SUBMIT_TIMEOUT_SEC} seconds" in r["summary"]

    @pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privilege on Windows")
    def test_links_are_not_uploaded(self, monkeypatch, tmp_path):
        secret = tmp_path / "secret.txt"
        secret.write_bytes(b"private\n")
        fake = FakeTessl()
        _patch(monkeypatch, fake)
        skill = _skill(tmp_path)
        (skill / "references" / "leak.md").symlink_to(secret)
        (skill / "assets").symlink_to(tmp_path)
        mod.submit_review(skill, _prefs(tmp_path))
        assert fake.uploaded == ["SKILL.md", "references/full-api.md", "scripts/run.py"]

    @pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privilege on Windows")
    def test_linked_skill_md_is_refused(self, monkeypatch, tmp_path):
        fake = FakeTessl()
        _patch(monkeypatch, fake)
        skill = _skill(tmp_path)
        real = tmp_path / "elsewhere.md"
        real.write_bytes((skill / "SKILL.md").read_bytes())
        (skill / "SKILL.md").unlink()
        (skill / "SKILL.md").symlink_to(real)
        r = mod.submit_review(skill, _prefs(tmp_path))
        assert r["status"] == "failed" and all(c[1] != "review" for c in fake.calls)


INCOMPLETE = (0, _fixture("view-incomplete.json"), "")


FETCH_FAILED = (1, "", "TypeError: fetch failed\n")


class TestCollect:
    def test_collects_a_finished_review(self, monkeypatch):
        fake = FakeTessl()
        r = _collect(monkeypatch, fake, tessl_version="0.111.0")
        assert r["status"] == "reviewed" and r["run_id"] == RUN_ID and r["review_score"] == 72
        assert (r["workspace"], r["tessl_version"], r["exit_code"]) == ("skill-forge", "0.111.0", 0)
        assert fake.calls == [["tessl", "review", "view", RUN_ID, "--json"]] * 2, "collect runs only review view"
        assert fake.sleeps == [mod.POLL_INTERVAL_SEC]
        assert len(set(fake.cwds)) == 1 and os.path.abspath(fake.cwds[0]) != os.path.abspath(os.getcwd())
        assert not Path(fake.cwds[0]).exists()

    def test_a_tessl_version_that_would_hang_is_never_asked(self, monkeypatch):
        fake = FakeTessl(version="timeout", whoami="timeout")
        assert _collect(monkeypatch, fake)["status"] == "reviewed"
        assert all(c[1:3] == ["review", "view"] for c in fake.calls)

    def test_still_running_is_pending(self, monkeypatch):
        fake = FakeTessl(views=[INCOMPLETE])
        r = _collect(monkeypatch, fake, tessl_version="0.111.0")
        assert r["status"] == "pending" and r["run_id"] == RUN_ID and r["workspace"] == "skill-forge"
        assert r["tessl_version"] == "0.111.0" and r["detail"] is None
        assert r["warnings"] == [f"Tessl Review: {r['summary']}"]
        assert len(fake.views_made()) >= 2

    def test_final_turns_a_running_review_into_timeout(self, monkeypatch):
        r = _collect(monkeypatch, FakeTessl(views=[INCOMPLETE]), final=True)
        assert r["status"] == "timeout" and r["run_id"] == RUN_ID
        assert r["summary"] == (f"no result — Tessl Review run {RUN_ID} did not finish while SKF waited; it "
                                f"may still finish in workspace skill-forge (tessl review view {RUN_ID})")
        assert r["warnings"] == [f"Tessl Review: {r['summary']}"]

    def test_final_keeps_a_finished_review(self, monkeypatch):
        assert _collect(monkeypatch, FakeTessl(), final=True)["status"] == "reviewed"

    @pytest.mark.parametrize("first", [FETCH_FAILED, (0, "Fetching review...\n", ""), "timeout"],
                             ids=["error", "no-json", "timeout"])
    def test_a_failed_check_is_tried_again(self, monkeypatch, first):
        """One network error must not throw away a review Tessl is still finishing."""
        fake = FakeTessl(views=[first, (0, _completed(), "")])
        r = _collect(monkeypatch, fake)
        assert r["status"] == "reviewed" and r["review_score"] == 72
        assert len(fake.views_made()) == 2 and fake.sleeps == [mod.POLL_INTERVAL_SEC]

    @pytest.mark.parametrize("final, status", [(False, "pending"), (True, "timeout")])
    def test_checks_that_keep_failing_keep_the_run(self, monkeypatch, final, status):
        fake = FakeTessl(views=[FETCH_FAILED], view_seconds=0.5)
        r = _collect(monkeypatch, fake, final=final)
        assert r["status"] == status and r["run_id"] == RUN_ID and RUN_ID in r["summary"]
        assert r["detail"] == "tessl review view: TypeError: fetch failed" and r["exit_code"] == 1
        # A fast error still waits POLL_INTERVAL_SEC before the next check.
        assert set(fake.sleeps) == {mod.POLL_INTERVAL_SEC}
        assert 2 <= len(fake.views_made()) <= 1 + mod.COLLECT_MAX_SEC // mod.POLL_INTERVAL_SEC

    def test_a_tessl_that_cannot_start_ends_the_call(self, monkeypatch):
        fake = FakeTessl(views=[(None, "", "cannot start tessl: [Errno 2] No such file or directory")])
        r = _collect(monkeypatch, fake)
        assert r["status"] == "failed" and r["run_id"] == RUN_ID and len(fake.views_made()) == 1

    @pytest.mark.parametrize("answer, seconds", [
        (INCOMPLETE, 0.5), (INCOMPLETE, 2.0), (INCOMPLETE, 9.0), (INCOMPLETE, 19.9), (FETCH_FAILED, 0.5),
        (FETCH_FAILED, 19.9), ("timeout", None),
    ])
    @pytest.mark.parametrize("kill_waits", [0, 1, 2])
    @pytest.mark.parametrize("max_seconds", [None, 0, 10_000])
    def test_one_collect_stays_within_its_budget(self, monkeypatch, answer, seconds, kill_waits, max_seconds):
        """However long each view and each kill takes, and whatever --max-seconds asks, one collect ends in time.

        The budget starts before the first view, and a view starts only while
        it and the pause before it fit, so only the kill after the last view
        can overrun it (by KILL_WAIT_SEC on POSIX, twice that on Windows).
        """
        kill = kill_waits * mod.KILL_WAIT_SEC
        fake = FakeTessl(views=[answer], view_seconds=seconds, kill_seconds=kill)
        kwargs = {} if max_seconds is None else {"max_seconds": max_seconds}
        r = _collect(monkeypatch, fake, **kwargs)
        assert r["status"] == "pending"
        budget = mod.COLLECT_MAX_SEC if max_seconds is None else min(max_seconds, mod.COLLECT_MAX_SEC)
        assert fake.clock <= max(budget, mod.VIEW_TIMEOUT_SEC) + kill
        assert fake.clock <= mod.COLLECT_MAX_SEC + 2 * mod.KILL_WAIT_SEC
        assert set(fake.timeouts) == {mod.VIEW_TIMEOUT_SEC}
        if answer == "timeout":
            assert r["detail"] == f"tessl review view did not answer within {mod.VIEW_TIMEOUT_SEC} seconds"

    def test_no_budget_means_one_view(self, monkeypatch):
        fake = FakeTessl(views=[INCOMPLETE])
        assert _collect(monkeypatch, fake, max_seconds=0)["status"] == "pending"
        assert len(fake.views_made()) == 1 and fake.sleeps == []

    def test_unknown_run_id(self, monkeypatch):
        fake = FakeTessl(views=[(1, "", _fixture("view-unknown-run.stderr"))])
        r = _collect(monkeypatch, fake, run_id=UNKNOWN_ID)
        assert r["status"] == "unknown-run" and r["run_id"] == UNKNOWN_ID and r["exit_code"] == 1
        assert len(fake.views_made()) == 1 and fake.sleeps == []

    @pytest.mark.parametrize("run_id", ["--force", "", "a b", "-x", "../x", "id\n"])
    def test_malformed_run_id_runs_nothing(self, monkeypatch, run_id):
        fake = FakeTessl()
        r = _collect(monkeypatch, fake, run_id=run_id)
        assert r["status"] == "unknown-run" and fake.calls == []
        assert r["summary"].startswith(_reference_prefixes()["unknown-run"]), "tessl-review.md names its start"
        assert "\n" not in r["summary"]

    def test_view_of_a_failed_run_is_failed(self, monkeypatch):
        data = json.loads(_completed())
        data["status"] = "failed"
        fake = FakeTessl(views=[(1, json.dumps(data), "")])
        r = _collect(monkeypatch, fake)
        assert r["status"] == "failed" and r["run_id"] == RUN_ID and RUN_ID in r["summary"]
        assert len(fake.views_made()) == 1, "a run Tessl reports as failed is not checked again"

    def test_signed_out_view(self, monkeypatch):
        fake = FakeTessl(views=[(1, "", SIGNED_OUT_STDERR)])
        r = _collect(monkeypatch, fake)
        assert r["status"] == "signed-out" and r["run_id"] == RUN_ID and len(fake.views_made()) == 1

    def test_not_installed(self, monkeypatch):
        r = _collect(monkeypatch, FakeTessl(), base=None, tessl_version="0.111.0")
        assert r["status"] == "not-installed" and r["run_id"] == RUN_ID and r["tessl_version"] == "0.111.0"


def _reference_prefixes() -> dict[str, str]:
    rows = re.findall(r"^\| `([a-z-]+)` \| `([^`]+)` \|", _read(REFERENCE), re.M)
    return dict(rows)


@pytest.mark.parametrize("status", mod.STATUSES)
def test_every_status_carries_every_key(monkeypatch, tmp_path, status):
    submits = {
        "reviewed": dict(fake=FakeTessl(submit=(0, _fixture("demo-skill.json"), ""))),
        "pending": dict(fake=FakeTessl()),
        "off": dict(fake=FakeTessl(), prefs_body="headless_mode: false\n"),
        "invalid-config": dict(fake=FakeTessl(), prefs_body="tessl_review_workspace: true\n"),
        "not-installed": dict(fake=FakeTessl(), base=None),
        "signed-out": dict(fake=FakeTessl(whoami=(1, "", SIGNED_OUT_STDERR))),
        "command-unavailable": dict(fake=FakeTessl(submit=(1, "", REMOVED_STUB))),
        "failed": dict(fake=FakeTessl(submit=(3, "", "boom\n"))),
        "parse-failure": dict(fake=FakeTessl(submit=(0, "not json\n", ""))),
    }
    collects = {
        "unknown-run": dict(fake=FakeTessl(views=[(1, "", _fixture("view-unknown-run.stderr"))])),
        "timeout": dict(fake=FakeTessl(views=[INCOMPLETE]), final=True),
    }
    if status in submits:
        r = _submit(monkeypatch, tmp_path, **submits[status])
    else:
        r = _collect(monkeypatch, **collects[status])
    assert r["status"] == status
    assert tuple(r) == mod.RESULT_KEYS
    assert (r["review_score"] is not None) == (status == "reviewed")
    assert r["summary"].startswith(_reference_prefixes()[status]), "tessl-review.md names each summary's start"


class TestUnreadableFiles:
    @pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                        reason="POSIX permissions; root reads everything")
    def test_unreadable_folder_fails_instead_of_uploading_less(self, monkeypatch, tmp_path):
        fake = FakeTessl()
        _patch(monkeypatch, fake)
        skill = _skill(tmp_path)
        refs = skill / "references"
        refs.chmod(0)
        try:
            r = mod.submit_review(skill, _prefs(tmp_path))
        finally:
            refs.chmod(0o755)
        assert r["status"] == "failed" and "cannot copy" in r["summary"]
        assert all(c[1] != "review" for c in fake.calls)


class TestRealSubprocess:
    """_run against real child processes, with a Python stand-in for tessl."""

    def _fake(self, tmp_path, body: str) -> list[str]:
        script = tmp_path / "fake_tessl.py"
        script.write_bytes(textwrap.dedent(body).encode("utf-8"))
        return [sys.executable, str(script)]

    def test_end_to_end_submit_then_collect(self, monkeypatch, tmp_path):
        done = tmp_path / "done.json"
        done.write_bytes(_completed().encode("utf-8"))
        seen = tmp_path / "bundle-path.txt"
        base = self._fake(tmp_path, f"""
            import os, sys
            if sys.argv[1] == "--version": print("Downloading 0.111.0 for linux-x64"); print("0.111.0")
            elif sys.argv[1] == "whoami": print("ok")
            elif sys.argv[2] == "run":
                assert os.path.realpath(os.getcwd()) == os.path.realpath(os.path.dirname(sys.argv[3]))
                assert os.path.isfile(os.path.join(sys.argv[3], "SKILL.md"))
                open({str(seen)!r}, "w", encoding="utf-8").write(sys.argv[3])
                print('{{"reviewRunId": "{RUN_ID}", "status": "pending"}}')
            else:
                assert sys.argv[2:] == ["view", "{RUN_ID}", "--json"]
                assert os.path.realpath(os.getcwd()) != os.path.realpath({str(REPO)!r})
                sys.stdout.write(open({str(done)!r}, encoding="utf-8").read())
            """)
        monkeypatch.setattr(mod, "resolve_tessl", lambda: base)
        r = mod.submit_review(_skill(tmp_path), _prefs(tmp_path))
        assert r["status"] == "pending" and r["run_id"] == RUN_ID and r["tessl_version"] == "0.111.0"
        assert not Path(seen.read_text(encoding="utf-8")).exists(), "submit removes the copy"
        r = mod.collect_review(r["run_id"], r["workspace"], max_seconds=0, tessl_version=r["tessl_version"])
        assert r["status"] == "reviewed" and r["review_score"] == 72 and r["workspace"] == "skill-forge"
        assert r["tessl_version"] == "0.111.0"

    @pytest.mark.parametrize("call", ["submit", "collect"])
    def test_time_limit_stops_tessl_and_what_it_started(self, monkeypatch, tmp_path, call):
        """POSIX kills the process group, Windows runs taskkill /T: either way the grandchild dies.

        The grandchild gets the marker path as an argument, not inside its
        code, so a Windows path's backslashes cannot turn the code into a
        SyntaxError that would pass this test without killing anything.
        """
        marker = tmp_path / "grandchild-survived"
        base = self._fake(tmp_path, f"""
            import subprocess, sys, time
            if sys.argv[1] in ("--version", "whoami"): print("0.111.0"); sys.exit(0)
            subprocess.Popen([sys.executable, "-c",
                              "import pathlib, sys, time; time.sleep(3); pathlib.Path(sys.argv[1]).write_text('x')",
                              {str(marker)!r}])
            time.sleep(60)
            """)
        monkeypatch.setattr(mod, "resolve_tessl", lambda: base)
        monkeypatch.setattr(mod, "SUBMIT_TIMEOUT_SEC", 1)
        monkeypatch.setattr(mod, "VIEW_TIMEOUT_SEC", 1)
        start = time.monotonic()
        if call == "submit":
            r = mod.submit_review(_skill(tmp_path), _prefs(tmp_path))
            assert r["status"] == "failed" and "did not answer within 1 seconds" in r["summary"]
        else:
            r = mod.collect_review(RUN_ID, "skill-forge", max_seconds=0)
            assert r["status"] == "pending" and "did not answer within 1 seconds" in r["detail"]
        assert time.monotonic() - start < 20
        time.sleep(4)
        assert not marker.exists()

    def test_windows_kill_uses_taskkill_tree(self, monkeypatch):
        calls = []
        monkeypatch.setattr(mod, "_resolve_outside_cwd", lambda name: "taskkill" if name == "taskkill" else None)
        monkeypatch.setattr(mod.subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw.get("timeout"))))

        class Proc:
            pid = 4242
            killed = False

            def kill(self):
                self.killed = True

        proc = Proc()
        mod._kill_tree(proc, windows=True)
        assert calls == [(["taskkill", "/F", "/T", "/PID", "4242"], mod.KILL_WAIT_SEC)] and proc.killed


# ---------------------------------------------------------------------------
# Finding tessl (every submit and collect test above replaces the lookup)
# ---------------------------------------------------------------------------


def _stub(folder: Path, name: str, marker: Path | None = None) -> None:
    """A command `name` in folder, as a POSIX script and a Windows .cmd, that appends to marker when run."""
    folder.mkdir(parents=True, exist_ok=True)
    script = folder / name
    script.write_bytes(("#!/bin/sh\n" + (f"echo ran >> '{marker}'\n" if marker else "") + "exit 0\n").encode("utf-8"))
    script.chmod(0o755)
    (folder / f"{name}.cmd").write_bytes(
        ("@echo off\r\n" + (f'echo ran >> "{marker}"\r\n' if marker else "") + "exit /b 0\r\n").encode("utf-8"))


class TestResolveTessl:
    """tessl on PATH first, else npx that only runs a tessl it already has, never a shim in the current folder."""

    def _lookup(self, monkeypatch, tmp_path, *names):
        bin_dir, project = tmp_path / "bin", tmp_path / "project"
        bin_dir.mkdir()
        project.mkdir()
        for name in names:
            _stub(bin_dir, name)
        monkeypatch.setenv("PATH", str(bin_dir))
        monkeypatch.chdir(project)
        return bin_dir, mod.resolve_tessl()

    def test_tessl_on_path_comes_first(self, monkeypatch, tmp_path):
        bin_dir, argv = self._lookup(monkeypatch, tmp_path, "tessl", "npx")
        assert argv is not None and len(argv) == 1, argv
        assert Path(argv[0]).parent == bin_dir and Path(argv[0]).stem == "tessl"

    def test_npx_never_installs_tessl(self, monkeypatch, tmp_path):
        """--no-install: npx runs a tessl it already has or fails, so SKF never downloads tessl."""
        bin_dir, argv = self._lookup(monkeypatch, tmp_path, "npx")
        assert argv is not None and Path(argv[0]).parent == bin_dir and Path(argv[0]).stem == "npx"
        assert argv[1:] == ["--no-install", "tessl"]
        assert not {"-y", "--yes"} & set(argv)

    def test_neither_is_none(self, monkeypatch, tmp_path):
        assert self._lookup(monkeypatch, tmp_path)[1] is None

    def test_shims_in_the_current_folder_are_not_found(self, monkeypatch, tmp_path):
        """shutil.which on Windows searches the current folder, the user's project, ahead of PATH."""
        project = tmp_path / "project"
        _stub(project, "tessl")
        _stub(project, "npx")
        monkeypatch.setenv("PATH", str(project))
        monkeypatch.chdir(project)
        assert mod.resolve_tessl() is None

    @pytest.mark.skipif(os.name == "nt", reason="POSIX shell shim")
    def test_submit_never_runs_a_shim_in_the_current_folder(self, tmp_path):
        project, marker = tmp_path / "project", tmp_path / "shim-ran"
        _stub(project, "tessl", marker)
        _stub(project, "npx", marker)
        res = subprocess.run(
            [sys.executable, str(HELPER), "submit", str(_skill(tmp_path)), "--preferences", str(_prefs(tmp_path))],
            capture_output=True, cwd=project, env={**os.environ, "PATH": str(project)})
        assert res.returncode == 0, res.stderr
        payload = json.loads(res.stdout)
        assert (payload["status"], payload["detail"]) == ("not-installed", "neither tessl nor npx is on PATH")
        assert not marker.exists(), "a shim in the current folder ran"


class TestCli:
    def _cli(self, *args, env=None):
        return subprocess.run([sys.executable, str(HELPER), *args], capture_output=True, env=env)

    def test_parse_subcommand_prints_utf8(self):
        res = self._cli("parse", str(FIXTURES / "demo-skill.json"), env={**os.environ, "PYTHONIOENCODING": "ascii"})
        assert res.returncode == 0
        payload = json.loads(res.stdout.decode("utf-8"))
        assert payload["review_score"] == 72 and payload["summary"].startswith("reviewed — score")

    def test_parse_reads_a_pending_answer(self):
        res = self._cli("parse", str(FIXTURES / "submit-pending.json"))
        assert res.returncode == 0 and json.loads(res.stdout)["status"] == "pending"

    def test_submit_off(self, tmp_path):
        res = self._cli("submit", str(_skill(tmp_path)), "--preferences", str(tmp_path / "missing.yaml"))
        assert res.returncode == 0 and json.loads(res.stdout)["status"] == "off"

    def test_collect_refuses_a_malformed_run_id(self):
        res = self._cli("collect", "a b", "--workspace", "skill-forge", "--tessl-version", "0.111.0",
                        "--max-seconds", "0", "--final")
        assert res.returncode == 0
        payload = json.loads(res.stdout)
        assert payload["status"] == "unknown-run"
        assert (payload["workspace"], payload["tessl_version"]) == ("skill-forge", "0.111.0")

    @pytest.mark.parametrize("given", ["", "null", " None "])
    def test_collect_reads_a_rendered_null_as_none(self, given):
        res = self._cli("collect", "a b", "--workspace", given, "--tessl-version", given)
        payload = json.loads(res.stdout)
        assert (payload["workspace"], payload["tessl_version"]) == (None, None)

    def test_blocking_run_subcommand_is_gone(self, tmp_path):
        """One call that waits for a whole review would outlast a two-minute shell limit."""
        res = self._cli("run", str(_skill(tmp_path)), "--preferences", str(tmp_path / "missing.yaml"))
        assert res.returncode == 2 and res.stdout == b""


# ---------------------------------------------------------------------------
# Workflow wiring (prose pins: step files are otherwise untested)
# ---------------------------------------------------------------------------

CS = REPO / "src" / "skf-create-skill"
TS = REPO / "src" / "skf-test-skill"
VALIDATE = CS / "references" / "validate.md"
EXTERNAL = TS / "references" / "external-validators.md"
REFERENCE = REPO / "src" / "shared" / "references" / "tessl-review.md"
HELPER_PROBE = [
    "{project-root}/_bmad/skf/shared/scripts/skf-tessl-review.py",
    "{project-root}/src/shared/scripts/skf-tessl-review.py",
]
RULES_PROBE = [
    "{project-root}/_bmad/skf/shared/references/tessl-review.md",
    "{project-root}/src/shared/references/tessl-review.md",
]
BINDINGS = {
    "{tessl_status}": "status",
    "{tessl_summary}": "summary",
    "{tessl_warnings}": "warnings",
    "{tessl_workspace}": "workspace",
    "{tessl_version}": "tessl_version",
    "{tessl_run_id}": "run_id",
    "{tessl_review_score}": "review_score",
    "{tessl_description_score}": "description_score",
    "{tessl_content_score}": "content_score",
    "{tessl_validation}": "validation",
    "{tessl_description_suggestions}": "description_suggestions",
    "{tessl_content_suggestions}": "content_suggestions",
}
BINDING_RE = re.compile(r"^- `(\{[a-z_]+\})` ← `([a-z_.]+)`$", re.M)
COLLECT_CMD = ('uv run {tesslReviewHelper} collect "{tessl_run_id}" --workspace "{tessl_workspace}" '
               '--tessl-version "{tessl_version}"')
COUNT_WORDS = {3: ("three", "third"), 4: ("four", "fourth"), 5: ("five", "fifth"), 6: ("six", "sixth"),
               7: ("seven", "seventh"), 8: ("eight", "eighth")}
VALIDATOR_CMD = 'uv run {frontmatterValidator} "<staging-skill-dir>/SKILL.md" --forbid-angle-brackets'
SANITIZE_CMD = 'uv run {descriptionGuardHelper} sanitize "<staging-skill-dir>/SKILL.md"'
HALT_MESSAGE = "Description sanitization failed — "
STOPPED = "failed — stopped before skf-tessl-review.py reported a result"
# A call the shell tool stops replaces the pending values the calls before it bound.
SHELL_FALLBACK = ("If the shell tool stops a call before it prints its JSON, or it prints none, make that the last "
                  f"call: set `{{tessl_status}}` to `failed`, `{{tessl_summary}}` to `{STOPPED}` and "
                  "`{tessl_warnings}` to the one line `Tessl Review: {tessl_summary}`, keep `{tessl_run_id}` and "
                  "the other values the calls before it bound,")
MISSING_HELPER = ("If neither path exists, set `{tessl_summary}` to `not run — skf-tessl-review.py is missing` and "
                  "`{tessl_warnings}` to the one line `Tessl Review: {tessl_summary}`,")
RETIRED = ("tessl skill review", "tesslDismissal", "tessl-dismissal-rules", "[TESSL:", 'confidence: "TESSL"',
           "tessl-suggestions", "Content-Quality Gate")


def _read(path: Path) -> str:
    assert path.is_file(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    assert text.count(start) == 1, f"{start!r} must occur exactly once"
    body = text.split(start, 1)[1]
    assert end in body, f"{end!r} must follow {start!r}"
    body = body.split(end, 1)[0]
    assert body.strip(), f"empty section after {start!r}"
    return body


def _frontmatter_text(path: Path) -> str:
    match = re.match(r"^---\n(.*?)\n---\n", _read(path), re.S)
    assert match, f"{path} has no frontmatter"
    return match.group(1)


def _shipped_text_files():
    files = [REPO / "README.md", REPO / "CONTRIBUTING.md"]
    for root in (REPO / "src", REPO / "docs", REPO / "tools"):
        files += [p for p in root.rglob("*")
                  if p.suffix in {".md", ".py", ".js", ".mjs", ".toml", ".yaml", ".yml", ".csv", ".json"}
                  and "node_modules" not in p.parts]
    return files


class TestWorkflowWiring:
    def test_retired_tessl_machinery_is_gone(self):
        assert not (CS / "assets" / "tessl-dismissal-rules.md").exists()
        hits = sorted({f"{p.relative_to(REPO).as_posix()}: {token}" for p in _shipped_text_files()
                       for token in RETIRED if token in p.read_text(encoding="utf-8", errors="replace")})
        assert hits == []

    def test_step_files_reach_tessl_only_through_the_helper(self):
        """No step file runs tessl itself: no `npx … tessl`, and no command line that starts with tessl."""
        npx = re.compile(r"npx\b[^\n`]*\btessl\b")
        command = re.compile(r"^\s*(?:timeout\s+\S+\s+)?tessl\s", re.M)
        hits = sorted(p.relative_to(REPO).as_posix() for p in (REPO / "src").glob("skf-*/**/*.md")
                      if npx.search(p.read_text(encoding="utf-8")) or command.search(p.read_text(encoding="utf-8")))
        assert hits == []

    @pytest.mark.parametrize("subcommand", ["submit", "collect"])
    def test_helper_call_sites_are_exactly_two(self, subcommand):
        sites = sorted(p.relative_to(REPO).as_posix() for p in (REPO / "src").rglob("*.md")
                       if f"{{tesslReviewHelper}} {subcommand}" in p.read_text(encoding="utf-8"))
        assert sites == ["src/skf-create-skill/references/validate.md",
                         "src/skf-test-skill/references/external-validators.md"]

    @pytest.mark.parametrize("path", [VALIDATE, EXTERNAL])
    def test_probe_orders_and_preferences(self, path):
        fm_text = _frontmatter_text(path)
        fm = yaml.safe_load(fm_text)
        assert fm["tesslReviewProbeOrder"] == HELPER_PROBE
        assert fm["tesslReviewRulesProbeOrder"] == RULES_PROBE
        assert fm["preferencesFile"] == "{sidecar_path}/preferences.yaml"
        block = _section(fm_text, "# Resolve `{tesslReviewHelper}`", "preferencesFile:")
        assert "HALT" not in block, "the review is advisory: its probe orders never halt"

    @pytest.mark.parametrize("path, start, end, submit", [
        (VALIDATE, "### 6b. Tessl Review (optional)", "### 7. Validate metadata.json",
         'uv run {tesslReviewHelper} submit "<staging-skill-dir>" --preferences "{preferencesFile}"'),
        (EXTERNAL, "### 3. Run Tessl Review (optional)", "### 4. Calculate Combined External Score",
         'uv run {tesslReviewHelper} submit "{skillDir}" --preferences "{preferencesFile}"'),
    ])
    def test_helper_calls_and_bindings(self, path, start, end, submit):
        section = _section(_read(path), start, end)
        # The only commands: one submit, then collect while pending, the last collect with --final.
        commands = re.findall(r"^```bash\n(.*?)\n```$", section, re.M | re.S)
        assert commands == [submit, COLLECT_CMD]
        count, ordinal = COUNT_WORDS[mod.MAX_COLLECTS]
        assert "While `{tessl_status}` is `pending`, collect the review" in section
        assert f"at most {count} times, and add `--final` to the {ordinal} call" in section
        # Every call fits a shell tool's default limit: nothing asks for a longer one.
        assert f"up to {mod.COLLECT_MAX_SEC} seconds" in section
        assert "with your shell tool's default time limit" in section
        for longer in ("600000", "ten-minute", "10-minute", "ten minutes"):
            assert longer not in section
        assert SHELL_FALLBACK in section and MISSING_HELPER in section
        assert "record `Tessl Review:" not in section, "every recorded line goes through {tessl_summary}"
        assert "HALT" not in section
        # Names the tessl command next to the reviewed folder (the staging-validate-promote memory note keys on it).
        assert "(`tessl review run`, which the helper below runs on a copy of `" in section
        assert "from the `submit` JSON and again from each `collect` JSON" in section
        bound = dict(BINDING_RE.findall(section))
        assert bound == BINDINGS
        assert set(bound.values()) <= set(mod.RESULT_KEYS)
        assert "After the last call," in section and "each entry of `{tessl_warnings}`" in section

    @pytest.mark.parametrize("path, rule", [
        (VALIDATE, "the `## Tessl Review` section holds only its Result line and, when `{tessl_run_id}` is set, "
                   "its Workspace line"),
        (EXTERNAL, "the Tessl Review block holds only its Result line and, when `{tessl_run_id}` is set, its "
                   "Run line"),
    ])
    def test_reports_keep_the_run_id_of_an_unfinished_review(self, path, rule):
        """Only the report's run line tells the user which review to look up with tessl review view."""
        assert f"When `{{tessl_status}}` is not `reviewed`, {rule}" in _read(path)
        assert "holds only its Result line." not in _read(path)

    def test_combined_score_uses_the_bound_scores(self):
        section = _section(_read(EXTERNAL), "### 4. Calculate Combined External Score", "### 5. ")
        assert "Pass `skill_check_score` as `skillCheckScore` and `{tessl_review_score}` as `tesslReviewScore`" in section
        assert "Bind `{external_score}` ← `externalScore`" in section
        assert "`{external_tools_used}` ← `toolsUsed`" in section
        append = _section(_read(EXTERNAL), "### 5. Write the External Validation Section", "### 6. Report Results")
        assert "### Tessl Review\n- **Result:** {tessl_summary}\n" in append
        assert "- **Tools used:** {external_tools_used}" in append
        # The combined score reaches the scoring script as the file §4 writes, never copied by hand.
        assert '--output "{run_dir}/external.json"' in section
        score = _read(TS / "references" / "score.md")
        assert '--external "{run_dir}/external.json"' in score
        assert "{external_validation_score" not in score and "{external_score" not in score
        assert "{skill-check and Tessl Review | skill-check only | Tessl Review only | none" in score

    def test_reuse_never_skips_tessl_review_or_the_combine(self):
        section = _section(_read(EXTERNAL), "### 1b. ", "### 2. Run skill-check")
        assert "skip section 2 and continue at section 3" in section
        assert "Never reuse a Tessl Review result" in section
        assert "Skip to section 5" not in section

    def test_description_check_prose(self):
        text = _read(VALIDATE)
        check = _section(text, "### 6. Description Angle-Bracket Check", "### 6b. Tessl Review (optional)")
        assert VALIDATOR_CMD in check and SANITIZE_CMD in check
        for binding in ("`{description_angle_brackets}` ← `description_angle_brackets`",
                        "`{angle_bracket_substitutions}` ← `substitutions`",
                        "`{angle_brackets_sanitized}` ← `sanitized`",
                        "`{sanitized_description}` ← `description`"):
            assert binding in check
        assert 'summary.halt_reason: "description-angle-brackets"' in check
        assert f'HALT** with: "{HALT_MESSAGE}' in check
        assert "--captured-description" not in check, "the description never goes through the shell"
        hook = _section(text, "**This skill's post-restore re-validation hook:**", "### 1. Check Tool Availability")
        assert "--forbid-angle-brackets" not in hook, "§6 owns the check; the §0 hook must not flip Schema to FAIL"
        comment = _section(_frontmatter_text(VALIDATE), "# Resolve `{frontmatterValidator}`",
                           "frontmatterValidatorProbeOrder:")
        assert "HALT if neither resolves" in comment
        halts = _section(_read(CS / "references" / "report.md"), "### Result Contract on HARD HALT", "### 6. ")
        assert "`description-angle-brackets`" in halts and "frontmatter-validator helper unresolved" in halts

    def test_description_check_contract(self, tmp_path):
        """The §6 commands, run for real, find and clear the angle brackets."""
        check = _section(_read(VALIDATE), "### 6. Description Angle-Bracket Check", "### 6b. Tessl Review (optional)")
        flags = re.search(r'uv run \{frontmatterValidator\} "<staging-skill-dir>/SKILL.md"((?: --[a-z-]+)+)', check)
        assert flags, "the §6 validator command must be quoted in the prose"
        sub = re.search(r'uv run \{descriptionGuardHelper\} (\S+) "<staging-skill-dir>/SKILL.md"', check)
        assert sub, "the §6 guard command must be quoted in the prose"
        stage = tmp_path / "demo-skill"
        stage.mkdir()
        skill_md = stage / "SKILL.md"
        skill_md.write_bytes(
            b'---\nname: demo-skill\ndescription: "Maps `Array<T>` values for $HOME. Use when mapping arrays."\n'
            b"---\n\n# Demo\n")

        def validate():
            res = subprocess.run([sys.executable, str(VALIDATOR), str(skill_md), *flags.group(1).split()],
                                 capture_output=True, text=True, encoding="utf-8")
            return res.returncode, json.loads(res.stdout)

        code, before = validate()
        assert code == 1 and before["description_angle_brackets"] == 2
        res = subprocess.run([sys.executable, str(GUARD), sub.group(1), str(skill_md)],
                             capture_output=True, text=True, encoding="utf-8")
        assert res.returncode == 0, res.stderr
        fixed = json.loads(res.stdout)
        assert (fixed["substitutions"], fixed["sanitized"]) == (2, True)
        assert fixed["description"] == "Maps `Array{T}` values for $HOME. Use when mapping arrays."
        code, after = validate()
        assert code == 0 and after["description_angle_brackets"] == 0
        assert after["frontmatter"]["description"] == fixed["description"]

    def test_troubleshooting_heading_matches_the_halt(self):
        check = _section(_read(VALIDATE), "### 6. Description Angle-Bracket Check", "### 6b. Tessl Review (optional)")
        heading = f'### "{HALT_MESSAGE.split(" — ")[0]}"'
        assert heading in _read(REPO / "docs" / "troubleshooting.md")
        assert HALT_MESSAGE in check

    def test_evidence_rows_match_the_template(self):
        rows = _section(_read(VALIDATE), "## Validation Results\n", "\n\n## Quality Score Breakdown")
        template = _section(_read(CS / "assets" / "skill-sections.md"), "## Validation Results\n",
                            "\n\n## Quality Score Breakdown")
        assert rows == template
        assert "- Description angle brackets: {none | re-sanitized ({count} substitutions) | not checked — no description}" in rows
        assert "- Tessl Review: {tessl_summary}" in rows and "Content Quality" not in rows
        for text in (_read(VALIDATE), _read(CS / "assets" / "skill-sections.md")):
            assert "## Tessl Review\n- Result: {tessl_summary}\n" in text

    def test_create_skill_gates_match_the_step_files(self):
        skill = _read(CS / "SKILL.md")
        rows = re.findall(r"^\| (\w+) \| [^|]+ \| (references/[\w/.-]+\.md) \| ([^|]+) \|$", skill, re.M)
        assert len(rows) >= 10
        gates_row = next(line for line in skill.splitlines() if line.startswith("| **Gates** |"))
        for number, rel, auto in rows:
            has_gate = bool(re.search(r"\*\*GATE \[default: [^\]]+\]\*\*", _read(CS / rel)))
            assert has_gate == (auto.strip() != "Yes"), f"Stages row {number} ({rel}) says {auto.strip()!r}"
            assert has_gate == (f"step {number}:" in gates_row), f"Gates row and step {number} ({rel}) disagree"

    def test_compile_rationale_names_the_real_rule(self):
        compile_md = _read(CS / "references" / "compile.md")
        sanitize = _section(compile_md, "### 2a. Description Sanitization Pass", "### 3. Build context-snippet.md Content")
        assert "Claude platform" in sanitize and "step 6 §6" in sanitize
        rules = _read(CS / "assets" / "compile-assembly-rules.md")
        assert "Claude platform" in rules
        for text in (compile_md, rules):
            assert "description_field" not in text
        assert "Exactly one gate can still fire" not in compile_md
        assert "replaces that line if a later decision lands" not in compile_md

    def test_reference_and_troubleshooting_name_every_status(self):
        reference = _read(REFERENCE)
        assert set(_reference_prefixes()) == set(mod.STATUSES)
        assert f"below {mod.SCORE_FLOOR}%" in reference
        count, ordinal = COUNT_WORDS[mod.MAX_COLLECTS]
        assert f"up to {mod.COLLECT_MAX_SEC} seconds" in reference
        assert f"collects at most {count} times" in reference and f"its {ordinal} call passes `--final`" in reference
        assert "--no-wait --json" in reference and "tessl review view <run id> --json" in reference
        trouble = _section(_read(REPO / "docs" / "troubleshooting.md"),
                           "### A report says `Tessl Review: off`, `not run`, `no result` or `failed`", "\n### ")
        documented = set(re.findall(r"^\| `([a-z-]+)` \|", trouble, re.M))
        assert documented == set(mod.STATUSES) - {"reviewed"}
        for needle in ("tessl_review_workspace", "tessl login", "TESSL_TOKEN", "credits", "tessl review view",
                       "did not answer within", "stopped before skf-tessl-review.py reported a result",
                       "something that is not a run id", "letters, digits, `.`, `_` and `-`"):
            assert needle in trouble
        assert f"`{STOPPED}`" in reference and "letters, digits, `.`, `_` and `-`" in reference
        assert STOPPED.startswith(_reference_prefixes()["failed"])

    def test_every_call_fits_a_two_minute_shell_limit(self):
        """Hosts whose shell tool stops a command after two minutes must get every result.

        submit: the version and sign-in probes, then the submission; only the
        call that hits its limit is killed. collect runs only views: a view
        starts only while it and the pause before it still fit in the budget,
        so its waiting stays within max(budget, one view) plus one kill;
        TestCollect checks that on a fake clock.
        """
        kill = 2 * mod.KILL_WAIT_SEC  # taskkill, then the wait for the child
        submit = 2 * mod.PROBE_TIMEOUT_SEC + mod.SUBMIT_TIMEOUT_SEC + kill
        collect = max(mod.COLLECT_MAX_SEC, mod.VIEW_TIMEOUT_SEC) + kill
        assert max(submit, collect) <= 100, "leave room under 120 s for uv, Python and the copy"
        assert mod.POLL_INTERVAL_SEC + mod.VIEW_TIMEOUT_SEC < mod.COLLECT_MAX_SEC, "a collect can view twice"

    def test_docs_describe_the_opt_in(self):
        assert "`tessl_review_workspace: ~`" in _read(REPO / "src" / "skf-setup" / "references" / "write-config.md")
        started = _read(REPO / "docs" / "getting-started.md")
        assert re.search(r"^\| `tessl_review_workspace` +\|", started, re.M) and "one runtime preference" not in started
        security = _section(_read(REPO / "docs" / "architecture.md"), "## Security", "\n---\n")
        assert "tessl_review_workspace" in security
        assert "Tessl Review when you opt in" in _read(REPO / "docs" / "workflows.md")
        assert "Headless never turns Tessl Review on" in _read(REPO / "docs" / "workflows.md")
        assert "**Tessl Review is optional.**" in _read(REPO / "docs" / "verifying-a-skill.md")
        quick = [line for line in _read(REPO / "docs" / "skill-model.md").splitlines() if line.startswith("| **Quick** |")]
        assert len(quick) == 1 and "`tessl` when you opt in to Tessl Review" in quick[0]
        assert "content quality review" not in quick[0]

    def test_tool_counts_agree(self):
        arch = _read(REPO / "docs" / "architecture.md")
        count = int(re.search(r"^### (\d+) Tools$", arch, re.M).group(1))
        table = _section(arch, f"### {count} Tools\n", "\n\n")
        assert len(re.findall(r"^\| \*\*`", table, re.M)) == count
        assert f"Runtime flow, {count} tools," in _read(REPO / "README.md")
        assert f"the {count} tools and which one wins when they disagree" in _read(REPO / "docs" / "how-it-works.md")
