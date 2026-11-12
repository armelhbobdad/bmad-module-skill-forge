#!/usr/bin/env python3
"""Tests for skf-health-check-seen.py: the shared health check's fingerprints
and seen-issue cache (#1122).

src/shared/health-check.md used to have the model hash both fingerprints
through a sha1sum, shasum or python chain, read $HOME/.skf/health-check-seen.json,
map a bounded `gh issue view` through five branches and two legacy demotions,
and merge its record back by hand. The helper owns all of that now, so these
tests pin its behaviour instead of the prose:

- fingerprint: the golden hashes, and the rules that exit 2.
- lookup: every branch, the legacy demotions, a cache that is not usable,
  with the gh call replaced in the loaded module (no test runs the gh a
  developer has installed), and end to end against a fake gh first on PATH
  (POSIX only: the fake is a script).
- record: the merge, the never-downgraded resolved record and the
  --regression call that replaces one, a corrupt cache set aside, the lock,
  the failure paths, the Windows rename retry, and eight parallel writers.

No test reads or writes the real $HOME/.skf: every call names its cache, or
runs with HOME pointed at a temporary folder.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HELPER = REPO / "src" / "shared" / "scripts" / "skf-health-check-seen.py"
RUN_LOCK = REPO / "src" / "shared" / "scripts" / "skf-run-lock.py"
SHARED_HEALTH_CHECK = REPO / "src" / "shared" / "health-check.md"

# The worked example of the fingerprint prose test: two different defects in the only section of one step file.
SAMPLE = {"severity": "gap", "workflow": "skf-test-skill",
          "step_file": "src/skf-test-skill/references/inventory-contract.md",
          "section": "documented-inventory-contract"}
FP_A, FP_B, LEGACY = "fp-a54e7a6", "fp-ed2bb67", "fp-eb2d6f2"
OTHER_FP = "fp-1234567"
URL = "https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1"
DAY = "2026-11-12"
# JSON nested past the parser's depth: json.loads raises RecursionError, not ValueError.
DEEP = b"[" * 200_000

_MODULE = None


def _mod():
    """Load the helper lazily, so a missing helper fails each test, not collection."""
    global _MODULE
    if _MODULE is None:
        assert HELPER.is_file(), f"missing helper: {HELPER}"
        spec = importlib.util.spec_from_file_location("skf_health_check_seen", HELPER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _MODULE = module
    return _MODULE


def _cli(*args: str, env: dict | None = None, timeout: float = 60) -> tuple[int, str, str]:
    proc = subprocess.run([sys.executable, str(HELPER), *args], capture_output=True, text=True, encoding="utf-8",
                          env=env, timeout=timeout, stdin=subprocess.DEVNULL)
    return proc.returncode, proc.stdout, proc.stderr


def _fingerprint_args(**over: str) -> list[str]:
    values = {**SAMPLE, "defect_key": "const-holding-function", **over}
    return ["fingerprint", "--severity", values["severity"], "--workflow", values["workflow"],
            "--step-file", values["step_file"], "--section", values["section"], "--defect-key", values["defect_key"]]


def _write_cache(path: Path, data) -> Path:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def _live(action: str = "created", url: str | None = URL) -> dict:
    record = {"action": action, "date": "2026-10-01"}
    if url is not None:
        record["issue_url"] = url
    return record


@pytest.fixture
def no_gh(monkeypatch):
    """gh_issue_state replaced by a recorder that fails the test when called."""
    calls = []

    def fake(issue_url, timeout=None):
        calls.append(issue_url)
        raise AssertionError(f"gh must not run here, got {issue_url!r}")

    monkeypatch.setattr(_mod(), "gh_issue_state", fake)
    return calls


@pytest.fixture
def gh_answer(monkeypatch):
    """gh_issue_state replaced by one that answers with the value set on it, recording each URL."""
    state = {"answer": None, "calls": []}

    def fake(issue_url, timeout=None):
        state["calls"].append(issue_url)
        return state["answer"]

    monkeypatch.setattr(_mod(), "gh_issue_state", fake)
    return state


# --------------------------------------------------------------------------
# fingerprint
# --------------------------------------------------------------------------


class TestFingerprint:
    def test_the_golden_fingerprints(self):
        """The prose test's worked example: the key keeps two defects of one section apart."""
        a = _mod().fingerprint(defect_key="const-holding-function", **SAMPLE)
        b = _mod().fingerprint(defect_key="shared-text", **SAMPLE)
        assert a == {"fp": FP_A, "legacy_fp": LEGACY}
        assert b == {"fp": FP_B, "legacy_fp": LEGACY}

    def test_the_hash_is_sha1_over_the_joined_fields(self):
        """Cross-checked with hashlib on the setup test's key, so the field order and the separator show here."""
        key = "bug|skf-setup|references/report.md|emit-headless-json-envelope|result-envelope"
        out = _mod().fingerprint("bug", "skf-setup", "references/report.md", "emit-headless-json-envelope",
                                 "result-envelope")
        assert out["fp"] == "fp-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:7]
        legacy = key.rsplit("|", 1)[0]
        assert out["legacy_fp"] == "fp-" + hashlib.sha1(legacy.encode("utf-8")).hexdigest()[:7]

    def test_the_cli_prints_both_fingerprints(self):
        code, out, err = _cli(*_fingerprint_args(defect_key="shared-text"))
        assert code == 0, err
        assert json.loads(out) == {"fp": FP_B, "legacy_fp": LEGACY}
        assert err == ""

    @pytest.mark.parametrize("over, rule", [
        ({"severity": "nit"}, "--severity"),
        ({"defect_key": "one-two-three-four-five"}, "--defect-key"),
        ({"defect_key": "Shared-Text"}, "--defect-key"),
        ({"section": "Missing Path"}, "--section"),
        ({"section": "missing--path"}, "--section"),
        ({"workflow": "skf|test-skill"}, "--workflow"),
        ({"workflow": ""}, "--workflow"),
        ({"step_file": "references/a.md\nb"}, "--step-file"),
        ({"step_file": "references/a.md|b"}, "--step-file"),
        # `$` alone matches before a final newline: each rule is a fullmatch.
        ({"section": "documented-inventory-contract\n"}, "--section"),
        ({"defect_key": "shared-text\n"}, "--defect-key"),
    ])
    def test_a_value_that_breaks_its_rule_exits_2(self, over, rule):
        code, out, err = _cli(*_fingerprint_args(**over))
        assert code == 2
        assert out == ""
        error = json.loads(err)
        assert error["status"] == "error" and rule in error["message"]

    def test_a_four_word_key_is_allowed(self):
        code, out, err = _cli(*_fingerprint_args(defect_key="very-long-helper-name"))
        assert code == 0, err
        assert json.loads(out)["legacy_fp"] == LEGACY


