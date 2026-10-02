#!/usr/bin/env python3
"""Tests for skf-detect-tools.py.

Strategy:
- Tier truth table is enumerated exhaustively (16 rows over the 4-tool boolean
  product). Each row asserts the calculated tier and the satisfied/missing
  result for every possible --require-tier value.
- Tool probes are tested with mocked subprocess.run (plus a mocked
  shutil.which, since _run() resolves cmd[0] through PATH before spawning)
  to cover normal, alias-shadowed, daemon-stopped, and timeout paths
  without hitting real binaries.
- Minimum versions: the version parse, the comparison and what a tool below
  its minimum does (a tier tool stops counting, git and uv only warn), with
  a version below, at and above the minimum, one that does not parse and a
  null minimum.
- CLI integration test invokes the script as a subprocess and validates the
  emitted JSON shape end-to-end.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


SCRIPT_PATH = (
    Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-detect-tools.py"
)

spec = importlib.util.spec_from_file_location("skf_detect_tools", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


# ─── Tier calculation ────────────────────────────────────────────────────────


def _tools_state(ag: bool, gh: bool, qm: bool, cc: bool) -> dict:
    return {
        "ast_grep": {"available": ag, "version": "x" if ag else None},
        "gh_cli":   {"available": gh, "version": "x" if gh else None},
        "qmd":      {"available": qm, "status": "healthy" if qm else "absent",
                     "version": "x" if qm else None},
        "ccc":      {"available": cc, "daemon": "healthy" if cc else None,
                     "version": "x" if cc else None},
        "security_scan": {"available": False},
    }


# Full 4-bool truth table (16 rows) with expected tier
TIER_TRUTH_TABLE = [
    # (ast_grep, gh, qmd, ccc, expected_tier)
    (False, False, False, False, "Quick"),
    (False, False, False, True,  "Quick"),  # ccc alone unlocks nothing
    (False, False, True,  False, "Quick"),
    (False, False, True,  True,  "Quick"),
    (False, True,  False, False, "Quick"),  # gh alone unlocks nothing
    (False, True,  False, True,  "Quick"),
    (False, True,  True,  False, "Quick"),
    (False, True,  True,  True,  "Quick"),
    (True,  False, False, False, "Forge"),
    (True,  False, False, True,  "Forge+"),
    (True,  False, True,  False, "Forge"),  # ast+qmd not enough for Deep without gh
    (True,  False, True,  True,  "Forge+"),
    (True,  True,  False, False, "Forge"),  # ast+gh not enough for Deep without qmd
    (True,  True,  False, True,  "Forge+"),
    (True,  True,  True,  False, "Deep"),
    (True,  True,  True,  True,  "Deep"),   # Deep takes priority over Forge+
]


@pytest.mark.parametrize("ag,gh,qm,cc,expected", TIER_TRUTH_TABLE)
def test_tier_calculation_truth_table(ag, gh, qm, cc, expected):
    tier = mod.calculate_tier(_tools_state(ag, gh, qm, cc))
    assert tier == expected, f"({ag=}, {gh=}, {qm=}, {cc=}) → expected {expected}, got {tier}"


# ─── Prerequisites check (drives both --tier-override sanity + --require-tier) ──


@pytest.mark.parametrize("ag,gh,qm,cc,_expected_tier", TIER_TRUTH_TABLE)
@pytest.mark.parametrize("required", ["Quick", "Forge", "Forge+", "Deep"])
def test_prerequisites_match_required_tools(ag, gh, qm, cc, _expected_tier, required):
    tools = _tools_state(ag, gh, qm, cc)
    satisfied, missing = mod.tier_prerequisites_met(required, tools)

    if required == "Quick":
        assert satisfied is True and missing == []
    elif required == "Forge":
        assert satisfied is ag
        assert missing == ([] if ag else ["ast-grep"])
    elif required == "Forge+":
        assert satisfied is (ag and cc)
        # Order matters — declared as ast_grep first, then ccc in the source dict
        expected_missing = []
        if not ag:
            expected_missing.append("ast-grep")
        if not cc:
            expected_missing.append("ccc")
        assert missing == expected_missing
    elif required == "Deep":
        assert satisfied is (ag and gh and qm)
        expected_missing = []
        if not ag:
            expected_missing.append("ast-grep")
        if not gh:
            expected_missing.append("gh")
        if not qm:
            expected_missing.append("qmd")
        assert missing == expected_missing


def test_deep_does_not_subsume_forge_plus():
    """Deep with no ccc should fail --require-tier=Forge+."""
    tools = _tools_state(ag=True, gh=True, qm=True, cc=False)
    assert mod.calculate_tier(tools) == "Deep"
    satisfied, missing = mod.tier_prerequisites_met("Forge+", tools)
    assert satisfied is False
    assert "ccc" in missing


# ─── Individual probe behaviour (subprocess mocked) ──────────────────────────


def _fake_run(rc: int = 0, stdout: str = "", stderr: str = ""):
    """Build a CompletedProcess-like object _run() can wrap."""
    class _Result:
        def __init__(self):
            self.returncode = rc
            self.stdout = stdout
            self.stderr = stderr
    return _Result()


def _which_identity(name):
    """PATH-independent shutil.which stand-in: every probe binary "resolves"
    to its bare name, so mocked-subprocess tests reach subprocess.run
    regardless of what is actually installed on the host.
    """
    return name


def _logical(cmd):
    """Strip the OS `timeout(1)` wrapper `_run()` prepends, returning the
    underlying tool argv so probe `side_effect`s can match on the logical
    command regardless of whether the host has `timeout` available.
    """
    if cmd and os.path.splitext(os.path.basename(str(cmd[0])))[0].lower() == "timeout":
        rest = list(cmd[1:])
        while rest and (rest[0].startswith("-") or rest[0].replace(".", "", 1).isdigit()):
            rest.pop(0)
        return rest
    return list(cmd)


def test_probe_ast_grep_success():
    with (
        patch.object(mod.shutil, "which", _which_identity),
        patch.object(mod.subprocess, "run", return_value=_fake_run(0, "ast-grep 0.39.5\n")),
    ):
        result = mod.probe_ast_grep()
    assert result == {"available": True, "version": "ast-grep 0.39.5"}


def test_probe_ast_grep_not_installed():
    # which resolves but the spawn itself fails (e.g. binary removed between
    # resolution and exec) — the FileNotFoundError guard must still hold.
    with (
        patch.object(mod.shutil, "which", _which_identity),
        patch.object(mod.subprocess, "run", side_effect=FileNotFoundError),
    ):
        result = mod.probe_ast_grep()
    assert result == {"available": False, "version": None}


def test_probe_ccc_identity_marker_present():
    """Genuine cocoindex-code help output should be accepted."""
    help_output = (
        "Usage: ccc [OPTIONS] COMMAND [ARGS]...\n\n"
        "CocoIndex Code — index and search codebases.\n"
    )
    doctor_output = "All systems operational\n"

    def _side_effect(cmd, **kwargs):
        cmd = _logical(cmd)
        if cmd == ["ccc", "--help"]:
            return _fake_run(0, help_output)
        if cmd == ["ccc", "doctor"]:
            return _fake_run(0, doctor_output)
        raise AssertionError(f"unexpected probe call: {cmd}")

    with (
        patch.object(mod.shutil, "which", _which_identity),
        patch.object(mod.subprocess, "run", side_effect=_side_effect),
    ):
        result = mod.probe_ccc()
    assert result["available"] is True
    assert result["daemon"] == "healthy"


def test_probe_ccc_version_is_none_not_misparsed_header():
    """`ccc doctor` leads with a settings header ("Global Settings"), not a
    version — it must never be reported as ccc's version string."""
    help_output = (
        "Usage: ccc [OPTIONS] COMMAND [ARGS]...\n\n"
        "CocoIndex Code — index and search codebases.\n"
    )
    doctor_output = (
        "\n  Global Settings\n"
        "  ----------------\n"
        "  Settings: /home/user/.cocoindex_code/global_settings.yml\n"
    )

    def _side_effect(cmd, **kwargs):
        cmd = _logical(cmd)
        if cmd == ["ccc", "--help"]:
            return _fake_run(0, help_output)
        if cmd == ["ccc", "doctor"]:
            return _fake_run(0, doctor_output)
        raise AssertionError(f"unexpected probe call: {cmd}")

    with (
        patch.object(mod.shutil, "which", _which_identity),
        patch.object(mod.subprocess, "run", side_effect=_side_effect),
    ):
        result = mod.probe_ccc()
    assert result["available"] is True
    assert result["daemon"] == "healthy"
    assert result["version"] is None


