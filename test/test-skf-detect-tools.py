#!/usr/bin/env python3
"""Tests for skf-detect-tools.py.

Strategy:
- Tier truth table is enumerated exhaustively (16 rows over the 4-tool boolean
  product). Each row asserts the calculated tier and the satisfied/missing
  result for every possible --require-tier value.
- Tool probes are tested with mocked subprocess.run to cover normal,
  alias-shadowed, daemon-stopped, and timeout paths without hitting real
  binaries.
- CLI integration test invokes the script as a subprocess and validates the
  emitted JSON shape end-to-end.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

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


def test_probe_ast_grep_success():
    with patch.object(mod.subprocess, "run", return_value=_fake_run(0, "ast-grep 0.39.5\n")):
        result = mod.probe_ast_grep()
    assert result == {"available": True, "version": "ast-grep 0.39.5"}


def test_probe_ast_grep_not_installed():
    with patch.object(mod.subprocess, "run", side_effect=FileNotFoundError):
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
        if cmd == ["ccc", "--help"]:
            return _fake_run(0, help_output)
        if cmd == ["ccc", "doctor"]:
            return _fake_run(0, doctor_output)
        raise AssertionError(f"unexpected probe call: {cmd}")

    with patch.object(mod.subprocess, "run", side_effect=_side_effect):
        result = mod.probe_ccc()
    assert result["available"] is True
    assert result["daemon"] == "healthy"


def test_probe_ccc_identity_marker_absent_rejects_alias():
    """Foreign `ccc` binary (e.g. code2prompt alias) must not pass."""
    # Foreign tool exits 0 on --help but lacks the marker
    foreign_help = "Usage: ccc [OPTIONS]\n\nA generic tool that happens to use ccc as its name.\n"

    def _side_effect(cmd, **kwargs):
        if cmd == ["ccc", "--help"]:
            return _fake_run(0, foreign_help)
        raise AssertionError(
            "ccc doctor MUST NOT be called when identity marker is absent — "
            f"called with {cmd}"
        )

    with patch.object(mod.subprocess, "run", side_effect=_side_effect):
        result = mod.probe_ccc()
    assert result == {"available": False, "daemon": None, "version": None}


def test_probe_qmd_binary_present_daemon_stopped():
    def _side_effect(cmd, **kwargs):
        if cmd == ["qmd", "--version"]:
            return _fake_run(0, "qmd 1.2.3\n")
        if cmd == ["qmd", "status"]:
            return _fake_run(1, "", "qmd: daemon not running\n")
        raise AssertionError(f"unexpected: {cmd}")

    with patch.object(mod.subprocess, "run", side_effect=_side_effect):
        result = mod.probe_qmd()
    assert result == {"available": False, "status": "daemon_stopped", "version": "qmd 1.2.3"}


def test_probe_qmd_falls_back_to_help_when_version_unsupported():
    """Some qmd builds reject --version; fall back to --help for identity check."""
    def _side_effect(cmd, **kwargs):
        if cmd == ["qmd", "--version"]:
            return _fake_run(2, "", "unknown option --version\n")
        if cmd == ["qmd", "--help"]:
            return _fake_run(0, "qmd: a search engine\n")
        if cmd == ["qmd", "status"]:
            return _fake_run(0, "Operational\n")
        raise AssertionError(f"unexpected: {cmd}")

    with patch.object(mod.subprocess, "run", side_effect=_side_effect):
        result = mod.probe_qmd()
    assert result["available"] is True
    assert result["status"] == "healthy"


def test_probe_qmd_absent():
    with patch.object(mod.subprocess, "run", side_effect=FileNotFoundError):
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
    with patch.object(
        mod.subprocess,
        "run",
        side_effect=subprocess.TimeoutExpired(cmd=["x"], timeout=1),
    ):
        rc, stdout, stderr = mod._run(["x"])
    assert rc == 127 and stdout == "" and stderr == ""


# ─── Override + require-tier integration via detect() ────────────────────────


def _detect_args(**overrides):
    """Build an argparse.Namespace with detect() defaults."""
    import argparse
    return argparse.Namespace(
        tier_override=overrides.get("tier_override"),
        require_tier=overrides.get("require_tier"),
        snyk_env_var=overrides.get("snyk_env_var", "SNYK_TOKEN_DOES_NOT_EXIST"),
    )


def _patch_all_probes(ag=False, gh=False, qm=False, cc=False):
    return patch.multiple(
        mod,
        probe_ast_grep=lambda: {"available": ag, "version": "x" if ag else None},
        probe_gh_cli=lambda:   {"available": gh, "version": "x" if gh else None},
        probe_qmd=lambda:      {"available": qm,
                                "status": "healthy" if qm else "absent",
                                "version": "x" if qm else None},
        probe_ccc=lambda:      {"available": cc,
                                "daemon": "healthy" if cc else None,
                                "version": "x" if cc else None},
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
    assert set(payload["tools"].keys()) == {"ast_grep", "gh_cli", "qmd", "ccc", "security_scan"}
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