# --------------------------------------------------------------------------
# lookup: the branches, with the gh call replaced
# --------------------------------------------------------------------------


class TestLookupBranches:
    @pytest.mark.parametrize("content", [None, b"", b"   \n", b"[]", b"{bad", b'"text"',
                                         b"\xff\xfe{}", '{"fp-a54e7a6": {"action": "created\xff"}}'.encode("latin-1"),
                                         pytest.param(DEEP, id="nested-past-the-parsers-depth")])
    def test_no_usable_cache_is_unseen(self, tmp_path, no_gh, content):
        cache = tmp_path / "seen.json"
        if content is not None:
            cache.write_bytes(content)
        assert _mod().lookup(FP_A, LEGACY, cache) == {"verdict": "unseen", "record": None, "matched_on": None}
        assert no_gh == []

    def test_a_folder_in_place_of_the_cache_is_an_empty_cache(self, tmp_path, no_gh):
        cache = tmp_path / "seen.json"
        cache.mkdir()
        assert _mod().lookup(FP_A, LEGACY, cache)["verdict"] == "unseen"

    def test_neither_key_present_is_unseen(self, tmp_path, no_gh):
        cache = _write_cache(tmp_path / "seen.json", {OTHER_FP: _live()})
        assert _mod().lookup(FP_A, LEGACY, cache) == {"verdict": "unseen", "record": None, "matched_on": None}

    def test_a_resolved_record_is_a_regression_without_gh(self, tmp_path, no_gh):
        record = {"action": "resolved", "issue_url": URL, "date": "2026-10-02"}
        cache = _write_cache(tmp_path / "seen.json", {FP_A: record})
        assert _mod().lookup(FP_A, LEGACY, cache) == {"verdict": "regression", "record": record, "matched_on": "fp"}

    @pytest.mark.parametrize("action", ["created", "reacted", "commented"])
    @pytest.mark.parametrize("answer, verdict", [
        ({"state": "CLOSED", "stateReason": "COMPLETED"}, "regression"),
        ({"state": "MERGED", "stateReason": ""}, "regression"),
        ({"state": "MERGED"}, "regression"),
        ({"state": "OPEN", "stateReason": ""}, "handled"),
        ({"state": "OPEN", "stateReason": "REOPENED"}, "handled"),
        ({"state": "CLOSED", "stateReason": "NOT_PLANNED"}, "handled"),
        ({"state": "CLOSED", "stateReason": "DUPLICATE"}, "handled"),
        ({"state": "CLOSED", "stateReason": None}, "handled"),
        (None, "handled"),  # any failure: no gh, the time limit, a non-zero exit, junk
    ])
    def test_a_live_record_asks_the_issue(self, tmp_path, gh_answer, action, answer, verdict):
        record = _live(action)
        cache = _write_cache(tmp_path / "seen.json", {FP_A: record})
        gh_answer["answer"] = answer
        assert _mod().lookup(FP_A, LEGACY, cache) == {"verdict": verdict, "record": record, "matched_on": "fp"}
        assert gh_answer["calls"] == [URL]

    @pytest.mark.parametrize("url", ["", None])
    @pytest.mark.parametrize("action", ["created", "reacted", "commented"])
    def test_a_live_record_without_a_url_is_handled_without_gh(self, tmp_path, no_gh, action, url):
        record = _live(action, url)
        cache = _write_cache(tmp_path / "seen.json", {FP_A: record})
        assert _mod().lookup(FP_A, LEGACY, cache) == {"verdict": "handled", "record": record, "matched_on": "fp"}

    @pytest.mark.parametrize("url", ["--web", "http://github.com/o/r/issues/1", "https://github.com/o/r/issues/1 --web",
                                     "  ", 12])
    def test_a_url_gh_may_not_take_counts_as_a_failure(self, tmp_path, no_gh, url):
        """A value starting with `-` would reach gh as a flag."""
        cache = _write_cache(tmp_path / "seen.json", {FP_A: _live("created", url)})
        assert _mod().lookup(FP_A, LEGACY, cache)["verdict"] == "handled"

    @pytest.mark.parametrize("record", [{"issue_url": URL, "date": DAY}, {"action": "queued", "issue_url": URL},
                                        {"action": "Created", "issue_url": URL}, None, "created", ["created"], 7])
    def test_an_odd_record_is_unrecognized(self, tmp_path, no_gh, record):
        cache = _write_cache(tmp_path / "seen.json", {FP_A: record})
        assert _mod().lookup(FP_A, LEGACY, cache) == {"verdict": "unrecognized", "record": record,
                                                      "matched_on": "fp"}

    @pytest.mark.parametrize("answer", [{"state": "OPEN"}, None])
    def test_a_legacy_record_that_would_suppress_is_unseen(self, tmp_path, gh_answer, answer):
        record = _live("reacted")
        cache = _write_cache(tmp_path / "seen.json", {LEGACY: record})
        gh_answer["answer"] = answer
        assert _mod().lookup(FP_A, LEGACY, cache) == {"verdict": "unseen", "record": record,
                                                      "matched_on": "legacy_fp"}

    def test_a_legacy_record_without_a_url_is_unseen(self, tmp_path, no_gh):
        record = _live("created", "")
        cache = _write_cache(tmp_path / "seen.json", {LEGACY: record})
        assert _mod().lookup(FP_A, LEGACY, cache)["verdict"] == "unseen"

    def test_a_legacy_resolved_record_is_a_possible_regression(self, tmp_path, no_gh):
        record = {"action": "resolved", "issue_url": URL, "date": "2026-10-02"}
        cache = _write_cache(tmp_path / "seen.json", {LEGACY: record})
        assert _mod().lookup(FP_A, LEGACY, cache) == {"verdict": "possible-regression", "record": record,
                                                      "matched_on": "legacy_fp"}

    def test_a_legacy_record_whose_issue_was_completed_is_a_possible_regression(self, tmp_path, gh_answer):
        cache = _write_cache(tmp_path / "seen.json", {LEGACY: _live("commented")})
        gh_answer["answer"] = {"state": "CLOSED", "stateReason": "COMPLETED"}
        assert _mod().lookup(FP_A, LEGACY, cache)["verdict"] == "possible-regression"

    def test_a_legacy_odd_record_stays_unrecognized(self, tmp_path, no_gh):
        cache = _write_cache(tmp_path / "seen.json", {LEGACY: {"action": "queued"}})
        assert _mod().lookup(FP_A, LEGACY, cache) == {"verdict": "unrecognized", "record": {"action": "queued"},
                                                      "matched_on": "legacy_fp"}

    def test_the_fp_record_wins_over_the_legacy_one(self, tmp_path, gh_answer):
        fp_record = _live("created")
        legacy = {"action": "resolved", "issue_url": "https://github.com/o/r/issues/2", "date": "2026-10-02"}
        cache = _write_cache(tmp_path / "seen.json", {LEGACY: legacy, FP_A: fp_record})
        gh_answer["answer"] = {"state": "OPEN"}
        assert _mod().lookup(FP_A, LEGACY, cache) == {"verdict": "handled", "record": fp_record, "matched_on": "fp"}
        assert gh_answer["calls"] == [URL]

    def test_an_fp_key_holding_null_is_a_record(self, tmp_path, no_gh):
        """The key is present, so the legacy record is never consulted."""
        cache = _write_cache(tmp_path / "seen.json", {FP_A: None, LEGACY: {"action": "resolved"}})
        assert _mod().lookup(FP_A, LEGACY, cache) == {"verdict": "unrecognized", "record": None, "matched_on": "fp"}

    @pytest.mark.parametrize("flag, value", [("--fp", "fp-A54E7A6"), ("--fp", "a54e7a6"), ("--legacy-fp", "fp-eb2d6f"),
                                             ("--legacy-fp", "fp-eb2d6f2x"), ("--fp", FP_A + "\n"),
                                             ("--legacy-fp", LEGACY + "\n")])
    def test_a_bad_fingerprint_exits_2(self, tmp_path, flag, value):
        args = {"--fp": FP_A, "--legacy-fp": LEGACY, flag: value}
        code, out, err = _cli("lookup", "--fp", args["--fp"], "--legacy-fp", args["--legacy-fp"],
                              "--cache", str(tmp_path / "seen.json"))
        assert code == 2 and out == ""
        assert flag in json.loads(err)["message"]