def test_probe_ccc_identity_marker_absent_rejects_alias():
    """Foreign `ccc` binary (e.g. code2prompt alias) must not pass."""
    # Foreign tool exits 0 on --help but lacks the marker
    foreign_help = "Usage: ccc [OPTIONS]\n\nA generic tool that happens to use ccc as its name.\n"

    def _side_effect(cmd, **kwargs):
        cmd = _logical(cmd)
        if cmd == ["ccc", "--help"]:
            return _fake_run(0, foreign_help)
        raise AssertionError(
            "ccc doctor MUST NOT be called when identity marker is absent — "
            f"called with {cmd}"
        )

    with (
        patch.object(mod.shutil, "which", _which_identity),
        patch.object(mod.subprocess, "run", side_effect=_side_effect),
    ):
        result = mod.probe_ccc()
    assert result == {"available": False, "daemon": None, "version": None}


def test_probe_qmd_binary_present_daemon_stopped():
    def _side_effect(cmd, **kwargs):
        cmd = _logical(cmd)
        if cmd == ["qmd", "--version"]:
            return _fake_run(0, "qmd 1.2.3\n")
        if cmd == ["qmd", "status"]:
            return _fake_run(1, "", "qmd: daemon not running\n")
        raise AssertionError(f"unexpected: {cmd}")

    with (
        patch.object(mod.shutil, "which", _which_identity),
        patch.object(mod.subprocess, "run", side_effect=_side_effect),
    ):
        result = mod.probe_qmd()
    assert result == {"available": False, "status": "daemon_stopped", "version": "qmd 1.2.3"}


def test_probe_qmd_falls_back_to_help_when_version_unsupported():
    """Some qmd builds reject --version; fall back to --help for identity check."""
    def _side_effect(cmd, **kwargs):
        cmd = _logical(cmd)
        if cmd == ["qmd", "--version"]:
            return _fake_run(2, "", "unknown option --version\n")
        if cmd == ["qmd", "--help"]:
            return _fake_run(0, "qmd: a search engine\n")
        if cmd == ["qmd", "status"]:
            return _fake_run(0, "Operational\n")
        raise AssertionError(f"unexpected: {cmd}")

    with (
        patch.object(mod.shutil, "which", _which_identity),
        patch.object(mod.subprocess, "run", side_effect=_side_effect),
    ):
        result = mod.probe_qmd()
    assert result["available"] is True
    assert result["status"] == "healthy"


def test_probe_qmd_absent():
    with patch.object(mod.shutil, "which", return_value=None):
        result = mod.probe_qmd()
    assert result == {"available": False, "status": "absent", "version": None}


def test_probe_security_scan_set_and_unset():
    with patch.dict(os.environ, {"SNYK_TOKEN": "abc123"}, clear=False):
        assert mod.probe_security_scan("SNYK_TOKEN") == {"available": True}
    # Whitespace-only is treated as unset
    with patch.dict(os.environ, {"SNYK_TOKEN": "   "}, clear=False):
        assert mod.probe_security_scan("SNYK_TOKEN") == {"available": False}
    # Unset
    env = {k: v for k, v in os.environ.items() if k != "SNYK_TOKEN"}
    with patch.dict(os.environ, env, clear=True):
        assert mod.probe_security_scan("SNYK_TOKEN") == {"available": False}


def test_run_swallows_timeout():
    """Probe wrapper must never raise — timeouts become rc=127."""
    with (
        patch.object(mod.shutil, "which", _which_identity),
        patch.object(
            mod.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd=["x"], timeout=1),
        ),
    ):
        rc, stdout, stderr = mod._run(["x"])
    assert rc == 127 and stdout == "" and stderr == ""


