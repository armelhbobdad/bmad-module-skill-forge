#!/usr/bin/env python3
"""Tests for skf-preflight.py, and for the Ferris activation that runs it.

Ferris (src/skf-forger/SKILL.md) is the script's one caller, so its prose
contract is checked here too: the call it makes runs as written, it reads
only fields the script prints and binds each folder from its resolved path,
its halts name the installer the way the script and skf-setup do, its menu
and the lifecycle knowledge fragment show the pipeline aliases the parser
expands, and the knowledge fragments count the workflows there are.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
SCRIPT = REPO / "src" / "shared" / "scripts" / "skf-preflight.py"

spec = importlib.util.spec_from_file_location("skf_preflight", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
run_preflight = mod.run_preflight


def make_project(tmpdir, config=None, sidecar=True, preferences=None, forge_tier=None):
    """Create a mock project structure for testing."""
    import yaml

    root = Path(tmpdir)
    cfg_dir = root / "_bmad" / "skf"
    cfg_dir.mkdir(parents=True, exist_ok=True)

    sidecar_dir = root / "_bmad" / "_memory" / "forger-sidecar"
    if sidecar:
        sidecar_dir.mkdir(parents=True, exist_ok=True)

    if config is None:
        config = {
            "project_name": "test-project",
            "output_folder": str(root / "_bmad-output"),
            "user_name": "TestUser",
            "communication_language": "English",
            "document_output_language": "English",
            "sidecar_path": str(sidecar_dir),
            "skills_output_folder": str(root / "skills"),
            "forge_data_folder": str(root / "forge-data"),
        }

    with open(cfg_dir / "config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(config, f)

    if sidecar and preferences is not None:
        with open(sidecar_dir / "preferences.yaml", "w", encoding="utf-8") as f:
            yaml.dump(preferences, f)

    if sidecar and forge_tier is not None:
        with open(sidecar_dir / "forge-tier.yaml", "w", encoding="utf-8") as f:
            yaml.dump(forge_tier, f)

    return root


class TestPreflightHappyPath:
    """Suite 1: Happy path -- full config + sidecar."""

    def test_status_ok(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"compact_greeting": True},
            forge_tier={"tier": "Forge+", "tier_detected_at": "2026-04-08"},
        )
        result = run_preflight(str(root))
        assert result["status"] == "ok"

    def test_project_name_resolved(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"compact_greeting": True},
            forge_tier={"tier": "Forge+", "tier_detected_at": "2026-04-08"},
        )
        result = run_preflight(str(root))
        assert result["config"]["project_name"] == "test-project"

    def test_user_name_resolved(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"compact_greeting": True},
            forge_tier={"tier": "Forge+", "tier_detected_at": "2026-04-08"},
        )
        result = run_preflight(str(root))
        assert result["config"]["user_name"] == "TestUser"

    def test_tier_forge_plus(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"compact_greeting": True},
            forge_tier={"tier": "Forge+", "tier_detected_at": "2026-04-08"},
        )
        result = run_preflight(str(root))
        assert result["derived"]["tier"] == "Forge+"

    def test_compact_greeting(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"compact_greeting": True},
            forge_tier={"tier": "Forge+", "tier_detected_at": "2026-04-08"},
        )
        result = run_preflight(str(root))
        assert result["derived"]["compact_greeting"] is True

    def test_not_first_run(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"compact_greeting": True},
            forge_tier={"tier": "Forge+", "tier_detected_at": "2026-04-08"},
        )
        result = run_preflight(str(root))
        assert result["derived"]["is_first_run"] is False

    def test_tier_source_detected(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"compact_greeting": True},
            forge_tier={"tier": "Forge+", "tier_detected_at": "2026-04-08"},
        )
        result = run_preflight(str(root))
        assert result["derived"]["tier_source"] == "detected"


class TestPreflightMissingConfig:
    """Suite 2: Missing config."""

    def test_hard_halt_on_missing_config(self, tmp_path):
        result = run_preflight(str(tmp_path))
        assert result["status"] == "hard-halt"

    def test_code_config_missing(self, tmp_path):
        result = run_preflight(str(tmp_path))
        assert result["code"] == "CONFIG_MISSING"

    def test_error_names_the_installer(self, tmp_path):
        """skf-setup halts on the same missing file and never writes it."""
        error = run_preflight(str(tmp_path))["error"]
        assert "SKF is not installed in this project" in error
        assert "npx bmad-module-skill-forge install" in error
        assert "npx bmad-method install" in error
        assert "to initialize your forge environment" not in error


def write_config(root, content):
    cfg = Path(root) / "_bmad" / "skf" / "config.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(content, encoding="utf-8")
    return cfg


class TestPreflightMalformedConfig:
    """Suite 2b: a config.yaml that exists but does not load."""

    def test_invalid_yaml(self, tmp_path):
        write_config(tmp_path, "project_name: [\n")
        result = run_preflight(str(tmp_path))
        assert result["status"] == "hard-halt"
        assert result["code"] == "CONFIG_MALFORMED"
        assert "YAML parse error" in result["error"]
        assert "\n" not in result["error"]

    def test_names_no_installer(self, tmp_path):
        """An update install restores the broken file as it is."""
        write_config(tmp_path, "project_name: [\n")
        error = run_preflight(str(tmp_path))["error"]
        assert "npx bmad-module-skill-forge install" not in error
        assert "Repair the file" in error

    def test_top_level_list(self, tmp_path):
        write_config(tmp_path, "- project_name\n")
        result = run_preflight(str(tmp_path))
        assert result["code"] == "CONFIG_MALFORMED"
        assert "Not a YAML mapping" in result["error"]

    def test_folder_in_place_of_the_file(self, tmp_path):
        (tmp_path / "_bmad" / "skf" / "config.yaml").mkdir(parents=True)
        result = run_preflight(str(tmp_path))
        assert result["code"] == "CONFIG_MALFORMED"
        assert "Cannot read" in result["error"]

    def test_empty_file_reads_as_an_empty_mapping(self, tmp_path):
        write_config(tmp_path, "")
        assert run_preflight(str(tmp_path))["code"] == "SIDECAR_UNDEFINED"


class TestPreflightMissingSidecar:
    """Suite 3: Missing sidecar directory (without --allow-missing-sidecar)."""

    def test_hard_halt_on_missing_sidecar(self, tmp_path):
        root = make_project(tmp_path, sidecar=False)
        result = run_preflight(str(root))
        assert result["status"] == "hard-halt"

    def test_code_sidecar_missing(self, tmp_path):
        root = make_project(tmp_path, sidecar=False)
        result = run_preflight(str(root))
        assert result["code"] == "SIDECAR_MISSING"


class TestPreflightFirstRun:
    """Suite 4: First run -- no forge-tier."""

    def test_status_ok(self, tmp_path):
        root = make_project(tmp_path)
        result = run_preflight(str(root))
        assert result["status"] == "ok"

    def test_is_first_run(self, tmp_path):
        root = make_project(tmp_path)
        result = run_preflight(str(root))
        assert result["derived"]["is_first_run"] is True

    def test_tier_none(self, tmp_path):
        root = make_project(tmp_path)
        result = run_preflight(str(root))
        assert result["derived"]["tier"] is None


class TestPreflightTierOverride:
    """Suite 5: Tier override."""

    def test_status_ok(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"tier_override": "Deep"},
            forge_tier={"tier": "Quick"},
        )
        result = run_preflight(str(root))
        assert result["status"] == "ok"

    def test_tier_deep_override(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"tier_override": "Deep"},
            forge_tier={"tier": "Quick"},
        )
        result = run_preflight(str(root))
        assert result["derived"]["tier"] == "Deep"

    def test_tier_source_override(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"tier_override": "Deep"},
            forge_tier={"tier": "Quick"},
        )
        result = run_preflight(str(root))
        assert result["derived"]["tier_source"] == "override"


class TestPreflightLiteralSidecarPath:
    """Suite 6: Literal sidecar_path string."""

    def test_hard_halt_on_literal_sidecar_path(self, tmp_path):
        root = make_project(tmp_path, config={
            "project_name": "test",
            "sidecar_path": "{sidecar_path}",
        })
        result = run_preflight(str(root))
        assert result["status"] == "hard-halt"

    def test_code_sidecar_undefined(self, tmp_path):
        root = make_project(tmp_path, config={
            "project_name": "test",
            "sidecar_path": "{sidecar_path}",
        })
        result = run_preflight(str(root))
        assert result["code"] == "SIDECAR_UNDEFINED"


class TestPreflightAllowMissingSidecar:
    """Suite 7: --allow-missing-sidecar reads a missing sidecar folder as empty defaults."""

    def test_status_ok(self, tmp_path):
        root = make_project(tmp_path, sidecar=False)
        result = run_preflight(str(root), allow_missing_sidecar=True)
        assert result["status"] == "ok"

    def test_empty_defaults(self, tmp_path):
        root = make_project(tmp_path, sidecar=False)
        result = run_preflight(str(root), allow_missing_sidecar=True)
        assert result["sidecar"] == {"missing": True, "preferences": {}, "forge_tier": {}}
        assert result["derived"] == {
            "tier": None,
            "tier_source": None,
            "compact_greeting": False,
            "headless_mode": False,
            "is_first_run": True,
        }

    def test_sidecar_path_resolved(self, tmp_path):
        root = make_project(tmp_path, sidecar=False)
        result = run_preflight(str(root), allow_missing_sidecar=True)
        expected = root / "_bmad" / "_memory" / "forger-sidecar"
        assert result["config"]["sidecar_path_resolved"] == str(expected)

    def test_relative_sidecar_path_resolves_from_the_project_root(self, tmp_path):
        """The standalone installer writes sidecar_path as a relative path."""
        root = make_project(tmp_path, sidecar=False, config={
            "user_name": "TestUser",
            "sidecar_path": "_bmad/_memory/forger-sidecar",
        })
        result = run_preflight(str(root), allow_missing_sidecar=True)
        expected = root.resolve() / "_bmad" / "_memory" / "forger-sidecar"
        assert result["config"]["sidecar_path_resolved"] == str(expected)

    def test_existing_sidecar_is_read_as_usual(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"compact_greeting": True},
            forge_tier={"tier": "Forge"},
        )
        result = run_preflight(str(root), allow_missing_sidecar=True)
        assert result["sidecar"]["missing"] is False
        assert result["derived"]["tier"] == "Forge"
        assert result["derived"]["compact_greeting"] is True

    def test_undefined_sidecar_path_still_halts(self, tmp_path):
        root = make_project(tmp_path, config={
            "project_name": "test",
            "sidecar_path": "{sidecar_path}",
        })
        result = run_preflight(str(root), allow_missing_sidecar=True)
        assert result["code"] == "SIDECAR_UNDEFINED"

    def test_missing_config_still_halts(self, tmp_path):
        result = run_preflight(str(tmp_path), allow_missing_sidecar=True)
        assert result["code"] == "CONFIG_MISSING"


# The folder values the BMAD Method installer writes (module.yaml's
# `result: "{project-root}/{value}"`), as BMAD 6.10.0 does.
BMAD_METHOD_CONFIG = {
    "user_name": "TestUser",
    "output_folder": "{project-root}/_bmad-output",
    "skills_output_folder": "{project-root}/skills",
    "forge_data_folder": "{project-root}/forge-data",
    "sidecar_path": "{project-root}/_bmad/_memory/forger-sidecar",
}
RETURNING_USER = {
    "preferences": {"compact_greeting": True, "headless_mode": True},
    "forge_tier": {"tier": "Forge"},
}


class TestPreflightProjectRootPlaceholder:
    """Suite 7b: folder values that start with {project-root} (#608)."""

    @pytest.mark.parametrize("allow", [False, True])
    def test_sidecar_is_found_and_read(self, tmp_path, allow):
        """Joined as a literal, the path pointed nowhere, and the flag read
        a returning user as a first run with no preferences."""
        root = make_project(tmp_path, config=BMAD_METHOD_CONFIG, **RETURNING_USER)
        result = run_preflight(str(root), allow_missing_sidecar=allow)
        assert result["status"] == "ok"
        assert result["sidecar"]["missing"] is False
        expected = root.resolve() / "_bmad" / "_memory" / "forger-sidecar"
        assert result["config"]["sidecar_path_resolved"] == str(expected)
        assert result["derived"] == {
            "tier": "Forge",
            "tier_source": "detected",
            "compact_greeting": True,
            "headless_mode": True,
            "is_first_run": False,
        }

    def test_folders_resolve_to_absolute_paths(self, tmp_path):
        root = make_project(tmp_path, config=BMAD_METHOD_CONFIG, **RETURNING_USER)
        config = run_preflight(str(root))["config"]
        base = root.resolve()
        assert config["output_folder_resolved"] == str(base / "_bmad-output")
        assert config["skills_output_folder_resolved"] == str(base / "skills")
        assert config["forge_data_folder_resolved"] == str(base / "forge-data")
        # The raw values stay as config.yaml holds them.
        assert config["skills_output_folder"] == "{project-root}/skills"

    def test_standalone_install_resolves_the_same_way(self, tmp_path):
        """The standalone installer writes the folders relative to the project root."""
        root = make_project(tmp_path, config={
            "user_name": "TestUser",
            "skills_output_folder": "skills",
            "forge_data_folder": "forge-data",
            "sidecar_path": "_bmad/_memory/forger-sidecar",
        })
        config = run_preflight(str(root))["config"]
        assert config["skills_output_folder_resolved"] == str(root.resolve() / "skills")
        assert config["forge_data_folder_resolved"] == str(root.resolve() / "forge-data")
        assert config["output_folder_resolved"] == ""

    @pytest.mark.parametrize(("value", "expected"), [
        ("{project-root}/skills", "skills"),
        ("{project-root}\\skills", "skills"),
        ("{project-root}//skills/", "skills"),
        ("./skills", "skills"),
        ("{project-root}", ""),
    ])
    def test_folder_value_forms(self, tmp_path, value, expected):
        root = tmp_path.resolve()
        assert mod.resolve_folder(value, root) == (str(root / expected), None)

    def test_absolute_and_empty_values(self, tmp_path):
        root = tmp_path.resolve()
        elsewhere = str(root / "elsewhere")
        assert mod.resolve_folder(elsewhere, root / "project") == (elsewhere, None)
        assert mod.resolve_folder("", root) == ("", None)
        assert mod.resolve_folder(None, root) == ("", None)

    @pytest.mark.parametrize(("value", "placeholder"), [
        ("{project-root}/{value}", "{value}"),
        ("{sidecar_path}", "{sidecar_path}"),
        ("{project-root}/_bmad/{value}", "{value}"),
        # With no separator after it, {project-root} is not the root.
        ("{project-root}_bmad/_memory/forger-sidecar", "{project-root}"),
    ])
    def test_unfilled_placeholder_halts_even_with_the_flag(self, tmp_path, value, placeholder):
        """Checked before the folder test, so the flag cannot turn it into a first run."""
        root = make_project(tmp_path, config={"user_name": "TestUser", "sidecar_path": value}, **RETURNING_USER)
        result = run_preflight(str(root), allow_missing_sidecar=True)
        assert result["status"] == "hard-halt"
        assert result["code"] == "SIDECAR_UNDEFINED"
        assert f"sidecar_path holds the placeholder {placeholder} in " in result["error"]

    def test_following_the_undefined_advice_reads_the_sidecar(self, tmp_path):
        root = make_project(tmp_path, config={"user_name": "TestUser", "sidecar_path": "{project-root}/{value}"},
                            **RETURNING_USER)
        error = run_preflight(str(root), allow_missing_sidecar=True)["error"]
        suggested = re.search(r"Set sidecar_path to (\S+?),", error).group(1)
        write_config(root, f"user_name: TestUser\nsidecar_path: {suggested}\n")
        result = run_preflight(str(root), allow_missing_sidecar=True)
        assert result["status"] == "ok"
        assert result["sidecar"]["missing"] is False
        assert result["derived"]["tier"] == "Forge"


class TestPreflightHeadlessMode:
    """Suite 8: derived.headless_mode mirrors preferences.yaml."""

    @pytest.mark.parametrize(("preferences", "expected"), [
        ({"headless_mode": True}, True),
        ({"headless_mode": False}, False),
        # Only a YAML boolean counts, as for compact_greeting.
        ({"headless_mode": "true"}, False),
        ({"compact_greeting": True}, False),
    ])
    def test_headless_mode(self, tmp_path, preferences, expected):
        root = make_project(tmp_path, preferences=preferences, forge_tier={"tier": "Forge"})
        assert run_preflight(str(root))["derived"]["headless_mode"] is expected

    def test_false_without_a_preferences_file(self, tmp_path):
        root = make_project(tmp_path, forge_tier={"tier": "Forge"})
        result = run_preflight(str(root))
        assert result["sidecar"]["preferences"] == {}
        assert "preferences_error" not in result["sidecar"]
        assert result["derived"]["headless_mode"] is False


class TestPreflightUnreadableSidecarFiles:
    """Suite 9: a sidecar file that does not load is reported, never a crash.
    A file that is not there yet is not an error."""

    def test_files_not_written_yet_read_as_empty(self, tmp_path):
        """The same shape as a missing folder under --allow-missing-sidecar,
        so an `*_error` field always means a file that is there but did not
        load."""
        root = make_project(tmp_path)
        result = run_preflight(str(root))
        assert result["status"] == "ok"
        assert result["sidecar"] == {"missing": False, "preferences": {}, "forge_tier": {}}
        assert result["derived"]["is_first_run"] is True

    def test_preferences_list(self, tmp_path):
        root = make_project(tmp_path, forge_tier={"tier": "Forge"})
        prefs = root / "_bmad" / "_memory" / "forger-sidecar" / "preferences.yaml"
        prefs.write_text("- headless_mode\n", encoding="utf-8")
        result = run_preflight(str(root))
        assert result["status"] == "ok"
        assert result["sidecar"]["preferences"] is None
        assert "Not a YAML mapping" in result["sidecar"]["preferences_error"]
        assert result["derived"]["headless_mode"] is False

    def test_forge_tier_scalar(self, tmp_path):
        root = make_project(tmp_path, preferences={})
        tier = root / "_bmad" / "_memory" / "forger-sidecar" / "forge-tier.yaml"
        tier.write_text("Forge\n", encoding="utf-8")
        result = run_preflight(str(root))
        assert result["status"] == "ok"
        assert "Not a YAML mapping" in result["sidecar"]["forge_tier_error"]
        assert result["derived"]["is_first_run"] is True


@contextlib.contextmanager
def cannot_search(folder):
    """Take every permission away from `folder`, then give them back."""
    mode = stat.S_IMODE(folder.stat().st_mode)
    folder.chmod(0)
    try:
        yield
    finally:
        folder.chmod(mode)


@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="needs POSIX folder permissions that bind the user running the tests",
)
class TestPreflightFolderThatCannotBeSearched:
    """Suite 9b: a folder that cannot be searched is reported as JSON on every
    Python version. Path.exists() and Path.is_dir() raise for it on 3.12 and
    return False on 3.14."""

    def test_config_folder_is_malformed_not_missing(self, tmp_path):
        """The file is there, so the installer is the wrong remedy."""
        root = make_project(tmp_path)
        with cannot_search(root / "_bmad" / "skf"):
            result = run_preflight(str(root))
        assert result["code"] == "CONFIG_MALFORMED"
        assert "Permission denied" in result["error"]
        assert "npx bmad-module-skill-forge install" not in result["error"]

    @pytest.mark.parametrize("allow", [False, True])
    def test_sidecar_parent_reports_both_files(self, tmp_path, allow):
        """Not a missing folder, and not a first run the flag would hide."""
        root = make_project(tmp_path, **RETURNING_USER)
        with cannot_search(root / "_bmad" / "_memory"):
            result = run_preflight(str(root), allow_missing_sidecar=allow)
        assert result["status"] == "ok"
        assert result["sidecar"]["missing"] is False
        for key in ("preferences_error", "forge_tier_error"):
            assert result["sidecar"][key].startswith("Cannot read "), key
            assert "Permission denied" in result["sidecar"][key], key


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )


class TestPreflightCli:
    """Suite 10: the command line."""

    def test_allow_missing_sidecar_flag(self, tmp_path):
        root = make_project(tmp_path, sidecar=False)
        done = run_cli(str(root), "--allow-missing-sidecar")
        assert done.returncode == 0, done.stdout + done.stderr
        assert json.loads(done.stdout)["sidecar"]["missing"] is True

    def test_missing_sidecar_halts_without_the_flag(self, tmp_path):
        root = make_project(tmp_path, sidecar=False)
        done = run_cli(str(root))
        assert done.returncode == 1
        assert json.loads(done.stdout)["code"] == "SIDECAR_MISSING"

    def test_flag_in_place_of_the_project_root(self, tmp_path):
        done = run_cli("--allow-missing-sidecar", str(tmp_path))
        assert done.returncode == 1
        assert done.stdout == ""
        assert "[--allow-missing-sidecar]" in done.stderr


# ---------------------------------------------------------------- Ferris runs this script

FORGER_SKILL = REPO / "src" / "skf-forger" / "SKILL.md"
FORGER_MANIFEST = REPO / "src" / "skf-forger" / "bmad-skill-manifest.yaml"
SETUP_SKILL = REPO / "src" / "skf-setup" / "SKILL.md"
LIFECYCLE = REPO / "src" / "knowledge" / "skill-lifecycle.md"
INVENTORY = REPO / "src" / "shared" / "scripts" / "skf-skill-inventory.py"
INSTALLERS = ("npx bmad-module-skill-forge install", "npx bmad-method install")