# --------------------------------------------------------------------------
# lookup end to end: the real gh call against a fake gh first on PATH
# --------------------------------------------------------------------------

FAKE_GH = """#!{python}
import json, os, sys, time
with open(os.environ["FAKE_GH_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
mode = os.environ.get("FAKE_GH_MODE", "")
if mode == "hang":
    time.sleep(30)
    sys.exit(0)
if mode == "fail":
    print("GraphQL: Could not resolve to an issue or pull request", file=sys.stderr)
    sys.exit(1)
if mode == "junk":
    print("not json")
    sys.exit(0)
print(mode)
"""


@pytest.fixture
def fake_gh(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("the fake gh is a POSIX script")
    folder = tmp_path / "bin"
    folder.mkdir()
    script = folder / "gh"
    script.write_bytes(FAKE_GH.format(python=sys.executable).encode("utf-8"))
    script.chmod(0o755)
    log = tmp_path / "gh.log"
    monkeypatch.setenv("PATH", f"{folder}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    monkeypatch.setenv("FAKE_GH_MODE", "")
    return log


def _logged(log: Path) -> list:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _must_not_run(argv, timeout):
    """A replacement for skf-source-tree.py's _run that fails the test when anything is started."""
    raise AssertionError(f"nothing may be started here, got {argv!r}")


class TestGhEndToEnd:
    def test_the_call_gh_gets(self, fake_gh, monkeypatch):
        monkeypatch.setenv("FAKE_GH_MODE", json.dumps({"state": "CLOSED", "stateReason": "COMPLETED"}))
        assert _mod().gh_issue_state(URL) == {"state": "CLOSED", "stateReason": "COMPLETED"}
        assert _logged(fake_gh) == [["issue", "view", URL, "--json", "state,stateReason"]]

    @pytest.mark.parametrize("mode", ["fail", "junk", "[]", '{"stateReason": "COMPLETED"}'])
    def test_a_failed_answer_is_none(self, fake_gh, monkeypatch, mode):
        monkeypatch.setenv("FAKE_GH_MODE", mode)
        assert _mod().gh_issue_state(URL) is None

    def test_a_hanging_gh_is_stopped_at_the_limit(self, fake_gh, monkeypatch):
        monkeypatch.setenv("FAKE_GH_MODE", "hang")
        start = time.monotonic()
        assert _mod().gh_issue_state(URL, 1.0) is None
        assert time.monotonic() - start < 20

    def test_the_limit_is_ten_seconds(self):
        assert _mod().GH_TIMEOUT_SEC == 10.0

    def test_lookup_hands_gh_the_ten_second_limit(self, tmp_path, fake_gh, monkeypatch):
        """The limit lookup passes reaches skf-source-tree.py's _run, which stops a hanging gh there.
        The wrapper runs the real _run with a 1-second cap, so the test does not wait the 10."""
        monkeypatch.setenv("FAKE_GH_MODE", "hang")
        tree = _mod()._load(_mod().SOURCE_TREE_HELPER)
        real_run = tree._run
        limits = []

        def capped(argv, timeout):
            limits.append(timeout)
            return real_run(argv, 1.0)

        monkeypatch.setattr(tree, "_run", capped)
        cache = _write_cache(tmp_path / "seen.json", {FP_A: _live("created")})
        start = time.monotonic()
        assert _mod().lookup(FP_A, LEGACY, cache) == {"verdict": "handled", "record": _live("created"),
                                                      "matched_on": "fp"}
        assert time.monotonic() - start < 20
        assert limits == [10.0]
        assert len(_logged(fake_gh)) == 1

    def test_no_gh_is_none(self, monkeypatch):
        tree = _mod()._load(_mod().SOURCE_TREE_HELPER)
        monkeypatch.setattr(tree, "_resolve_outside_cwd", lambda _name: None)
        monkeypatch.setattr(tree, "_run", _must_not_run)
        assert _mod().gh_issue_state(URL) is None

    def test_a_gh_planted_in_the_current_folder_is_not_run(self, monkeypatch):
        """shutil.which on Windows searches the current folder ahead of PATH: a gh.CMD that the repository a
        workflow runs in plants there reads as no gh, and nothing is started."""
        tree = _mod()._load(_mod().SOURCE_TREE_HELPER)
        monkeypatch.setattr(tree.shutil, "which", lambda _name, *_a, **_k: os.path.join(os.getcwd(), "gh.CMD"))
        monkeypatch.setattr(tree, "_run", _must_not_run)
        assert _mod().gh_issue_state(URL) is None

    @pytest.mark.parametrize("mode, verdict", [
        (json.dumps({"state": "CLOSED", "stateReason": "COMPLETED"}), "regression"),
        (json.dumps({"state": "MERGED", "stateReason": ""}), "regression"),
        (json.dumps({"state": "OPEN", "stateReason": ""}), "handled"),
        (json.dumps({"state": "CLOSED", "stateReason": "NOT_PLANNED"}), "handled"),
        ("fail", "handled"),
        ("junk", "handled"),
    ])
    def test_the_cli_lookup(self, tmp_path, fake_gh, monkeypatch, mode, verdict):
        monkeypatch.setenv("FAKE_GH_MODE", mode)
        cache = _write_cache(tmp_path / "seen.json", {FP_A: _live("created")})
        code, out, err = _cli("lookup", "--fp", FP_A, "--legacy-fp", LEGACY, "--cache", str(cache))
        assert code == 0, err
        assert json.loads(out) == {"verdict": verdict, "record": _live("created"), "matched_on": "fp"}
        assert len(_logged(fake_gh)) == 1

    def test_the_cli_runs_no_gh_without_a_live_record(self, tmp_path, fake_gh):
        cache = _write_cache(tmp_path / "seen.json", {FP_A: {"action": "resolved"}, FP_B: _live("created", "")})
        for fp, verdict in ((FP_A, "regression"), (FP_B, "handled"), (OTHER_FP, "unseen")):
            code, out, err = _cli("lookup", "--fp", fp, "--legacy-fp", LEGACY, "--cache", str(cache))
            assert code == 0, err
            assert json.loads(out)["verdict"] == verdict
        assert _logged(fake_gh) == []


# --------------------------------------------------------------------------
# record
# --------------------------------------------------------------------------


def _record(cache: Path, *extra: str, fp: str = FP_A, action: str = "created", url: str = URL,
            day: str = DAY) -> tuple[int, str, str]:
    return _cli("record", "--fp", fp, "--action", action, "--issue-url", url, "--date", day, "--cache", str(cache),
                *extra)


class TestRecord:
    def test_a_first_record_creates_the_folder_and_the_file(self, tmp_path):
        cache = tmp_path / "home" / ".skf" / "health-check-seen.json"
        code, out, err = _record(cache)
        assert code == 0, err
        new = {"issue_url": URL, "action": "created", "date": DAY}
        assert json.loads(out) == {"written": True, "fp": FP_A, "record": new, "set_aside": None}
        assert json.loads(cache.read_text(encoding="utf-8")) == {FP_A: new}
        assert sorted(p.name for p in cache.parent.iterdir()) == ["health-check-seen.json"]

    def test_the_merge_sets_one_key_and_keeps_the_rest(self, tmp_path):
        others = {
            LEGACY: {"action": "created", "issue_url": "https://github.com/o/r/issues/9", "date": "2026-01-01"},
            OTHER_FP: {"action": "resolved", "issue_url": "", "date": "2026-02-02", "note": "kept"},
            "not-a-fingerprint": [1, 2, 3],
            FP_A: {"action": "created", "issue_url": "https://github.com/o/r/issues/3", "date": "2026-03-03"},
        }
        cache = _write_cache(tmp_path / "seen.json", others)
        code, out, err = _record(cache, action="reacted")
        assert code == 0, err
        after = json.loads(cache.read_text(encoding="utf-8"))
        assert after[FP_A] == {"issue_url": URL, "action": "reacted", "date": DAY}
        assert {k: v for k, v in after.items() if k != FP_A} == {k: v for k, v in others.items() if k != FP_A}
        assert list(after) == list(others), "the keys keep their order"
        assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"], "no temp, lock or guard file is left"

    def test_record_never_writes_a_legacy_key(self, tmp_path):
        legacy = {"action": "resolved", "issue_url": URL, "date": "2026-01-01"}
        cache = _write_cache(tmp_path / "seen.json", {LEGACY: legacy})
        code, _, err = _record(cache)
        assert code == 0, err
        assert json.loads(cache.read_text(encoding="utf-8"))[LEGACY] == legacy

    @pytest.mark.parametrize("action, extra", [("reacted", ()), ("commented", ()), ("created", ())])
    def test_a_resolved_record_is_never_downgraded(self, tmp_path, action, extra):
        resolved = {"action": "resolved", "issue_url": URL, "date": "2026-10-02"}
        cache = _write_cache(tmp_path / "seen.json", {FP_A: resolved, OTHER_FP: _live()})
        before = cache.read_bytes()
        code, out, err = _record(cache, *extra, action=action, url="https://github.com/o/r/issues/5")
        assert code == 0, err
        assert json.loads(out) == {"written": False, "fp": FP_A, "record": resolved, "set_aside": None}
        assert cache.read_bytes() == before

    def test_the_regression_issue_replaces_a_resolved_record(self, tmp_path):
        resolved = {"action": "resolved", "issue_url": URL, "date": "2026-10-02"}
        cache = _write_cache(tmp_path / "seen.json", {FP_A: resolved, OTHER_FP: _live()})
        new_url = "https://github.com/o/r/issues/5"
        code, out, err = _record(cache, "--regression", url=new_url)
        assert code == 0, err
        new = {"issue_url": new_url, "action": "created", "date": DAY}
        assert json.loads(out) == {"written": True, "fp": FP_A, "record": new, "set_aside": None}
        assert json.loads(cache.read_text(encoding="utf-8")) == {FP_A: new, OTHER_FP: _live()}

    def test_regression_on_a_record_that_is_not_resolved_writes_as_usual(self, tmp_path):
        cache = _write_cache(tmp_path / "seen.json", {FP_A: _live("created")})
        code, out, err = _record(cache, "--regression")
        assert code == 0, err
        assert json.loads(out)["written"] is True

    @pytest.mark.parametrize("content", [b"{bad", b"[]", b'"text"', b"\xff\xfe{}",
                                         pytest.param(DEEP, id="nested-past-the-parsers-depth")])
    def test_a_corrupt_cache_is_set_aside(self, tmp_path, content):
        cache = tmp_path / "seen.json"
        cache.write_bytes(content)
        code, out, err = _record(cache)
        assert code == 0, err
        result = json.loads(out)
        aside = Path(result["set_aside"])
        assert aside.parent == tmp_path and aside.name.startswith("seen.json.corrupt-")
        assert len(aside.name) == len("seen.json.corrupt-20261112T101500Z")
        assert aside.read_bytes() == content
        assert json.loads(cache.read_text(encoding="utf-8")) == {FP_A: {"issue_url": URL, "action": "created",
                                                                       "date": DAY}}
        assert sorted(p.name for p in tmp_path.iterdir()) == sorted(["seen.json", aside.name])

    def test_a_second_set_aside_never_overwrites_the_first(self, tmp_path):
        cache = tmp_path / "seen.json"
        first = _mod()._set_aside(_bytes(cache, b"{one"))
        second = _mod()._set_aside(_bytes(cache, b"{two"))
        assert first != second
        assert first.read_bytes() == b"{one" and second.read_bytes() == b"{two"

    @pytest.mark.parametrize("content", [b"", b"  \n"])
    def test_an_empty_cache_is_not_set_aside(self, tmp_path, content):
        cache = tmp_path / "seen.json"
        cache.write_bytes(content)
        code, out, err = _record(cache)
        assert code == 0, err
        assert json.loads(out)["set_aside"] is None
        assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"]

    def test_a_bom_cache_is_read(self, tmp_path):
        cache = tmp_path / "seen.json"
        cache.write_bytes(b"\xef\xbb\xbf" + json.dumps({OTHER_FP: _live()}).encode("utf-8"))
        code, out, err = _record(cache)
        assert code == 0, err
        assert json.loads(out)["set_aside"] is None
        assert set(json.loads(cache.read_text(encoding="utf-8"))) == {OTHER_FP, FP_A}

    @pytest.mark.parametrize("over, rule", [
        ({"fp": "fp-12345"}, "--fp"),
        ({"fp": FP_A + "\n"}, "--fp"),
        ({"url": "http://github.com/o/r/issues/1"}, "--issue-url"),
        ({"url": "--web"}, "--issue-url"),
        ({"url": "https://github.com/o/r/issues/1 x"}, "--issue-url"),
        ({"day": "2026-02-30"}, "--date"),
        ({"day": "20261112"}, "--date"),
        ({"day": "12/11/2026"}, "--date"),
        ({"day": DAY + "\n"}, "--date"),
        ({"action": "resolved"}, "--action"),
        ({"action": "queued"}, "--action"),
    ])
    def test_a_value_that_breaks_its_rule_exits_2(self, tmp_path, over, rule):
        cache = tmp_path / "seen.json"
        code, out, err = _record(cache, **over)
        assert code == 2 and out == ""
        assert rule in json.loads(err)["message"]
        assert not cache.exists()

    @pytest.mark.parametrize("action", ["reacted", "commented"])
    def test_a_reaction_on_the_recurrence_replaces_a_resolved_record(self, tmp_path, action):
        """After a regression verdict, [R] or [C] on an open issue that reports the defect: that issue tracks the
        recurrence now, so later sessions skip the finding instead of asking about the same issue again."""
        resolved = {"action": "resolved", "issue_url": URL, "date": "2026-10-02"}
        cache = _write_cache(tmp_path / "seen.json", {FP_A: resolved, OTHER_FP: _live()})
        open_issue = "https://github.com/o/r/issues/6"
        code, out, err = _record(cache, "--regression", action=action, url=open_issue)
        assert code == 0, err
        new = {"issue_url": open_issue, "action": action, "date": DAY}
        assert json.loads(out) == {"written": True, "fp": FP_A, "record": new, "set_aside": None}
        assert json.loads(cache.read_text(encoding="utf-8")) == {FP_A: new, OTHER_FP: _live()}

    def test_a_cache_that_cannot_be_read_exits_1(self, tmp_path):
        cache = tmp_path / "seen.json"
        cache.mkdir()
        code, out, err = _record(cache)
        assert code == 1 and out == ""
        assert json.loads(err)["status"] == "error"
        assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"], "no lock, guard or temp file is left"

    def test_a_corrupt_cache_that_cannot_be_set_aside_is_kept(self, tmp_path, monkeypatch, capsys):
        """Writing over it would lose the records a user can still repair, so nothing is written."""
        cache = _bytes(tmp_path / "seen.json", b"{bad")
        real_replace = os.replace

        def replace(src, dst):
            if ".corrupt-" in Path(dst).name:
                raise PermissionError(13, "Access is denied", str(dst))
            return real_replace(src, dst)

        monkeypatch.setattr(_mod(), "_IS_WINDOWS", False)
        monkeypatch.setattr(_mod().os, "replace", replace)
        code = _mod().main(["record", "--fp", FP_A, "--action", "created", "--issue-url", URL, "--date", DAY,
                            "--cache", str(cache)])
        captured = capsys.readouterr()
        assert code == 1 and captured.out == ""
        assert "cannot set aside" in json.loads(captured.err)["message"]
        assert cache.read_bytes() == b"{bad"
        assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"], "no .corrupt-*, lock or temp file"

    def test_a_failed_write_leaves_no_lock_and_no_temp_file(self, tmp_path, monkeypatch, capsys):
        cache = _write_cache(tmp_path / "seen.json", {OTHER_FP: _live()})
        before = cache.read_bytes()
        real_replace = os.replace

        def replace(src, dst):
            if Path(dst) == cache:
                raise PermissionError(13, "Access is denied", str(dst))
            return real_replace(src, dst)

        monkeypatch.setattr(_mod(), "_IS_WINDOWS", False)
        monkeypatch.setattr(_mod().os, "replace", replace)
        code = _mod().main(["record", "--fp", FP_A, "--action", "created", "--issue-url", URL, "--date", DAY,
                            "--cache", str(cache)])
        captured = capsys.readouterr()
        assert code == 1 and captured.out == ""
        assert json.loads(captured.err)["message"].startswith(f"cannot write {cache}")
        assert cache.read_bytes() == before
        assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"]

    def test_an_empty_lock_file_is_taken_at_once(self, tmp_path, monkeypatch, capsys):
        """skf-run-lock.py never writes an empty lock and nothing else writes this one, so an empty lock holds
        no call: record passes empty_is_stale=True and replaces it without waiting for it to go stale (here
        with no wait at all)."""
        cache = _write_cache(tmp_path / "seen.json", {OTHER_FP: _live()})
        (tmp_path / "seen.json.lock").write_bytes(b"")
        monkeypatch.setattr(_mod(), "LOCK_WAIT_SEC", 0.0)
        code = _mod().main(["record", "--fp", FP_A, "--action", "created", "--issue-url", URL, "--date", DAY,
                            "--cache", str(cache)])
        captured = capsys.readouterr()
        assert code == 0, captured.err
        assert json.loads(captured.out)["written"] is True
        assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"]

    def test_a_lock_another_run_holds_exits_1(self, tmp_path, monkeypatch, capsys):
        cache = _write_cache(tmp_path / "seen.json", {OTHER_FP: _live()})
        before = cache.read_bytes()
        run_lock = _mod()._load(RUN_LOCK)
        holder = "health-check-seen:record:20261112T101500Z-0badc0de"
        assert run_lock.acquire(tmp_path / "seen.json.lock", holder, 3600)["acquired"] is True
        monkeypatch.setattr(_mod(), "LOCK_WAIT_SEC", 0.3)
        code = _mod().main(["record", "--fp", FP_A, "--action", "created", "--issue-url", URL, "--date", DAY,
                            "--cache", str(cache)])
        captured = capsys.readouterr()
        assert code == 1 and captured.out == ""
        assert holder in json.loads(captured.err)["message"]
        assert cache.read_bytes() == before
        assert run_lock.release(tmp_path / "seen.json.lock", holder)["released"] is True

    def test_a_stale_lock_left_by_a_killed_call_is_replaced(self, tmp_path, monkeypatch, capsys):
        """A record call killed while it held the lock leaves it behind. Once it is older than LOCK_STALE_SEC,
        the next record replaces it at once, with no wait, and leaves no lock; a longer stale window would
        wait, then exit 1."""
        cache = _write_cache(tmp_path / "seen.json", {OTHER_FP: _live()})
        run_lock = _mod()._load(RUN_LOCK)
        killed = "health-check-seen:record:20261112T101500Z-0badc0de"
        killed_at = datetime.now(timezone.utc) - timedelta(seconds=60)
        assert run_lock.acquire(tmp_path / "seen.json.lock", killed, 15, now=killed_at)["acquired"] is True
        monkeypatch.setattr(_mod(), "LOCK_WAIT_SEC", 0.3)
        code = _mod().main(["record", "--fp", FP_A, "--action", "created", "--issue-url", URL, "--date", DAY,
                            "--cache", str(cache)])
        captured = capsys.readouterr()
        assert code == 0, captured.err
        assert json.loads(captured.out)["written"] is True
        assert set(json.loads(cache.read_text(encoding="utf-8"))) == {OTHER_FP, FP_A}
        assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"]

    def test_the_lock_is_the_registry_lock_shape(self):
        """Held for one read-merge-write: stale after 15 seconds, waited on for up to 10."""
        assert (_mod().LOCK_STALE_SEC, _mod().LOCK_WAIT_SEC) == (15.0, 10.0)

    def test_the_default_cache_is_in_home(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
        code, out, err = _cli("record", "--fp", FP_A, "--action", "created", "--issue-url", URL, "--date", DAY,
                              env=env)
        assert code == 0, err
        cache = home / ".skf" / "health-check-seen.json"
        assert json.loads(cache.read_text(encoding="utf-8"))[FP_A]["issue_url"] == URL
        code, out, err = _cli("lookup", "--fp", FP_B, "--legacy-fp", LEGACY, env=env)
        assert code == 0, err
        assert json.loads(out)["verdict"] == "unseen"

    def test_a_record_reads_back_through_lookup(self, tmp_path, no_gh):
        cache = tmp_path / "seen.json"
        _mod().record(FP_A, "created", URL, DAY, False, cache)
        _mod().record(FP_B, "created", "https://github.com/o/r/issues/2", DAY, False, cache)
        data = json.loads(cache.read_text(encoding="utf-8"))
        data[FP_A]["action"] = "resolved"  # the fix, recorded by hand
        cache.write_text(json.dumps(data), encoding="utf-8")
        assert _mod().lookup(FP_A, LEGACY, cache)["verdict"] == "regression"


class TestAtomicWriteWindowsRename:
    """Windows refuses os.replace over the cache while another process has it open (a lookup reading it, a
    scanner); _atomic_write retries a PermissionError there, and only there, before it fails. Ported from
    test-skf-forge-tier-rw.py's class of the same name."""

    @staticmethod
    def _refuse(times: int | None, calls: list, only: Path | None = None):
        """os.replace refused `times` times (None: always), for `only` when it is given."""
        real_replace = os.replace

        def replace(src, dst):
            if only is not None and Path(dst) != only:
                return real_replace(src, dst)  # the lock's own rename
            calls.append(dst)
            if times is None or len(calls) <= times:
                raise PermissionError(13, "Access is denied", str(dst))
            return real_replace(src, dst)

        return replace

    def test_a_rename_refused_for_a_moment_is_retried(self, tmp_path, monkeypatch):
        target = _bytes(tmp_path / "seen.json", b"{}\n")
        calls: list = []
        monkeypatch.setattr(_mod(), "_IS_WINDOWS", True)
        monkeypatch.setattr(_mod().os, "replace", self._refuse(2, calls))
        _mod()._atomic_write(target, '{"new": true}\n')
        assert len(calls) == 3
        assert target.read_bytes() == b'{"new": true}\n'
        assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"]

    def test_a_rename_refused_past_the_wait_fails_and_keeps_the_file(self, tmp_path, monkeypatch):
        target = _bytes(tmp_path / "seen.json", b"{}\n")
        calls: list = []
        monkeypatch.setattr(_mod(), "_IS_WINDOWS", True)
        monkeypatch.setattr(_mod(), "_REPLACE_WAIT_SECONDS", 0.05)
        monkeypatch.setattr(_mod().os, "replace", self._refuse(None, calls))
        started = time.monotonic()
        with pytest.raises(PermissionError):
            _mod()._atomic_write(target, '{"new": true}\n')
        elapsed = time.monotonic() - started
        assert len(calls) > 1 and 0.05 <= elapsed < 2.0
        assert target.read_bytes() == b"{}\n"
        assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"]

    def test_off_windows_a_refused_rename_fails_at_once(self, tmp_path, monkeypatch):
        calls: list = []
        monkeypatch.setattr(_mod(), "_IS_WINDOWS", False)
        monkeypatch.setattr(_mod().os, "replace", self._refuse(None, calls))
        with pytest.raises(PermissionError):
            _mod()._atomic_write(tmp_path / "seen.json", '{"new": true}\n')
        assert len(calls) == 1
        assert list(tmp_path.iterdir()) == []

    def test_only_a_refused_rename_is_retried(self, tmp_path, monkeypatch):
        calls: list = []

        def missing(src, dst):
            calls.append(dst)
            raise FileNotFoundError(2, "No such file or directory", str(src))

        monkeypatch.setattr(_mod(), "_IS_WINDOWS", True)
        monkeypatch.setattr(_mod().os, "replace", missing)
        with pytest.raises(FileNotFoundError):
            _mod()._atomic_write(tmp_path / "seen.json", '{"new": true}\n')
        assert len(calls) == 1

    def test_record_retries_a_refused_rename_on_windows(self, tmp_path, monkeypatch, capsys):
        cache = _write_cache(tmp_path / "seen.json", {OTHER_FP: _live()})
        calls: list = []
        monkeypatch.setattr(_mod(), "_IS_WINDOWS", True)
        monkeypatch.setattr(_mod().os, "replace", self._refuse(2, calls, only=cache))
        code = _mod().main(["record", "--fp", FP_A, "--action", "created", "--issue-url", URL, "--date", DAY,
                            "--cache", str(cache)])
        captured = capsys.readouterr()
        assert code == 0, captured.err
        assert len(calls) == 3
        assert set(json.loads(cache.read_text(encoding="utf-8"))) == {OTHER_FP, FP_A}
        assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"]

    def test_record_refused_past_the_wait_exits_1_and_keeps_the_cache(self, tmp_path, monkeypatch, capsys):
        cache = _write_cache(tmp_path / "seen.json", {OTHER_FP: _live()})
        before = cache.read_bytes()
        calls: list = []
        monkeypatch.setattr(_mod(), "_IS_WINDOWS", True)
        monkeypatch.setattr(_mod(), "_REPLACE_WAIT_SECONDS", 0.05)
        monkeypatch.setattr(_mod().os, "replace", self._refuse(None, calls, only=cache))
        code = _mod().main(["record", "--fp", FP_A, "--action", "created", "--issue-url", URL, "--date", DAY,
                            "--cache", str(cache)])
        captured = capsys.readouterr()
        assert code == 1 and captured.out == "" and len(calls) > 1
        assert json.loads(captured.err)["message"].startswith(f"cannot write {cache}")
        assert cache.read_bytes() == before
        assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"], "no lock, guard or temp file is left"

    def test_the_wait_stays_well_under_the_lock_stale_window(self):
        assert _mod()._REPLACE_WAIT_SECONDS <= _mod().LOCK_STALE_SEC / 2


def _bytes(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


# Runs the helper once a start file exists, so the calls reach the lock together.
RUNNER = (
    "import os, runpy, sys, time\n"
    "go, script = sys.argv[1], sys.argv[2]\n"
    "while not os.path.exists(go):\n"
    "    time.sleep(0.002)\n"
    "sys.argv = sys.argv[2:]\n"
    "runpy.run_path(script, run_name='__main__')\n"
)


def test_parallel_records_lose_none(tmp_path):
    """Without the lock, calls that read the same file overwrite each other's record."""
    cache = _write_cache(tmp_path / "seen.json", {OTHER_FP: _live()})
    go = tmp_path / "go"
    fps = [f"fp-{i:07x}" for i in range(8)]
    procs = [subprocess.Popen([sys.executable, "-c", RUNNER, str(go), str(HELPER), "record", "--fp", fp,
                               "--action", "created", "--issue-url", f"{URL}{i}", "--date", DAY,
                               "--cache", str(cache)],
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for i, fp in enumerate(fps)]
    time.sleep(0.8)
    go.write_bytes(b"")
    for proc in procs:
        out, err = proc.communicate(timeout=120)
        assert proc.returncode == 0, err
        assert json.loads(out)["written"] is True
    data = json.loads(cache.read_text(encoding="utf-8"))
    assert sorted(data) == sorted([OTHER_FP, *fps])
    assert sorted(p.name for p in tmp_path.iterdir()) == ["go", "seen.json"]


# --------------------------------------------------------------------------
# The step's own calls, filled in and run
# --------------------------------------------------------------------------


def _step_calls(subcommand: str) -> list[str]:
    """The fenced `uv run {seenCacheHelper} <subcommand> ...` lines of the shared health check."""
    prefix = f"uv run {{seenCacheHelper}} {subcommand} "
    return [line for line in SHARED_HEALTH_CHECK.read_text(encoding="utf-8").splitlines() if line.startswith(prefix)]


def _run_step_call(line: str, values: dict, env: dict) -> dict:
    """Run one of the step's calls with its placeholders filled, through this checkout's helper."""
    for placeholder, value in {"{seenCacheHelper}": "HELPER", **values}.items():
        line = line.replace(placeholder, value)
    assert "{" not in line, line
    words = shlex.split(line)
    assert words[:3] == ["uv", "run", "HELPER"], words
    code, out, err = _cli(*words[3:], env=env)
    assert code == 0, err
    return json.loads(out)


def test_a_worked_example_through_the_steps_command():
    """Two different defects in inventory-contract.md's only section shared one fingerprint before the key; the
    step's call keeps them apart and gives hashlib's 7 hex characters, with the key and without it."""
    (line,) = _step_calls("fingerprint")
    base = {"{severity}": SAMPLE["severity"], "{workflow}": SAMPLE["workflow"], "{step_file}": SAMPLE["step_file"],
            "{section-slug}": SAMPLE["section"]}
    joined = "|".join(base.values())
    assert joined == "gap|skf-test-skill|src/skf-test-skill/references/inventory-contract.md|documented-inventory-contract"

    def sha7(text: str) -> str:
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:7]

    for key, fp in (("const-holding-function", FP_A), ("shared-text", FP_B)):
        out = _run_step_call(line, {**base, "{defect-key}": key}, dict(os.environ))
        assert out == {"fp": fp, "legacy_fp": LEGACY}
        assert out == {"fp": f"fp-{sha7(f'{joined}|{key}')}", "legacy_fp": f"fp-{sha7(joined)}"}


def test_the_steps_lookup_and_record_calls_share_the_default_cache(tmp_path):
    """The step passes no --cache: its calls meet in $HOME/.skf/health-check-seen.json. A fix recorded by hand
    there makes the next sighting a regression, whose new issue the step's --regression call records."""
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
    cache = home / ".skf" / "health-check-seen.json"
    ids = {"{fp}": FP_A, "{legacy_fp}": LEGACY, "{today}": DAY}
    # §5a-i's call after [R] or [C], then §5b's after a new issue, each with its --regression form.
    reacted, reacted_regression, created, regression = _step_calls("record")
    assert reacted_regression == f"{reacted} --regression" and regression == f"{created} --regression"

    def mark_resolved():  # CONTRIBUTING.md's hand edit once the defect is fixed
        data = json.loads(cache.read_text(encoding="utf-8"))
        data[FP_A]["action"] = "resolved"
        cache.write_text(json.dumps(data), encoding="utf-8")

    first = _run_step_call(created, {**ids, "{new_issue_url}": URL}, env)
    assert first["written"] is True and cache.is_file()
    mark_resolved()
    (lookup_call,) = _step_calls("lookup")
    assert _run_step_call(lookup_call, ids, env)["verdict"] == "regression"
    # The plain call leaves the fix alone; the regression call records the recurrence's issue.
    new_url = "https://github.com/o/r/issues/77"
    assert _run_step_call(created, {**ids, "{new_issue_url}": new_url}, env)["written"] is False
    assert _run_step_call(regression, {**ids, "{new_issue_url}": new_url}, env)["record"] == {
        "issue_url": new_url, "action": "created", "date": DAY}
    # The same after [R] or [C] on an open issue that reports the recurrence.
    mark_resolved()
    open_issue = {**ids, "{reacted|commented}": "commented", "{url}": "https://github.com/o/r/issues/78"}
    assert _run_step_call(reacted, open_issue, env)["written"] is False
    assert _run_step_call(reacted_regression, open_issue, env)["record"] == {
        "issue_url": "https://github.com/o/r/issues/78", "action": "commented", "date": DAY}
    out = _run_step_call(reacted, {**ids, "{fp}": FP_B, "{reacted|commented}": "reacted", "{url}": URL}, env)
    assert out["record"]["action"] == "reacted"
    assert set(json.loads(cache.read_text(encoding="utf-8"))) == {FP_A, FP_B}


# --------------------------------------------------------------------------
# The helper's shape
# --------------------------------------------------------------------------


def test_the_helper_is_a_stdlib_script_with_a_parser():
    text = HELPER.read_text(encoding="utf-8")
    assert text.startswith("# /// script\n# requires-python = \">=3.11\"\n# dependencies = []\n# ///\n")
    parser = _mod()._build_parser()
    for argv in (_fingerprint_args(), ["lookup", "--fp", FP_A, "--legacy-fp", LEGACY],
                 ["record", "--fp", FP_A, "--action", "created", "--issue-url", URL, "--date", DAY, "--regression"]):
        parser.parse_args(argv)


def test_fingerprint_and_record_run_no_gh(tmp_path, no_gh):
    _mod().fingerprint(defect_key="shared-text", **SAMPLE)
    _mod().record(FP_A, "created", URL, DAY, False, tmp_path / "seen.json")
    assert no_gh == []