def test_run_unresolvable_command_returns_127_without_spawning():
    """which() → None means the tool is absent: rc=127 and no process is
    ever spawned (previously a bare-name spawn raised FileNotFoundError)."""
    run_mock = MagicMock()
    with (
        patch.object(mod.shutil, "which", return_value=None),
        patch.object(mod.subprocess, "run", run_mock),
    ):
        rc, stdout, stderr = mod._run(["ast-grep", "--version"])
    assert rc == 127 and stdout == "" and stderr == ""
    run_mock.assert_not_called()


def test_run_invokes_which_resolved_path_not_bare_name():
    """subprocess.run must receive the which()-resolved path — a bare name
    misses npm .CMD shims on Windows, where CreateProcess only appends .exe
    (issue #460)."""
    resolved = os.path.join("npm-shims", "ast-grep.CMD")
    calls: list[list[str]] = []

    def _side_effect(cmd, **kwargs):
        calls.append(list(cmd))
        return _fake_run(0, "ast-grep 0.45.0\n")

    with (
        patch.object(mod.shutil, "which", return_value=resolved),
        patch.object(mod.subprocess, "run", side_effect=_side_effect),
    ):
        rc, stdout, _ = mod._run(["ast-grep", "--version"])
    assert rc == 0 and stdout == "ast-grep 0.45.0\n"
    assert len(calls) == 1
    assert _logical(calls[0]) == [resolved, "--version"]


def test_run_rejects_cwd_planted_shim_without_spawning():
    """shutil.which on Windows searches CWD ahead of PATH — a repo-planted
    ast-grep.CMD must read as rc=127 (absent) and never spawn."""
    planted = os.path.join(os.getcwd(), "ast-grep.CMD")
    run_mock = MagicMock()
    with (
        patch.object(mod.shutil, "which", return_value=planted),
        patch.object(mod.subprocess, "run", run_mock),
    ):
        rc, stdout, stderr = mod._run(["ast-grep", "--version"])
    assert rc == 127 and stdout == "" and stderr == ""
    run_mock.assert_not_called()


def test_run_accepts_which_result_outside_cwd(tmp_path):
    """A which() hit in a real (non-CWD) PATH directory is still executed."""
    resolved = str(tmp_path / "ast-grep.CMD")
    calls: list[list[str]] = []

    def _side_effect(cmd, **kwargs):
        calls.append(list(cmd))
        return _fake_run(0, "ast-grep 0.45.0\n")

    with (
        patch.object(mod.shutil, "which", return_value=resolved),
        patch.object(mod.subprocess, "run", side_effect=_side_effect),
    ):
        rc, stdout, _ = mod._run(["ast-grep", "--version"])
    assert rc == 0 and stdout == "ast-grep 0.45.0\n"
    assert len(calls) == 1
    assert _logical(calls[0]) == [resolved, "--version"]


# ─── Minimum versions ───────────────────────────────────────────────────────


REPO_REQUIREMENTS = Path(__file__).parent.parent / "src" / "shared" / "tool-requirements.yaml"


@pytest.mark.parametrize("line,version", [
    ("ast-grep 0.45.3", "0.45.3"),
    ("gh version 2.101.0 (2026-09-15)", "2.101.0"),
    ("qmd 2.8.3 (facd35e)", "2.8.3"),
    ("git version 2.47.1.windows.2", "2.47.1"),
    ("uv 0.12.15 (x86_64-unknown-linux-gnu)", "0.12.15"),
    ("tool 0.45", "0.45"),
    ("qmd: a search engine", None),
    ("x", None),
    (None, None),
], ids=["ast-grep", "gh", "qmd", "git-windows", "uv", "two-parts", "help-line", "no-digits", "none"])
def test_found_version_reads_the_first_x_y_or_x_y_z(line, version):
    assert mod.found_version(line) == version


@pytest.mark.parametrize("version,minimum,meets", [
    ("ast-grep 0.42.2", "0.45.3", False),
    ("ast-grep 0.45.3", "0.45.3", True),
    ("ast-grep 0.46.0", "0.45.3", True),
    ("ast-grep 0.45", "0.45.3", False),
    ("git version 2.9.5", "2.15", False),
    ("git version 2.15.0", "2.15", True),
    ("gh version 2.101.0 (2026-09-15)", "2.15", True),
    ("Python 3.11.9", "3", True),
    ("ast-grep (unknown build)", "0.45.3", None),
    ("ast-grep 0.42.2", None, None),
    (None, "0.45.3", None),
    ("ast-grep 0.42.2", "latest", None),
], ids=["below", "at", "above", "missing-patch-below", "numeric-not-text", "at-two-parts", "minor-above-100",
        "bare-major", "version-unparsed", "null-minimum", "not-installed", "minimum-not-a-version"])
def test_meets_minimum(version, minimum, meets):
    assert mod.meets_minimum(version, minimum) is meets


REQUIREMENTS = {
    "git": {"name": "git", "kind": "runtime", "tiers": ["Quick"], "minimum": "2.15",
            "upgrade": "Install the latest release from https://git-scm.com/downloads"},
    "gh_cli": {"name": "gh", "kind": "tier", "tiers": ["Deep"], "minimum": None,
               "upgrade": "Install the latest release from https://cli.github.com"},
    "ast_grep": {"name": "ast-grep", "kind": "tier", "tiers": ["Forge", "Forge+", "Deep"], "minimum": "0.45.3",
                 "upgrade": "npm install -g @ast-grep/cli@latest"},
}


def test_a_tier_tool_below_its_minimum_stops_counting_and_git_only_warns():
    tools = {"ast_grep": {"available": True, "version": "ast-grep 0.42.2"},
             "gh_cli": {"available": True, "version": "gh version 1.0.0"},
             "git": {"available": True, "version": "git version 2.9.5"},
             "security_scan": {"available": False}}
    below = mod.apply_minimums(tools, REQUIREMENTS)
    assert tools["ast_grep"] == {"available": False, "version": "ast-grep 0.42.2", "minimum": "0.45.3",
                                 "meets_minimum": False, "below_minimum": True}
    assert tools["git"]["available"] is True and tools["git"]["below_minimum"] is True
    # A null minimum never holds a tool back, however old it is.
    assert tools["gh_cli"] == {"available": True, "version": "gh version 1.0.0", "minimum": None,
                               "meets_minimum": None, "below_minimum": False}
    assert tools["security_scan"] == {"available": False}
    # In the list's order, with what the banner and the envelope need (the emitter reads no YAML).
    assert below == [
        {"tool": "git", "name": "git", "version": "2.9.5", "minimum": "2.15",
         "upgrade": "Install the latest release from https://git-scm.com/downloads", "tier": None},
        {"tool": "ast_grep", "name": "ast-grep", "version": "0.42.2", "minimum": "0.45.3",
         "upgrade": "npm install -g @ast-grep/cli@latest", "tier": "Forge"},
    ]


