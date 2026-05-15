#!/usr/bin/env python3
"""Tests for skf-update-active-symlink.py.

POSIX-only — Windows symlinks need admin/developer mode and don't support
the atomic temp-and-replace pattern this script relies on. Native Windows
is the same skip-territory as skf-atomic-write.py's flip-link primitive.

Covers update + verify subcommands:
  - idempotent no-op when target already correct
  - atomic flip from a different target
  - first-time creation (no prior link)
  - missing target directory → halt
  - mismatch detection in verify-only mode
  - refusal to overwrite a non-symlink path
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


# Hard skip on Windows — see module docstring.
pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="POSIX symlink semantics; Windows uses WSL2 per skf-atomic-write.py",
)


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-update-active-symlink.py"

spec = importlib.util.spec_from_file_location("skf_update_active_symlink", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Fixture helper
# --------------------------------------------------------------------------


def _make_group(tmp_path: Path, *versions: str) -> Path:
    """Build a skill_group dir with one or more version subdirectories."""
    group = tmp_path / "my-skill"
    group.mkdir()
    for v in versions:
        (group / v).mkdir()
    return group


# --------------------------------------------------------------------------
# read_link_target / atomic_flip_symlink
# --------------------------------------------------------------------------


class TestReadLinkTarget:
    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        assert mod.read_link_target(tmp_path / "nope") is None

    def test_returns_target_when_symlink(self, tmp_path: Path) -> None:
        target = tmp_path / "v1"
        target.mkdir()
        link = tmp_path / "active"
        os.symlink("v1", link)
        assert mod.read_link_target(link) == "v1"

    def test_raises_when_not_a_symlink(self, tmp_path: Path) -> None:
        # link path exists but is a real directory
        path = tmp_path / "active"
        path.mkdir()
        with pytest.raises(ValueError, match="not a symlink"):
            mod.read_link_target(path)


class TestAtomicFlip:
    def test_creates_first_time(self, tmp_path: Path) -> None:
        (tmp_path / "v1").mkdir()
        link = tmp_path / "active"
        mod.atomic_flip_symlink(link, "v1")
        assert link.is_symlink()
        assert os.readlink(link) == "v1"

    def test_replaces_existing(self, tmp_path: Path) -> None:
        (tmp_path / "v1").mkdir()
        (tmp_path / "v2").mkdir()
        link = tmp_path / "active"
        os.symlink("v1", link)
        mod.atomic_flip_symlink(link, "v2")
        assert os.readlink(link) == "v2"

    def test_no_orphan_temp_file_after_success(self, tmp_path: Path) -> None:
        (tmp_path / "v1").mkdir()
        link = tmp_path / "active"
        mod.atomic_flip_symlink(link, "v1")
        leftovers = [p for p in tmp_path.iterdir() if ".skf-symlink.tmp" in p.name]
        assert leftovers == []

    def test_cleans_stale_temp_from_prior_crash(self, tmp_path: Path) -> None:
        # simulate a crashed prior flip leaving the temp behind
        (tmp_path / "v1").mkdir()
        link = tmp_path / "active"
        stale_tmp = tmp_path / f".{link.name}.skf-symlink.tmp"
        os.symlink("v-crashed", stale_tmp)
        mod.atomic_flip_symlink(link, "v1")
        assert os.readlink(link) == "v1"
        assert not stale_tmp.exists()


# --------------------------------------------------------------------------
# update()
# --------------------------------------------------------------------------


class TestUpdate:
    def test_no_op_when_already_correct(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path, "1.0.0")
        os.symlink("1.0.0", group / "active")
        result = mod.update(group, "1.0.0")
        assert result["status"] == "ok"
        assert result["action_taken"] == "no-op"
        assert result["log_message"] == "active_symlink_update: ok (1.0.0)"

    def test_flip_when_different(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path, "1.0.0", "1.1.0")
        os.symlink("1.0.0", group / "active")
        result = mod.update(group, "1.1.0")
        assert result["status"] == "flipped"
        assert result["action_taken"] == "flipped"
        assert result["current_target"] == "1.1.0"
        assert "1.0.0 -> 1.1.0" in result["log_message"]
        # disk state matches
        assert os.readlink(group / "active") == "1.1.0"

    def test_first_time_creation(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path, "1.0.0")
        # no prior active symlink
        result = mod.update(group, "1.0.0")
        assert result["status"] == "flipped"
        assert (group / "active").is_symlink()

    def test_missing_target_dir(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path)  # no version dirs
        result = mod.update(group, "2.0.0")
        assert result["status"] == "missing-target"
        assert "does not exist" in result["halt_message"]
        # no symlink was created
        assert not (group / "active").exists()


# --------------------------------------------------------------------------
# verify()
# --------------------------------------------------------------------------


class TestVerify:
    def test_ok_when_match(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path, "1.0.0")
        os.symlink("1.0.0", group / "active")
        result = mod.verify(group, "1.0.0")
        assert result["status"] == "ok"
        assert result["current_target"] == "1.0.0"

    def test_mismatch_when_diverged(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path, "1.0.0", "1.1.0")
        os.symlink("1.0.0", group / "active")
        result = mod.verify(group, "1.1.0")
        assert result["status"] == "mismatch"
        assert "divergence" in result["halt_message"]
        assert "1.0.0" in result["halt_message"]
        assert "1.1.0" in result["halt_message"]

    def test_mismatch_when_link_missing(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path, "1.0.0")
        # no active symlink at all
        result = mod.verify(group, "1.0.0")
        assert result["status"] == "mismatch"


# --------------------------------------------------------------------------
# CLI integration
# --------------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


class TestCli:
    def test_update_no_op_exits_0(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path, "1.0.0")
        os.symlink("1.0.0", group / "active")
        result = _run_cli(
            "update", "--skill-group", str(group), "--version", "1.0.0"
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "ok"

    def test_update_flips_exits_0(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path, "1.0.0", "1.1.0")
        os.symlink("1.0.0", group / "active")
        result = _run_cli(
            "update", "--skill-group", str(group), "--version", "1.1.0"
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["status"] == "flipped"

    def test_update_missing_target_exits_2(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path)
        result = _run_cli(
            "update", "--skill-group", str(group), "--version", "2.0.0"
        )
        assert result.returncode == 2
        payload = json.loads(result.stdout)
        assert payload["status"] == "missing-target"

    def test_verify_mismatch_exits_2(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path, "1.0.0", "1.1.0")
        os.symlink("1.0.0", group / "active")
        result = _run_cli(
            "verify", "--skill-group", str(group), "--version", "1.1.0"
        )
        assert result.returncode == 2
        payload = json.loads(result.stdout)
        assert payload["status"] == "mismatch"

    def test_bad_skill_group_exits_1(self, tmp_path: Path) -> None:
        result = _run_cli(
            "update",
            "--skill-group", str(tmp_path / "missing"),
            "--version", "1.0.0",
        )
        assert result.returncode == 1
        assert "not a directory" in result.stderr

    def test_missing_subcommand_exits_2(self, tmp_path: Path) -> None:
        result = _run_cli()
        assert result.returncode == 2  # argparse missing required subparser