pp_spec = importlib.util.spec_from_file_location(
    "parse_pipeline", REPO / "src" / "skf-forger" / "scripts" / "parse-pipeline.py",
)
parse_pipeline = importlib.util.module_from_spec(pp_spec)
pp_spec.loader.exec_module(parse_pipeline)

STEP_RE = re.compile(r"^(\d+)\. \*\*(.+?)\*\*(.*?)(?=^\d+\. \*\*|\Z)", re.M | re.S)


def _read(path):
    return path.read_text(encoding="utf-8")


def _section(text, heading):
    m = re.search(rf"^{re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert m, f"section {heading!r} not found"
    return m.group(1)


def _activation():
    return _section(_read(FORGER_SKILL), "## On Activation")


def _steps():
    """(number, title, body) of each numbered On Activation step."""
    return STEP_RE.findall(_activation().split("**Dispatch**", 1)[0])


def _step(title):
    bodies = [body for _, t, body in _steps() if t == title]
    assert len(bodies) == 1, f"one step titled {title!r} expected, found {len(bodies)}"
    return bodies[0]


def _inline(code):
    """The Inline Actions entry for `code`, with its nested lines."""
    section = _section(_read(FORGER_SKILL), "## Inline Actions")
    entries = re.split(r"^(?=- \*\*)", section, flags=re.M)
    [entry] = [e for e in entries if e.startswith(f"- **{code}**")]
    return entry


def _call(text, placeholder):
    """The one `uv run` command in `text` that runs `placeholder`, split into
    words: an inline code span, or a line of fenced code."""
    spans = re.findall(r"`(uv run [^`\n]+)`", text)
    fenced = re.findall(r"^\s*(uv run [^`\n]+)$", text, re.M)
    calls = [call.strip() for call in spans + fenced if f'"{placeholder}"' in call]
    assert len(calls) == 1, calls
    return shlex.split(calls[0])


def _run_preflight_call(root):
    """Ferris's documented preflight call, run as written against `root`."""
    argv = _call(_step("Preflight."), "<preflight>")
    assert argv[:3] == ["uv", "run", "<preflight>"]
    values = {"<preflight>": str(SCRIPT), "{project-root}": str(root)}
    return subprocess.run(
        [sys.executable, *[values.get(a, a) for a in argv[2:]]],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )


class TestForgerActivation:
    """Suite 11: Ferris's On Activation runs this script (#608)."""

    def test_order(self):
        """The guard runs before anything loads the config, and the resume
        offer is read before the greeting that carries it."""
        steps = _steps()
        expected = ["Config guard.", "Preflight.", "Resolve `{headless_mode}`",
                    "Read the pipeline journal", "Greet, then dispatch or wait."]
        assert [t for _, t, _ in steps if t in expected] == expected
        assert [int(n) for n, _, _ in steps] == list(range(1, len(steps) + 1))

    def test_config_guard_runs_no_script(self):
        """A project with no config.yaml usually has no SKF scripts either."""
        guard = _step("Config guard.")
        assert "If `{project-root}/_bmad/skf/config.yaml` does not exist, HARD HALT" in guard
        assert "uv run" not in guard
        assert "<preflight>" not in guard

    def test_preflight_probes_the_installed_script_first(self):
        step = _step("Preflight.")
        assert ("`{project-root}/_bmad/skf/shared/scripts/skf-preflight.py` then "
                "`{project-root}/src/shared/scripts/skf-preflight.py`") in step
        assert "If neither exists, HARD HALT" in step

    def test_call_continues_on_a_first_run_without_a_sidecar(self, tmp_path):
        done = _run_preflight_call(make_project(tmp_path, sidecar=False))
        assert done.returncode == 0, done.stdout + done.stderr
        result = json.loads(done.stdout)
        assert result["status"] == "ok"
        assert result["sidecar"]["missing"] is True
        assert result["derived"]["is_first_run"] is True

    def test_call_reads_a_bmad_method_install(self, tmp_path):
        """With the {project-root} values the BMAD Method installer writes, the
        folder Ferris binds to {sidecar_path} holds the pipeline result step 4
        reads, and the returning user's preferences apply."""
        root = make_project(tmp_path, config=BMAD_METHOD_CONFIG, **RETURNING_USER)
        latest = root / "_bmad" / "_memory" / "forger-sidecar" / "pipeline-result-latest.json"
        latest.write_text(json.dumps({"summary": {"status": "failed"}}), encoding="utf-8")
        done = _run_preflight_call(root)
        assert done.returncode == 0, done.stdout + done.stderr
        result = json.loads(done.stdout)
        assert (Path(result["config"]["sidecar_path_resolved"]) / latest.name).is_file()
        assert result["derived"]["is_first_run"] is False
        assert result["derived"]["compact_greeting"] is True
        assert result["derived"]["headless_mode"] is True

    def test_binds_each_folder_from_its_resolved_path(self):
        """A raw folder value may start with {project-root} or be relative."""
        step = _step("Preflight.")
        for key in ("output_folder", "skills_output_folder", "forge_data_folder", "sidecar_path"):
            assert f"`{{{key}}}` from `config.{key}_resolved`" in step, key

    def test_reads_only_fields_the_script_prints(self, tmp_path):
        """Every `config.*`, `sidecar.*` and `derived.*` field Ferris reads is one
        the script prints in some state Ferris meets."""
        printed = {"config": set(), "sidecar": set(), "derived": set()}
        states = [
            {"preferences": {"headless_mode": True}, "forge_tier": {"tier": "Forge"}},
            {},  # a sidecar folder with no files
            {"sidecar": False},
            {"preferences": ["headless_mode"], "forge_tier": "Forge"},  # files that do not load
        ]
        for i, state in enumerate(states):
            result = run_preflight(str(make_project(tmp_path / str(i), **state)), allow_missing_sidecar=True)
            for part, keys in printed.items():
                keys.update(result[part])
        read = re.findall(r"`(config|sidecar|derived)\.([a-z_]+)`", _read(FORGER_SKILL))
        assert len(read) >= 5
        assert sorted(f"{part}.{key}" for part, key in read if key not in printed[part]) == []

    def test_names_every_halt_its_call_can_return(self):
        codes = set(re.findall(r'"code": "([A-Z_]+)"', _read(SCRIPT)))
        # MISSING_DEPENDENCY carries no status (the no-JSON branch covers it),
        # and --allow-missing-sidecar turns SIDECAR_MISSING into defaults.
        reachable = codes - {"MISSING_DEPENDENCY", "SIDECAR_MISSING"}
        named = set(re.findall(r"`([A-Z]+(?:_[A-Z]+)+)`", _step("Preflight.")))
        assert named == reachable

    def test_headless_mode_comes_from_the_preflight(self):
        step = _step("Resolve `{headless_mode}`")
        assert "`derived.headless_mode` is true" in step
        assert "preferences sets" not in step

    def test_resume_offer_is_read_before_the_greeting(self):
        step = _step("Read the pipeline journal")
        assert "uv run scripts/pipeline-journal.py resume" in step
        assert '--result-dir "{sidecar_path}"' in step
        greeting = _step("Greet, then dispatch or wait.")
        assert "resume offer" in greeting
        assert "End the greeting at the menu" in greeting

    def test_installer_remedy_is_the_same_everywhere(self, tmp_path):
        """skf-setup never writes config.yaml, only the installer does, so the
        three surfaces that meet a missing install all name it."""
        setup_reason = re.search(
            r"phase `on-activation:config-missing`[^\n]*?reason `([^`]+)`", _read(SETUP_SKILL),
        )
        assert setup_reason, "skf-setup config-missing halt not found"
        preflight = _step("Preflight.")
        surfaces = {
            "skf-preflight.py CONFIG_MISSING": run_preflight(str(tmp_path))["error"],
            "Ferris config guard": _step("Config guard."),
            "Ferris missing-script halt": preflight.split("If neither exists", 1)[1].split("Otherwise", 1)[0],
            "Ferris KI": _inline("KI"),
            "skf-setup config-missing reason": setup_reason.group(1),
        }
        missing = [(name, command) for name, text in surfaces.items()
                   for command in INSTALLERS if command not in text]
        assert missing == []
        assert "to initialize your forge environment" not in _read(FORGER_SKILL)
        assert "suggest running SF" not in _read(FORGER_SKILL)


class TestForgerMenu:
    """Suite 12: Ferris's menu, WS and modes (#608)."""

    def test_capabilities_name_every_pipeline_alias(self):
        capabilities = _section(_read(FORGER_SKILL), "## Capabilities")
        for alias in parse_pipeline.ALIASES:
            assert re.search(rf"`{re.escape(alias)}( <[^>`]+>)*`", capabilities), alias
        assert "`QS TS EX`" in capabilities

    def test_every_menu_display_shows_the_pipelines_and_the_fresh_context_line(self):
        """The greeting presents "the menu", which this rule defines, so a
        returning user sees the aliases too."""
        capabilities = _section(_read(FORGER_SKILL), "## Capabilities")
        assert ("Every display of this menu shows the table, then the **Pipelines** paragraph, then the line "
                '"Run each workflow in a fresh context window for best results."') in capabilities
        pipelines = next(p for p in capabilities.split("\n\n") if p.startswith("**Pipelines.**"))
        assert "below" not in pipelines  # users see this paragraph: no pointer into this file
        greeting = _step("Greet, then dispatch or wait.")
        assert "capabilities table" not in greeting
        assert greeting.count("present the menu") == 2

    def test_first_run_offers_forge_auto_after_sf_and_before_qs(self):
        greeting = _step("Greet, then dispatch or wait.")
        first_run = greeting.split("On a first run", 1)[1].split("Otherwise", 1)[0]
        paths = ["**SF**", "**forge-auto `<repo-or-doc-url>`**", "**QS**", "**BS**", "**KI**"]
        positions = [first_run.find(p) for p in paths]
        assert -1 not in positions, dict(zip(paths, positions))
        assert positions == sorted(positions)

    def test_second_workflow_offers_a_fresh_session_or_a_pipeline(self):
        dispatch = _activation().split("**Dispatch**", 1)[1]
        single = next(line for line in dispatch.splitlines() if line.startswith("- **Any other single code**"))
        assert "When another workflow already ran in this session and `{headless_mode}` is false" in single
        assert "fresh session (for example `@Ferris TS cocoindex`)" in single
        assert "as a pipeline (for example `TS EX`)" in single
        assert "in place only when the user asks for that" in single

    def test_ws_names_its_sources_and_the_next_codes(self):
        ws = _inline("WS")
        for source in ("`derived.tier`", "skf-skill-inventory.py", "`{forge_data_folder}/*/skill-brief.yaml`",
                       "skf-test-skill-result-latest.json", "resume offer"):
            assert source in ws, source
        assert ("`{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py` then "
                "`{project-root}/src/shared/scripts/skf-skill-inventory.py`") in ws
        for code in ("`CS <name>`", "`TS <name>`", "`US <name> --from-test-report`", "`EX <name>`"):
            assert code in ws, code

    def test_ws_reads_the_tier_and_the_pending_chain_again(self):
        """SF or a stopped pipeline in the same session changes both after
        activation, and WS is an inline action the second-workflow warning
        does not cover."""
        ws = _inline("WS")
        assert "Read every source again each time WS runs" in ws
        assert "`derived.tier` and `derived.tier_source` from the On Activation step 2 preflight call, run again" in ws
        assert "`pipeline-journal.py resume` call, run again" in ws
        assert "resume offer from On Activation" not in ws

    def test_ws_inventory_call_runs_as_written(self, tmp_path):
        argv = _call(_inline("WS"), "<inventory>")
        assert argv[:3] == ["uv", "run", "<inventory>"]
        skills, forge = tmp_path / "skills", tmp_path / "forge-data"
        skills.mkdir()
        forge.mkdir()
        values = {"<inventory>": str(INVENTORY), "{skills_output_folder}": str(skills),
                  "{forge_data_folder}": str(forge)}
        done = subprocess.run(
            [sys.executable, *[values.get(a, a) for a in argv[2:]]],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        assert done.returncode == 0, done.stdout + done.stderr
        result = json.loads(done.stdout)
        assert result["status"] == "ok"
        assert result["skills"] == [] and result["forge_groups"] == []

    def test_modes_match_the_agents_doc(self):
        """docs/agents.md maps Management to RS, DS and Campaign, and Delivery to EX."""
        identity = next(line for line in _read(FORGER_SKILL).splitlines() if "five modes" in line)
        manifest = next(line for line in _read(FORGER_MANIFEST).splitlines() if line.startswith("identity:"))
        for line in (identity, manifest):
            management = re.search(r"Management \(([^)]*)\)", line).group(1)
            assert "rename" in management and "drop" in management and "campaigns" in management, line
        roles = {"skf-export-skill": "Delivery", "skf-rename-skill": "Management",
                 "skf-drop-skill": "Management", "skf-campaign": "Management"}
        for skill, mode in roles.items():
            role = _section(_read(REPO / "src" / skill / "SKILL.md"), "## Role")
            assert f"{mode} mode" in role, skill


class TestLifecycleFragment:
    """Suite 13: the knowledge fragment skf-knowledge-index.csv lists for
    pipeline invocation syntax and aliases (#608)."""

    def test_lists_the_live_aliases_and_campaign(self):
        text = _read(LIFECYCLE)
        assert "onboard" not in text  # removed: the forger halts on it
        invocation = _section(text, "## Pipeline Invocation")
        for alias in parse_pipeline.ALIASES:
            assert re.search(rf"^{re.escape(alias)}\s", invocation, re.M), alias
        assert "`CA` (campaign) is not an alias" in invocation

    def test_states_no_threshold_of_its_own(self):
        invocation = _section(_read(LIFECYCLE), "## Pipeline Invocation")
        assert not re.search(r"score\s*[<>]", invocation)
        assert "`shared/references/pipeline-contracts.md` holds each alias's expansion and every threshold" in invocation

    def test_counts_and_places_every_workflow(self):
        """Every workflow on Ferris's menu sits in one lifecycle phase, and the
        fragment's count matches the workflow folders."""
        workflows = _menu_workflows()
        text = _read(LIFECYCLE)
        assert f"The {len(workflows)} SKF workflows" in text
        assert f"all {len(workflows)} workflow SKILL.md files" in text
        table = [line.split("|") for line in _section(text, "## Pipeline Phases").splitlines()
                 if line.startswith("| ")]
        placed = re.findall(r"\b[A-Z]{2}\b", " ".join(cells[2] for cells in table[1:]))
        assert sorted(placed) == workflows


def _menu_workflows():
    """The codes of the workflows on Ferris's menu, as many as the workflow
    folders (Ferris is not one)."""
    menu = _section(_read(FORGER_SKILL), "## Capabilities")
    rows = re.findall(r"^\| \d+ \| ([A-Z]{2}) \| .*? \| (\S+) \|$", menu, re.M)
    workflows = sorted(code for code, skill in rows if skill.startswith("skf-"))
    folders = [d for d in (REPO / "src").glob("skf-*") if d.is_dir() and d.name != "skf-forger"]
    assert len(workflows) == len(folders)
    return workflows


class TestKnowledgeOverview:
    """Suite 14: the knowledge overview counts the workflows as the lifecycle
    fragment does."""

    def test_counts_every_workflow(self):
        count = len(_menu_workflows())
        text = _read(REPO / "src" / "knowledge" / "overview.md")
        assert f"The SKF module has {count} workflows" in text
        row = next(line for line in text.splitlines() if line.startswith("| [skill-lifecycle.md]"))
        assert re.search(rf"\| All {count} +\|$", row), row