@pytest.mark.parametrize("version", ["ast-grep 0.45.3", "ast-grep 0.50.0", "ast-grep (dev build)", None],
                         ids=["at", "above", "unparsed", "absent"])
def test_a_tool_at_or_above_its_minimum_or_of_unknown_version_changes_nothing(version):
    tools = {"ast_grep": {"available": version is not None, "version": version}}
    assert mod.apply_minimums(tools, REQUIREMENTS) == []
    assert tools["ast_grep"]["available"] is (version is not None)
    assert tools["ast_grep"]["below_minimum"] is False


def test_a_tool_the_list_does_not_name_gets_no_minimum():
    tools = {"uv": {"available": True, "version": "uv 0.1.0"}}
    assert mod.apply_minimums(tools, {}) == []
    assert tools["uv"] == {"available": True, "version": "uv 0.1.0", "minimum": None, "meets_minimum": None,
                           "below_minimum": False}


def test_load_requirements_reads_the_shipped_list_beside_scripts(tmp_path):
    assert mod.REQUIREMENTS_FILE == REPO_REQUIREMENTS.resolve()
    shipped = mod.load_requirements()
    assert shipped["ast_grep"]["minimum"] == "0.45.3" and shipped["ast_grep"]["kind"] == "tier"
    assert {"git", "uv", "gh_cli", "qmd", "ccc"} <= set(shipped)
    # A list that is missing or not YAML holds no tool back.
    assert mod.load_requirements(tmp_path / "missing.yaml") == {}
    broken = tmp_path / "broken.yaml"
    broken.write_text("tools: [unclosed\n", encoding="utf-8")
    assert mod.load_requirements(broken) == {}


def test_an_installed_copy_reads_the_list_in_its_shared_folder(tmp_path):
    scripts = tmp_path / "_bmad" / "skf" / "shared" / "scripts"
    scripts.mkdir(parents=True)
    copy = scripts / SCRIPT_PATH.name
    copy.write_bytes(SCRIPT_PATH.read_bytes())
    installed_spec = importlib.util.spec_from_file_location("skf_detect_tools_installed", copy)
    installed = importlib.util.module_from_spec(installed_spec)
    installed_spec.loader.exec_module(installed)
    assert installed.REQUIREMENTS_FILE == (tmp_path / "_bmad" / "skf" / "shared" / "tool-requirements.yaml").resolve()


def test_detect_leaves_a_tier_tool_below_its_minimum_out_of_the_tier_and_require_tier():
    old = {"ast_grep": "ast-grep 0.42.2", "git": "git version 2.9.5"}
    with _patch_all_probes(ag=True, gh=True, cc=True, versions=old), \
            patch.object(mod, "REQUIREMENTS_FILE", REPO_REQUIREMENTS):
        out = mod.detect(_detect_args(require_tier="Forge"))
    # Forge+ tools, but ast-grep is below 0.45.3, so it counts toward no tier.
    assert out["tier"]["calculated"] == "Quick"
    assert out["tools"]["ast_grep"]["available"] is False and out["tools"]["ast_grep"]["below_minimum"] is True
    assert out["require_tier"] == {"requested": "Forge", "satisfied": False, "missing_tools": ["ast-grep"]}
    assert [tool["tool"] for tool in out["tools_below_minimum"]] == ["git", "ast_grep"]
    assert out["tools"]["git"]["available"] is True


@pytest.mark.parametrize("version,tier", [("ast-grep 0.45.3", "Forge+"), ("ast-grep 0.46.1", "Forge+"),
                                          ("ast-grep (dev)", "Forge+")], ids=["at", "above", "unparsed"])
def test_detect_counts_a_tool_at_or_above_its_minimum_or_of_unknown_version(version, tier):
    with _patch_all_probes(ag=True, cc=True, versions={"ast_grep": version}):
        out = mod.detect(_detect_args(require_tier="Forge"))
    assert out["tier"]["calculated"] == tier
    assert out["require_tier"]["satisfied"] is True and out["tools_below_minimum"] == []


def test_ccc_version_comes_from_uv_tool_list():
    listing = ("claude-swap v0.26.0\n- claude-swap\ncocoindex-code v0.2.41\n- ccc\n- cocoindex-code\n"
               "graphifyy v0.9.69\n- graphify\n")

    def _side_effect(cmd, **kwargs):
        assert _logical(cmd) == ["uv", "tool", "list"], cmd
        return _fake_run(0, listing)

    with (
        patch.object(mod.shutil, "which", _which_identity),
        patch.object(mod.subprocess, "run", side_effect=_side_effect),
    ):
        assert mod.probe_ccc_version() == "0.2.41"
    with (
        patch.object(mod.shutil, "which", _which_identity),
        patch.object(mod.subprocess, "run", return_value=_fake_run(0, "ruff v0.6.0\n- ruff\n")),
    ):
        assert mod.probe_ccc_version() is None
    with patch.object(mod.shutil, "which", return_value=None):
        assert mod.probe_ccc_version() is None


def test_detect_sets_ccc_version_only_for_an_installed_ccc():
    with _patch_all_probes(ag=True, cc=True, versions={"ccc": "0.2.41"}):
        assert mod.detect(_detect_args())["tools"]["ccc"]["version"] == "0.2.41"
    with _patch_all_probes(ag=True, cc=False, versions={"ccc": "0.2.41"}):
        assert mod.detect(_detect_args())["tools"]["ccc"]["version"] is None


@pytest.mark.parametrize("probe,command", [("probe_git", "git"), ("probe_uv", "uv")])
def test_git_and_uv_are_probed_with_one_version_call(probe, command):
    calls = []

    def _side_effect(cmd, **kwargs):
        calls.append(_logical(cmd))
        return _fake_run(0, f"{command} 1.2.3\n")

    with (
        patch.object(mod.shutil, "which", _which_identity),
        patch.object(mod.subprocess, "run", side_effect=_side_effect),
    ):
        assert getattr(mod, probe)() == {"available": True, "version": f"{command} 1.2.3"}
    assert calls == [[command, "--version"]]


# ─── Override + require-tier integration via detect() ────────────────────────


def _detect_args(**overrides):
    """Build an argparse.Namespace with detect() defaults."""
    import argparse
    return argparse.Namespace(
        tier_override=overrides.get("tier_override"),
        require_tier=overrides.get("require_tier"),
        snyk_env_var=overrides.get("snyk_env_var", "SNYK_TOKEN_DOES_NOT_EXIST"),
    )


def _patch_all_probes(ag=False, gh=False, qm=False, cc=False, versions=None):
    """Every probe detect() runs, faked: no real binary runs. `versions` gives
    a tool key's version line (the default "x" parses as no version)."""
    versions = versions or {}

    def version(key, present):
        return versions.get(key, "x") if present else None

    return patch.multiple(
        mod,
        probe_ast_grep=lambda: {"available": ag, "version": version("ast_grep", ag)},
        probe_gh_cli=lambda:   {"available": gh, "version": version("gh_cli", gh)},
        probe_qmd=lambda:      {"available": qm,
                                "status": "healthy" if qm else "absent",
                                "version": version("qmd", qm)},
        probe_ccc=lambda:      {"available": cc,
                                "daemon": "healthy" if cc else None,
                                "version": None},
        probe_ccc_version=lambda: versions.get("ccc"),
        probe_git=lambda: {"available": True, "version": versions.get("git", "git version 2.47.3")},
        probe_uv=lambda: {"available": True, "version": versions.get("uv", "uv 0.12.15")},
    )


def test_detect_no_override_no_require():
    with _patch_all_probes(ag=True, gh=True, qm=True, cc=True):
        out = mod.detect(_detect_args())
    assert out["tier"]["calculated"] == "Deep"
    assert out["tier"]["detected"] == "Deep"
    assert out["tier"]["override_applied"] is False
    assert out["tier"]["override_invalid"] is False
    assert out["tier"]["override_unsafe"] is False
    assert out["require_tier"]["requested"] is None
    assert out["require_tier"]["satisfied"] is None


def test_detect_valid_override_with_satisfied_prerequisites():
    with _patch_all_probes(ag=True, gh=True, qm=True, cc=False):
        out = mod.detect(_detect_args(tier_override="Deep"))
    assert out["tier"]["calculated"] == "Deep"
    assert out["tier"]["detected"] == "Deep"
    assert out["tier"]["override_applied"] is True
    assert out["tier"]["override_value"] == "Deep"
    assert out["tier"]["override_unsafe"] is False
    assert out["tier"]["override_unsafe_missing"] == []


def test_detect_valid_override_with_unsafe_prerequisites():
    """User forces Deep on a Quick host — applied, but flagged unsafe."""
    with _patch_all_probes(ag=False, gh=False, qm=False, cc=False):
        out = mod.detect(_detect_args(tier_override="Deep"))
    assert out["tier"]["calculated"] == "Deep"
    assert out["tier"]["detected"] == "Quick"
    assert out["tier"]["override_applied"] is True
    assert out["tier"]["override_unsafe"] is True
    assert set(out["tier"]["override_unsafe_missing"]) == {"ast-grep", "gh", "qmd"}


def test_detect_invalid_override_falls_back_to_detected():
    with _patch_all_probes(ag=True, gh=False, qm=False, cc=False):
        out = mod.detect(_detect_args(tier_override="forge+"))  # wrong case
    assert out["tier"]["calculated"] == "Forge"
    assert out["tier"]["detected"] == "Forge"
    assert out["tier"]["override_applied"] is False
    assert out["tier"]["override_invalid"] is True
    assert out["tier"]["override_invalid_value"] == "forge+"
    # Case-insensitive match should suggest the canonical form
    assert out["tier"]["override_invalid_suggestion"] == "Forge+"


# ─── suggest_valid_tier (fuzzy match for invalid --tier-override) ────────────


@pytest.mark.parametrize("bad,expected", [
    # Case-insensitive exact matches — most common typo class
    ("deep",     "Deep"),
    ("DEEP",     "Deep"),
    ("Deep",     None),    # Already valid — never called for valid values, but defensive
    ("forge+",   "Forge+"),
    ("FORGE+",   "Forge+"),
    ("quick",    "Quick"),
    ("forge",    "Forge"),
    # Whitespace tolerance — same suggestion logic applies after .strip()
    (" deep ",   "Deep"),
    ("\tquick\n", "Quick"),
    # difflib fuzzy match — handles single-character typos
    ("Deeep",    "Deep"),
    ("Quik",     "Quick"),
    ("Frge",     "Forge"),  # missing letter
    # Below cutoff — no suggestion is better than a wrong suggestion
    ("xyz",      None),
    ("",         None),
    ("   ",      None),
])
def test_suggest_valid_tier(bad, expected):
    """`Deep` is intentionally `None` because it's already valid; the function
    is only called from the invalid-override branch in production, but the
    parametrized case documents the expected return for an exact valid match."""
    if expected is None and bad in mod.VALID_TIERS:
        # Exact valid match: function does return the valid value via the
        # case-insensitive branch. Adjust expectation for those rows.
        assert mod.suggest_valid_tier(bad) == bad
    else:
        assert mod.suggest_valid_tier(bad) == expected


def test_suggest_valid_tier_for_non_string_returns_none():
    assert mod.suggest_valid_tier(None) is None
    assert mod.suggest_valid_tier(42) is None
    assert mod.suggest_valid_tier(["Deep"]) is None


def test_detect_invalid_override_with_no_close_match_has_null_suggestion():
    with _patch_all_probes(ag=True, gh=False, qm=False, cc=False):
        out = mod.detect(_detect_args(tier_override="xyzzy"))
    assert out["tier"]["override_invalid"] is True
    assert out["tier"]["override_invalid_value"] == "xyzzy"
    assert out["tier"]["override_invalid_suggestion"] is None


def test_detect_no_override_has_null_suggestion():
    """When no override is set, suggestion is null (suggestion is meaningful only with invalid override)."""
    with _patch_all_probes(ag=True, gh=True, qm=True, cc=True):
        out = mod.detect(_detect_args())
    assert out["tier"]["override_invalid"] is False
    assert out["tier"]["override_invalid_suggestion"] is None


def test_detect_valid_override_has_null_suggestion():
    """Valid override → no suggestion needed."""
    with _patch_all_probes(ag=True, gh=True, qm=True, cc=True):
        out = mod.detect(_detect_args(tier_override="Deep"))
    assert out["tier"]["override_applied"] is True
    assert out["tier"]["override_invalid"] is False
    assert out["tier"]["override_invalid_suggestion"] is None


def test_detect_require_tier_satisfied():
    with _patch_all_probes(ag=True, gh=True, qm=True, cc=True):
        out = mod.detect(_detect_args(require_tier="Forge+"))
    assert out["require_tier"]["requested"] == "Forge+"
    assert out["require_tier"]["satisfied"] is True
    assert out["require_tier"]["missing_tools"] == []


def test_detect_require_tier_not_satisfied():
    with _patch_all_probes(ag=True, gh=True, qm=True, cc=False):
        out = mod.detect(_detect_args(require_tier="Forge+"))
    # Calculated is Deep (ast+gh+qmd) but Forge+ requires ccc — not satisfied
    assert out["tier"]["calculated"] == "Deep"
    assert out["require_tier"]["satisfied"] is False
    assert out["require_tier"]["missing_tools"] == ["ccc"]


def test_detect_require_tier_invalid_value_dies():
    """Invalid --require-tier is a user error; --tier-override is not."""
    with _patch_all_probes(), pytest.raises(SystemExit) as exc:
        mod.detect(_detect_args(require_tier="quick"))
    assert exc.value.code == 1


VALID_LIST = "--require-tier must be one of Quick, Forge, Forge+, Deep (case-sensitive), got"


@pytest.mark.parametrize("value,expected", [
    ("Deep", None),
    ("Forge+", None),
    ("deep", f"{VALID_LIST} deep; did you mean Deep?"),
    ("FORGE+", f"{VALID_LIST} FORGE+; did you mean Forge+?"),
    ("forge plus", f"{VALID_LIST} forge plus"),
    ("", f"{VALID_LIST} an empty value"),
    ("Deep\n", f"{VALID_LIST} Deep?; did you mean Deep?"),
    ("it's \"x\"\\y", f"{VALID_LIST} it`s `x`/y"),
], ids=["valid", "valid-plus", "wrong-case", "wrong-case-plus", "no-close-match", "empty", "control-char",
        "quote-and-backslash"])
def test_require_tier_error_names_the_valid_tiers(value, expected):
    """setup carries the message into its blocked envelope's reason, so it
    names every tier, stays on one line and holds no quote or backslash."""
    message = mod.require_tier_error(value)
    assert message == expected
    if message:
        assert not set(message) & set("'\"\\\n")


def test_detect_rejects_a_bad_require_tier_before_any_probe(capsys):
    """A typo fails at once: no probe (up to 8 seconds each) runs first."""
    def never():
        raise AssertionError("a probe ran before --require-tier was checked")

    with patch.multiple(mod, probe_ast_grep=never, probe_gh_cli=never, probe_qmd=never, probe_ccc=never), \
            pytest.raises(SystemExit) as exc:
        mod.detect(_detect_args(require_tier="deep"))
    assert exc.value.code == 1
    assert json.loads(capsys.readouterr().err) == {"status": "error", "message": mod.require_tier_error("deep")}


# ─── CCC index freshness (compute_ccc_index_fresh) ───────────────────────────

from datetime import datetime, timedelta, timezone

# Fixed "now" so every freshness case is deterministic (same input → same bool).
_NOW = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)
_PROJ = "/home/user/proj"


def _fresh_prior(**over):
    """A prior-state dict that classifies as FRESH by default (1h-old index)."""
    base = {
        "previous_ccc_indexed_path": _PROJ,
        "previous_ccc_index_status": "created",
        "previous_ccc_last_indexed": (_NOW - timedelta(hours=1)).isoformat(),
        "previous_ccc_staleness_threshold_hours": 24,
    }
    base.update(over)
    return base


def test_ccc_fresh_baseline_true():
    assert mod.compute_ccc_index_fresh(_fresh_prior(), _PROJ, _NOW) is True


def test_ccc_fresh_boundary_exactly_at_threshold_is_fresh():
    """delta == threshold_hours is inclusive (<=) → still fresh."""
    prior = _fresh_prior(
        previous_ccc_last_indexed=(_NOW - timedelta(hours=24)).isoformat(),
        previous_ccc_staleness_threshold_hours=24,
    )
    assert mod.compute_ccc_index_fresh(prior, _PROJ, _NOW) is True


def test_ccc_fresh_boundary_just_over_threshold_is_stale():
    prior = _fresh_prior(
        previous_ccc_last_indexed=(_NOW - timedelta(hours=24, seconds=1)).isoformat(),
        previous_ccc_staleness_threshold_hours=24,
    )
    assert mod.compute_ccc_index_fresh(prior, _PROJ, _NOW) is False


def test_ccc_fresh_z_suffix_timestamp_parses():
    """A trailing 'Z' (UTC designator) must parse on Python 3.10 (no crash)."""
    prior = _fresh_prior(previous_ccc_last_indexed="2026-07-13T11:00:00Z")  # 1h before _NOW
    assert mod.compute_ccc_index_fresh(prior, _PROJ, _NOW) is True


def test_ccc_fresh_naive_timestamp_assumed_utc():
    """A timezone-naive timestamp is assumed UTC and compared without raising."""
    prior = _fresh_prior(previous_ccc_last_indexed="2026-07-13T11:00:00")  # 1h before _NOW
    assert mod.compute_ccc_index_fresh(prior, _PROJ, _NOW) is True


def test_ccc_fresh_unparseable_timestamp_is_false():
    prior = _fresh_prior(previous_ccc_last_indexed="not-a-timestamp")
    assert mod.compute_ccc_index_fresh(prior, _PROJ, _NOW) is False


@pytest.mark.parametrize("null_field", [
    "previous_ccc_indexed_path",
    "previous_ccc_index_status",
    "previous_ccc_last_indexed",
])
def test_ccc_fresh_required_field_null_is_false(null_field):
    """The three required fields, each null in turn, force a stale verdict.
    (The threshold field is the exception — see the 24h-default test below.)"""
    prior = _fresh_prior(**{null_field: None})
    assert mod.compute_ccc_index_fresh(prior, _PROJ, _NOW) is False


def test_ccc_fresh_threshold_null_defaults_to_24h():
    """Null threshold → 24h default (the staleness default in knowledge/ccc-bridge.md)."""
    # 23h-old index with no threshold set → fresh under the 24h default.
    prior = _fresh_prior(
        previous_ccc_last_indexed=(_NOW - timedelta(hours=23)).isoformat(),
        previous_ccc_staleness_threshold_hours=None,
    )
    assert mod.compute_ccc_index_fresh(prior, _PROJ, _NOW) is True
    # 25h-old index with no threshold set → stale under the 24h default.
    prior_stale = _fresh_prior(
        previous_ccc_last_indexed=(_NOW - timedelta(hours=25)).isoformat(),
        previous_ccc_staleness_threshold_hours=None,
    )
    assert mod.compute_ccc_index_fresh(prior_stale, _PROJ, _NOW) is False


def test_ccc_fresh_path_mismatch_is_false():
    prior = _fresh_prior(previous_ccc_indexed_path="/some/other/project")
    assert mod.compute_ccc_index_fresh(prior, _PROJ, _NOW) is False


def test_ccc_fresh_no_project_root_is_false():
    """No --project-root supplied → cannot confirm same-project → false."""
    assert mod.compute_ccc_index_fresh(_fresh_prior(), None, _NOW) is False


@pytest.mark.parametrize("status", ["failed", "skipped", "none", "error"])
def test_ccc_fresh_non_qualifying_status_is_false(status):
    prior = _fresh_prior(previous_ccc_index_status=status)
    assert mod.compute_ccc_index_fresh(prior, _PROJ, _NOW) is False


@pytest.mark.parametrize("status", ["fresh", "created"])
def test_ccc_fresh_qualifying_status_is_true(status):
    prior = _fresh_prior(previous_ccc_index_status=status)
    assert mod.compute_ccc_index_fresh(prior, _PROJ, _NOW) is True


def test_ccc_fresh_unparseable_threshold_is_false():
    prior = _fresh_prior(previous_ccc_staleness_threshold_hours="soon")
    assert mod.compute_ccc_index_fresh(prior, _PROJ, _NOW) is False


def _detect_args_full(**overrides):
    """Namespace including the --prior-state-from / --project-root fields that
    detect() reads via getattr (the lean _detect_args omits them)."""
    import argparse
    return argparse.Namespace(
        tier_override=overrides.get("tier_override"),
        require_tier=overrides.get("require_tier"),
        snyk_env_var=overrides.get("snyk_env_var", "SNYK_TOKEN_DOES_NOT_EXIST"),
        prior_state_from=overrides.get("prior_state_from"),
        project_root=overrides.get("project_root"),
    )


def test_detect_surfaces_ccc_index_fresh_from_prior_state(tmp_path):
    """End-to-end through detect(): a recent, same-project index reads as fresh."""
    recent = datetime.now(timezone.utc).isoformat()
    yaml_file = tmp_path / "forge-tier.yaml"
    yaml_file.write_text(
        "tier: Forge+\n"
        "tier_detected_at: 2026-01-01T00:00:00Z\n"
        "ccc_index:\n"
        "  status: created\n"
        f"  indexed_path: {tmp_path}\n"
        f"  last_indexed: '{recent}'\n"
        "  staleness_threshold_hours: 24\n",
        encoding="utf-8",
    )
    args = _detect_args_full(prior_state_from=str(yaml_file), project_root=str(tmp_path))
    with _patch_all_probes(ag=True, cc=True):
        out = mod.detect(args)
    assert out["prior"]["ccc_index_fresh"] is True


def test_detect_ccc_index_fresh_false_on_first_run():
    """No --prior-state-from / --project-root → first-run shape → not fresh."""
    with _patch_all_probes(ag=True, gh=True, qm=True, cc=True):
        out = mod.detect(_detect_args())
    assert out["prior"]["ccc_index_fresh"] is False


# ─── Prior CCC file_count (issue #473) ───────────────────────────────────────
# ccc-index.md's fresh-index branch binds `{ccc_file_count}` from
# `prior.previous_ccc_file_count`; before this key existed the flag was left
# unbound on every path that did not re-index, and write-config.md interpolated
# the literal placeholder into its JSON payload.


def test_read_prior_state_surfaces_ccc_file_count(tmp_path):
    yaml_file = tmp_path / "forge-tier.yaml"
    yaml_file.write_text(
        "tier: Deep\n"
        "ccc_index:\n"
        "  status: created\n"
        f"  indexed_path: {tmp_path}\n"
        "  last_indexed: '2026-07-13T11:00:00+00:00'\n"
        "  file_count: 1234\n",
        encoding="utf-8",
    )
    prior = mod.read_prior_state(str(yaml_file))
    assert prior["previous_ccc_file_count"] == 1234


def test_read_prior_state_ccc_file_count_null_when_absent(tmp_path):
    """A forge-tier.yaml without file_count (older writer, or a null value)
    yields None rather than a KeyError — same shape as the other prior keys."""
    yaml_file = tmp_path / "forge-tier.yaml"
    yaml_file.write_text("tier: Forge\nccc_index:\n  status: none\n", encoding="utf-8")
    prior = mod.read_prior_state(str(yaml_file))
    assert "previous_ccc_file_count" in prior
    assert prior["previous_ccc_file_count"] is None


def test_read_prior_state_first_run_shape_includes_ccc_file_count():
    """No prior file at all → the first-run shape still carries the key."""
    assert mod.read_prior_state(None)["previous_ccc_file_count"] is None
    absent = mod.read_prior_state("/definitely/not/here/forge-tier.yaml")
    assert absent["previous_ccc_file_count"] is None


_CCC_INDEX_STEP = Path(__file__).resolve().parent.parent / "src" / "skf-setup" / "references" / "ccc-index.md"
_DETECT_TIER_STEP = Path(__file__).resolve().parent.parent / "src" / "skf-setup" / "references" / "detect-and-tier.md"


def test_ccc_index_step_binds_no_index_field():
    """Step 1b binds no ccc_index field any more: the merge helper builds the
    index and writes its whole result to the run folder (#592), so no branch
    can leave a field unbound for write-tools."""
    text = _CCC_INDEX_STEP.read_text(encoding="utf-8")
    for gone in ("ccc_index_result:", "ccc_file_count:", "ccc_last_indexed:"):
        assert gone not in text, gone
    assert '--result-to "{run_dir}/ccc-exclusions.json"' in text


def test_fresh_index_count_comes_from_the_prior_record_not_from_step_1():
    """The fresh-index path re-counts nothing: the merge helper carries the count
    from the forge-tier.yaml it reads, so step 1 no longer maps it out."""
    detect_tier = _DETECT_TIER_STEP.read_text(encoding="utf-8")
    assert "previous_ccc_file_count" not in detect_tier
    merge = (Path(__file__).resolve().parent.parent / "src" / "shared" / "scripts"
             / "skf-merge-ccc-exclusions.py").read_text(encoding="utf-8")
    assert "keep   status \"fresh\"; last_indexed and file_count carry over from the" in merge


def test_detect_surfaces_previous_ccc_file_count_from_prior_state(tmp_path):
    """End-to-end through detect(): the count reaches the `prior` block that
    detect-and-tier.md maps into `{previous_ccc_file_count}`."""
    yaml_file = tmp_path / "forge-tier.yaml"
    yaml_file.write_text(
        "tier: Forge+\n"
        "ccc_index:\n"
        "  status: fresh\n"
        f"  indexed_path: {tmp_path}\n"
        "  file_count: 42\n",
        encoding="utf-8",
    )
    args = _detect_args_full(prior_state_from=str(yaml_file), project_root=str(tmp_path))
    with _patch_all_probes(ag=True, cc=True):
        out = mod.detect(args)
    assert out["prior"]["previous_ccc_file_count"] == 42


def test_a_rejected_require_tier_reaches_the_blocked_envelope_through_its_stderr_file(tmp_path):
    """determinism-3: step 1 saves the detector's stderr in the run folder and
    emit-blocked takes the message from it, so the did-you-mean hint arrives
    in the envelope with no reason typed by hand."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with open(run_dir / "detect-tools.err", "wb") as err:
        done = subprocess.run([sys.executable, str(SCRIPT_PATH), "--project-root", str(tmp_path),
                               "--require-tier", "deep"], stdout=subprocess.DEVNULL, stderr=err, timeout=30)
    assert done.returncode != 0
    text = _DETECT_TIER_STEP.read_text(encoding="utf-8")
    assert '2> "{run_dir}/detect-tools.err"' in text
    joined = re.sub(r"\\\n\s*", "", text)
    [call] = [line for line in joined.splitlines() if 'emit-blocked --phase "step 1:detect-tools"' in line]
    # A run whose customization resolver ran leaves out the optional resolver group.
    group = ' [--customization-resolver-unavailable "{customization_resolver_unavailable}"]'
    assert call.endswith(group), call
    call = call[:-len(group)]
    emitter = SCRIPT_PATH.parent / "skf-emit-result-envelope.py"
    values = {"emitEnvelopeHelper": emitter.as_posix(), "run_dir": run_dir.as_posix(),
              "project-root": tmp_path.as_posix()}
    words = shlex.split(re.sub(r"\{([\w-]+)\}", lambda m: values[m.group(1)], call))
    assert words[:3] == ["uv", "run", emitter.as_posix()], words
    blocked = subprocess.run([sys.executable, *words[2:]], capture_output=True, timeout=30)
    assert blocked.returncode == 0, blocked.stderr
    line = blocked.stdout.decode("utf-8").strip()
    error = json.loads(line[len("SKF_SETUP_RESULT_JSON: "):])["skf_setup"]["error"]
    assert error["phase"] == "step 1:detect-tools"
    assert error["reason"] == ("Setup cannot proceed: tool detection failed: --require-tier must be one of Quick, "
                               "Forge, Forge+, Deep (case-sensitive), got deep; did you mean Deep?")


# ─── End-to-end CLI integration ──────────────────────────────────────────────


def test_cli_emits_valid_json_on_stdout():
    """Invoke the script as a subprocess; JSON shape end-to-end."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--snyk-env-var", "DEFINITELY_NOT_SET_XYZ"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["version"] == "v1"
    assert set(payload["tools"].keys()) == {"ast_grep", "gh_cli", "qmd", "ccc", "git", "uv", "security_scan"}
    for key in ("ast_grep", "gh_cli", "qmd", "ccc", "git", "uv"):
        assert {"minimum", "meets_minimum", "below_minimum"} <= set(payload["tools"][key]), key
    assert payload["tools"]["ast_grep"]["minimum"] == "0.45.3"
    assert isinstance(payload["tools_below_minimum"], list)
    assert payload["tier"]["calculated"] in ("Quick", "Forge", "Forge+", "Deep")
    assert payload["tier"]["detected"] in ("Quick", "Forge", "Forge+", "Deep")
    assert payload["require_tier"] == {"requested": None, "satisfied": None, "missing_tools": []}


def test_cli_with_require_tier_below_actual():
    """If host has nothing, --require-tier=Quick should still pass (Quick = always)."""
    env = {k: v for k, v in os.environ.items() if k != "SNYK_TOKEN"}
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--require-tier", "Quick"],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["require_tier"]["satisfied"] is True


@pytest.mark.parametrize("args", [["--require-tier", "deep"], ["--require-tier=deep"], ["--require-tier=-Deep"]],
                         ids=["space", "equals", "equals-leading-dash"])
def test_cli_rejects_a_wrong_case_require_tier_naming_the_valid_tiers(args):
    """setup passes the = form, so even a value that starts with a dash
    reaches this check instead of argparse's usage error."""
    result = subprocess.run([sys.executable, str(SCRIPT_PATH), *args], capture_output=True, text=True,
                            timeout=30)
    assert result.returncode == 1 and result.stdout == ""
    message = json.loads(result.stderr)["message"]
    assert "Quick, Forge, Forge+, Deep" in message and message.endswith("did you mean Deep?")
