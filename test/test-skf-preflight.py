#!/usr/bin/env python3
"""Tests for skf-preflight.py, and for the Ferris activation that runs it.

Ferris (src/skf-forger/SKILL.md) is the script's one caller, so its prose
contract is checked here too: the call it makes runs as written, it reads
only fields the script prints and binds each folder from its resolved path,
its halts name the installer the way the script and skf-setup do, WS reads
one forge-status.py call, its menu and the lifecycle knowledge fragment show
the pipeline aliases the parser expands with their arguments, and the
knowledge fragments count the workflows there are.
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
            preferences={"passive_context": True},
            forge_tier={"tier": "Forge+", "tier_detected_at": "2026-04-08"},
        )
        result = run_preflight(str(root))
        assert result["status"] == "ok"

    def test_project_name_resolved(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"passive_context": True},
            forge_tier={"tier": "Forge+", "tier_detected_at": "2026-04-08"},
        )
        result = run_preflight(str(root))
        assert result["config"]["project_name"] == "test-project"

    def test_user_name_resolved(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"passive_context": True},
            forge_tier={"tier": "Forge+", "tier_detected_at": "2026-04-08"},
        )
        result = run_preflight(str(root))
        assert result["config"]["user_name"] == "TestUser"

    def test_tier_forge_plus(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"passive_context": True},
            forge_tier={"tier": "Forge+", "tier_detected_at": "2026-04-08"},
        )
        result = run_preflight(str(root))
        assert result["derived"]["tier"] == "Forge+"

    def test_a_set_compact_greeting_is_ignored(self, tmp_path):
        """#1171: the preference is gone, so a value left in preferences.yaml
        changes nothing, no derived field carries it, and neither Ferris nor
        the docs name it: a returning user always gets the menu."""
        root = make_project(
            tmp_path,
            preferences={"compact_greeting": True},
            forge_tier={"tier": "Forge+", "tier_detected_at": "2026-04-08"},
        )
        result = run_preflight(str(root))
        assert result["status"] == "ok"
        assert result["derived"] == {"tier": "Forge+", "tier_source": "detected", "headless_mode": False,
                                     "is_first_run": False}
        for path in (FORGER_SKILL, SCRIPT, REPO / "src" / "forger" / "preferences.yaml",
                     REPO / "docs" / "agents.md", REPO / "docs" / "getting-started.md"):
            assert "compact_greeting" not in _read(path), path
        assert "Otherwise, present the menu." in _step("Greet, then dispatch or wait.")

    def test_not_first_run(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"passive_context": True},
            forge_tier={"tier": "Forge+", "tier_detected_at": "2026-04-08"},
        )
        result = run_preflight(str(root))
        assert result["derived"]["is_first_run"] is False

    def test_tier_source_detected(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"passive_context": True},
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

    def test_an_override_before_any_sf_run_is_a_tier(self, tmp_path):
        """The installer seeds `tier: ~`, and the workflows apply a valid `tier_override` over it, so Ferris's
        first-run gate reads `derived.tier`, not `is_first_run` (lane review finding 9)."""
        root = make_project(tmp_path, preferences={"tier_override": "Forge"}, forge_tier={"tier": None})
        derived = run_preflight(str(root))["derived"]
        assert (derived["tier"], derived["tier_source"], derived["is_first_run"]) == ("Forge", "override", True)


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
            preferences={"headless_mode": True},
            forge_tier={"tier": "Forge"},
        )
        result = run_preflight(str(root), allow_missing_sidecar=True)
        assert result["sidecar"]["missing"] is False
        assert result["derived"]["tier"] == "Forge"
        assert result["derived"]["headless_mode"] is True

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
    "preferences": {"passive_context": False, "headless_mode": True},
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
        # Only a YAML boolean counts.
        ({"headless_mode": "true"}, False),
        ({"passive_context": True}, False),
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

    def test_a_forge_tier_from_skf_1_with_unquoted_timestamps_prints_json(self, tmp_path):
        """#674: SKF 1.x wrote tier_detected_at and ccc_index.last_indexed
        unquoted, YAML reads them as datetimes, and the preflight crashed
        printing them, so setup and Ferris halted on a valid sidecar."""
        root = make_project(tmp_path)
        tier = root / "_bmad" / "_memory" / "forger-sidecar" / "forge-tier.yaml"
        tier.write_text(
            "tools:\n  ast_grep: true\ntier: Forge\n"
            "tier_detected_at: 2026-04-10T15:12:15Z\n"
            "ccc_index:\n  last_indexed: 2026-04-10\n  status: created\n",
            encoding="utf-8",
        )
        done = run_cli(str(root))
        assert done.returncode == 0, done.stdout + done.stderr
        forge_tier = json.loads(done.stdout)["sidecar"]["forge_tier"]
        assert forge_tier["tier_detected_at"] == "2026-04-10T15:12:15+00:00"
        assert forge_tier["ccc_index"]["last_indexed"] == "2026-04-10"

    def test_a_value_json_cannot_print_still_fails(self):
        with pytest.raises(TypeError):
            mod._json_default(object())

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


# ---------------------------------------------------------------- --helpers (#1117)

INSTALLED = "{project-root}/_bmad/skf/shared/scripts/"
DEV = "{project-root}/src/shared/scripts/"
RESOLVER = "skf-resolve-customization.py"


def probe_order(name, *prefixes):
    """A frontmatter `*ProbeOrder` list for `name`, installed path then dev path by default."""
    return "".join(f"  - '{prefix}{name}'\n" for prefix in (prefixes or (INSTALLED, DEV)))


def make_skill(root, stages):
    """A skill folder whose references/ holds each {relative path: frontmatter body}."""
    skill = Path(root) / "skill"
    for rel, frontmatter in stages.items():
        path = skill / "references" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\n{frontmatter}---\n\n# {rel}\n", encoding="utf-8")
    return skill


def place(root, name, installed=False, dev=True):
    """Put a stub helper at its installed path, its dev path, or both."""
    for wanted, folder in ((installed, ("_bmad", "skf", "shared", "scripts")), (dev, ("src", "shared", "scripts"))):
        if wanted:
            path = Path(root).joinpath(*folder, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# stub\n", encoding="utf-8")


DETECT = "detectToolsProbeOrder:\n" + probe_order("skf-detect-tools.py")


class TestPreflightHelpers:
    """Suite 11: --helpers resolves every `*ProbeOrder` of a skill's stages into one map."""

    def test_installed_path_wins(self, tmp_path):
        root = make_project(tmp_path)
        place(root, "skf-detect-tools.py", installed=True, dev=True)
        place(root, RESOLVER)
        result = run_preflight(str(root), helpers_root=make_skill(root, {"a.md": DETECT}))
        assert result["status"] == "ok", result
        assert result["helpers"]["detectTools"] == str(root.resolve() / "_bmad/skf/shared/scripts/skf-detect-tools.py")
        assert "helpers_missing" not in result

    def test_dev_path_when_not_installed(self, tmp_path):
        root = make_project(tmp_path)
        place(root, "skf-detect-tools.py")
        place(root, RESOLVER)
        result = run_preflight(str(root), helpers_root=make_skill(root, {"a.md": DETECT}))
        assert result["status"] == "ok", result
        assert result["helpers"] == {
            "detectTools": str(root.resolve() / "src/shared/scripts/skf-detect-tools.py"),
            "resolveCustomization": str(root.resolve() / "src/shared/scripts" / RESOLVER),
        }

    def test_missing_helper_halts_naming_it_with_the_config_still_printed(self, tmp_path):
        root = make_project(tmp_path, preferences={"headless_mode": True})
        place(root, RESOLVER)
        skill = make_skill(root, {"a.md": DETECT, "b.md": "emitEnvelopeProbeOrder:\n"
                                  + probe_order("skf-emit-result-envelope.py")})
        done = run_cli(str(root), "--helpers", str(skill))
        assert done.returncode == 1, done.stdout + done.stderr
        out = json.loads(done.stdout)
        assert out["status"] == "hard-halt" and out["code"] == "HELPERS_MISSING"
        assert out["helpers"]["detectTools"] is None and out["helpers"]["emitEnvelope"] is None
        assert out["helpers_missing"] == ["skf-detect-tools.py", "skf-emit-result-envelope.py"]
        assert out["error"] == ("Cannot initialize. SKF helpers not found: skf-detect-tools.py, "
                                "skf-emit-result-envelope.py. Reinstall SKF, then retry.")
        assert out["config"]["project_name"] == "test-project"
        assert out["derived"]["headless_mode"] is True
        assert out["sidecar"]["missing"] is False

    def test_a_stem_two_stages_share_is_one_key(self, tmp_path):
        root = make_project(tmp_path)
        place(root, "skf-detect-tools.py")
        place(root, RESOLVER)
        skill = make_skill(root, {"a.md": DETECT, "nested/b.md": "nextStepFile: 'a.md'\n" + DETECT})
        result = run_preflight(str(root), helpers_root=skill)
        assert result["status"] == "ok", result
        assert sorted(result["helpers"]) == ["detectTools", "resolveCustomization"]

    def test_a_stem_only_a_nested_stage_declares_is_read(self, tmp_path):
        root = make_project(tmp_path)
        place(root, "skf-detect-tools.py")
        place(root, "skf-fetch-temporal.py")
        place(root, RESOLVER)
        skill = make_skill(root, {"a.md": DETECT, "sub/deeper/b.md": "fetchTemporalProbeOrder:\n"
                                  + probe_order("skf-fetch-temporal.py")})
        result = run_preflight(str(root), helpers_root=skill)
        assert result["status"] == "ok", result
        assert result["helpers"]["fetchTemporal"] == str(root.resolve() / "src/shared/scripts/skf-fetch-temporal.py")

    def test_a_nested_stage_with_another_list_for_a_stem_is_malformed(self, tmp_path):
        root = make_project(tmp_path)
        place(root, "skf-detect-tools.py")
        place(root, RESOLVER)
        skill = make_skill(root, {"a.md": DETECT, "sub/b.md": "detectToolsProbeOrder:\n"
                                  + probe_order("skf-detect-tools.py", DEV)})
        result = run_preflight(str(root), helpers_root=skill)
        assert result["code"] == "HELPERS_MALFORMED" and result["helpers"] is None, result
        assert str(skill / "references" / "sub" / "b.md") in result["error"]

    def test_one_stem_with_two_lists_is_malformed(self, tmp_path):
        root = make_project(tmp_path)
        place(root, "skf-detect-tools.py")
        place(root, RESOLVER)
        skill = make_skill(root, {"a.md": DETECT, "b.md": "detectToolsProbeOrder:\n"
                                  + probe_order("skf-detect-tools.py", DEV)})
        done = run_cli(str(root), "--helpers", str(skill))
        assert done.returncode == 1
        out = json.loads(done.stdout)
        assert out["code"] == "HELPERS_MALFORMED" and out["helpers"] is None
        assert "detectToolsProbeOrder differs between " in out["error"]
        assert str(skill / "references" / "a.md") in out["error"] and str(skill / "references" / "b.md") in out["error"]

    def test_a_stage_that_redeclares_the_built_in_differently_is_malformed(self, tmp_path):
        root = make_project(tmp_path)
        place(root, RESOLVER)
        skill = make_skill(root, {"a.md": "resolveCustomizationProbeOrder:\n" + probe_order(RESOLVER, DEV)})
        result = run_preflight(str(root), helpers_root=skill)
        assert result["code"] == "HELPERS_MALFORMED"
        assert "resolveCustomizationProbeOrder differs between skf-preflight.py and " in result["error"]

    @pytest.mark.parametrize("stages", [
        None,
        {"a.md": "a: [\n"},
        {"a.md": "xProbeOrder: 3\n"},
        {"a.md": "xProbeOrder: []\n"},
        {"a.md": "xProbeOrder:\n  - 3\n"},
        {"a.md": "- xProbeOrder\n"},
    ], ids=["skill-root-not-a-folder", "not-yaml", "a-number", "an-empty-list", "not-strings", "not-a-mapping"])
    def test_bad_input_is_malformed(self, tmp_path, stages):
        root = make_project(tmp_path)
        place(root, RESOLVER)
        if stages is None:
            skill = root / "skill.md"
            skill.write_text("not a folder\n", encoding="utf-8")
        else:
            skill = make_skill(root, stages)
        done = run_cli(str(root), "--helpers", str(skill))
        assert done.returncode == 1, done.stdout
        out = json.loads(done.stdout)
        assert out["status"] == "hard-halt" and out["code"] == "HELPERS_MALFORMED"
        assert out["error"].startswith("Cannot initialize. ") and out["error"].endswith(". Reinstall SKF, then retry.")
        assert "\n" not in out["error"]
        assert str(skill if stages is None else skill / "references" / "a.md") in out["error"]
        assert out["config"]["project_name"] == "test-project"

    def test_the_config_halts_first_and_keeps_its_code(self, tmp_path):
        """No config.yaml and a missing helper: the installer is the remedy, with the map attached."""
        skill = make_skill(tmp_path, {"a.md": DETECT})
        done = run_cli(str(tmp_path), "--allow-missing-sidecar", "--helpers", str(skill))
        assert done.returncode == 1
        out = json.loads(done.stdout)
        assert out["code"] == "CONFIG_MISSING"
        assert "npx bmad-module-skill-forge install" in out["error"]
        assert out["helpers"] == {"detectTools": None, "resolveCustomization": None}
        assert out["helpers_missing"] == ["skf-detect-tools.py", RESOLVER]

    def test_the_customization_resolver_is_always_resolved(self, tmp_path):
        root = make_project(tmp_path)
        skill = tmp_path / "bare-skill"
        skill.mkdir()
        result = run_preflight(str(root), helpers_root=skill)
        assert result["code"] == "HELPERS_MISSING"
        assert result["helpers"] == {"resolveCustomization": None}
        place(root, RESOLVER, installed=True)
        result = run_preflight(str(root), helpers_root=skill)
        assert result["status"] == "ok"
        assert result["helpers"] == {
            "resolveCustomization": str(root.resolve() / "_bmad/skf/shared/scripts" / RESOLVER)}

    def test_entries_resolve_from_the_project_root(self, tmp_path):
        """A relative entry joins the project root, and one with any other placeholder never matches."""
        root = make_project(tmp_path)
        place(root, RESOLVER)
        (root / "tools").mkdir()
        (root / "tools" / "relative.py").write_text("# stub\n", encoding="utf-8")
        (root / "{skill-root}").mkdir()
        (root / "{skill-root}" / "other.py").write_text("# stub\n", encoding="utf-8")
        skill = make_skill(root, {"a.md": "relativeProbeOrder:\n  - 'tools/relative.py'\n"
                                  "otherProbeOrder:\n  - '{skill-root}/other.py'\n"})
        result = run_preflight(str(root), helpers_root=skill)
        assert result["helpers"]["relative"] == str(root.resolve() / "tools" / "relative.py")
        assert result["helpers"]["other"] is None
        assert result["helpers_missing"] == ["other.py"]

    def test_crlf_frontmatter_and_keys_that_are_not_probe_orders(self, tmp_path):
        root = make_project(tmp_path)
        place(root, "skf-detect-tools.py")
        place(root, RESOLVER)
        skill = tmp_path / "skill"
        (skill / "references").mkdir(parents=True)
        (skill / "references" / "a.md").write_bytes(
            ("---\r\nnextStepFile: 'b.md'\r\nProbeOrder: 3\r\n# a comment\r\n" + DETECT.replace("\n", "\r\n")
             + "---\r\n\r\n# A\r\n").encode("utf-8"))
        (skill / "references" / "b.md").write_text("# No frontmatter\n\nxProbeOrder: 3\n", encoding="utf-8")
        (skill / "references" / "c.md").write_text("---\n# comments only\n---\n", encoding="utf-8")
        (skill / "references" / "d.txt").write_text("---\nxProbeOrder: 3\n---\n", encoding="utf-8")
        result = run_preflight(str(root), helpers_root=skill)
        assert result["status"] == "ok", result
        assert sorted(result["helpers"]) == ["detectTools", "resolveCustomization"]

    def test_the_keys_come_sorted(self, tmp_path):
        root = make_project(tmp_path)
        for name in ("skf-b.py", "skf-a.py", RESOLVER):
            place(root, name)
        skill = make_skill(root, {"a.md": "zedProbeOrder:\n" + probe_order("skf-b.py")
                                  + "alphaProbeOrder:\n" + probe_order("skf-a.py")})
        done = run_cli(str(root), "--helpers", str(skill))
        assert done.returncode == 0, done.stdout
        assert list(json.loads(done.stdout)["helpers"]) == ["alpha", "resolveCustomization", "zed"]

    def test_helpers_with_no_value_prints_the_usage(self, tmp_path):
        root = make_project(tmp_path)
        for args in (("--helpers",), ("--helpers", "--allow-missing-sidecar")):
            done = run_cli(str(root), *args)
            assert done.returncode == 1, args
            assert done.stdout == "", args
            assert "[--helpers <skill-root>]" in done.stderr, args

    def test_without_the_flag_the_output_is_unchanged(self, tmp_path):
        root = make_project(tmp_path, **RETURNING_USER)
        done = run_cli(str(root))
        assert done.returncode == 0
        out = json.loads(done.stdout)
        assert "helpers" not in out and "helpers_missing" not in out
        assert list(out) == ["status", "config", "sidecar", "derived"]
        assert done.stdout == json.dumps(mod.load_config_and_sidecar(str(root)), indent=2) + "\n"
        assert run_preflight(str(root)) == mod.load_config_and_sidecar(str(root))


SKILL_ROOTS = sorted(p for p in (REPO / "src").glob("skf-*") if (p / "references").is_dir())
SETUP_HELPERS = ["detectTools", "emitEnvelope", "forgeTierRw", "mergeCccExclusions", "qmdClassify",
                 "resolveCustomization"]


def _real_helpers(tmp_path, skill):
    config = tmp_path / "config.yaml"
    config.write_text(f"project_name: repo\nsidecar_path: {tmp_path.as_posix()}/sidecar\n", encoding="utf-8")
    done = run_cli(str(REPO), "--config-path", str(config), "--allow-missing-sidecar", "--helpers", str(skill))
    assert done.returncode == 0, done.stdout + done.stderr
    return json.loads(done.stdout)["helpers"]


@pytest.mark.parametrize("skill", SKILL_ROOTS, ids=lambda p: p.name)
def test_every_shipped_skill_resolves_every_helper(tmp_path, skill):
    """Every stage frontmatter in src/ parses, no stem has two lists, every stem a stage at any
    depth declares is in the map, and every helper ships."""
    helpers = _real_helpers(tmp_path, skill)
    declared = {"resolveCustomization"}
    for md in (skill / "references").rglob("*.md"):
        front = re.match(r"\A---\r?\n(.*?)^---", md.read_text(encoding="utf-8"), re.M | re.S)
        declared |= set(re.findall(r"^([A-Za-z][A-Za-z0-9]*)ProbeOrder:", front.group(1), re.M)) if front else set()
    assert set(helpers) == declared
    for stem, path in helpers.items():
        assert path is not None, stem
        assert Path(path).is_file() and Path(path).is_absolute(), (stem, path)


def test_setup_and_quick_skill_resolve_the_helpers_their_stages_declare(tmp_path):
    assert sorted(_real_helpers(tmp_path, REPO / "src" / "skf-setup")) == SETUP_HELPERS
    stems = set()
    for md in (REPO / "src" / "skf-quick-skill" / "references").glob("*.md"):
        stems |= set(re.findall(r"^([A-Za-z]+)ProbeOrder:", md.read_text(encoding="utf-8"), re.M))
    # No fixed count: a stage that gains a probe order (#1120) needs no edit here.
    assert stems and "resolveCustomization" not in stems
    assert sorted(_real_helpers(tmp_path, REPO / "src" / "skf-quick-skill")) == sorted(stems | {"resolveCustomization"})


# ---------------------------------------------------------------- Ferris runs this script

FORGER_SKILL = REPO / "src" / "skf-forger" / "SKILL.md"
FORGER_MANIFEST = REPO / "src" / "skf-forger" / "bmad-skill-manifest.yaml"
SETUP_SKILL = REPO / "src" / "skf-setup" / "SKILL.md"
LIFECYCLE = REPO / "src" / "knowledge" / "skill-lifecycle.md"
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
        """The guard runs before anything loads the config, the preflight and
        the customization resolver run in one message, and the resume offer
        is read before the greeting that carries it."""
        steps = _steps()
        expected = ["Config guard.", "Preflight.", "Resolve agent customization.", "Resolve `{headless_mode}`",
                    "Read the pipeline journal", "Greet, then dispatch or wait."]
        assert [t for _, t, _ in steps if t in expected] == expected
        assert [int(n) for n, _, _ in steps] == list(range(1, len(steps) + 1))

    def test_config_guard_runs_no_script(self):
        """A project with no config.yaml usually has no SKF scripts either."""
        guard = _step("Config guard.")
        assert "If `{project-root}/_bmad/skf/config.yaml` does not exist, HARD HALT" in guard
        assert "uv run" not in guard
        assert "<preflight>" not in guard

    def test_one_probe_then_the_preflight_and_the_resolver_in_one_message(self):
        """#1171 architecture-4: step 1 checks the config and both helpers in
        one call, its config halt winning whatever the helpers, then steps 2
        and 3 send their calls together, a preflight halt winning over the
        resolver's output and step 3's rules waiting for both."""
        intro = _activation().split("1. **Config guard.**", 1)[0]
        assert ("Steps 2 and 3 send their calls together, in one message; each other step waits for what an "
                "earlier one binds.") in intro
        guard = _step("Config guard.")
        assert "In one call that runs no script" in guard
        assert ("check which of these paths exist: `{project-root}/_bmad/skf/config.yaml`, the two "
                "`skf-preflight.py` paths step 2 names and the two `skf-resolve-customization.py` paths step 3 "
                "names") in guard
        assert "HARD HALT, whatever that check found for the helpers" in guard
        preflight = _step("Preflight.")
        assert preflight.lstrip().startswith("From step 1's check, resolve `<preflight>`")
        assert ("Otherwise run it once, in the same message as step 3's resolver call; a halt this call returns "
                "wins over anything the resolver printed:") in preflight
        assert "It loads the config" not in preflight
        assert "It prints one JSON object:" in preflight
        resolver = _step("Resolve agent customization.")
        assert ("(the first that exists), by step 1's check, and run this call in the same message as step 2's; "
                "the rules below apply once both calls return:") in resolver
        assert resolver.index("the rules below apply once both calls return") < resolver.index("```bash")
        assert "headless-gate-convention" not in _read(FORGER_SKILL)

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
        # --allow-missing-sidecar turns SIDECAR_MISSING into defaults, and
        # Ferris passes no --helpers, the only source of the HELPERS_ codes.
        reachable = codes - {"MISSING_DEPENDENCY", "SIDECAR_MISSING", "HELPERS_MISSING", "HELPERS_MALFORMED"}
        assert "--helpers" not in _step("Preflight.")
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
        assert "`QS[cocoindex] TS EX`" in capabilities

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

    def test_first_run_qs_says_what_it_enables(self):
        """#1171 agent-cohesion-5: principle 1 keeps its name and says where a
        citation is line-level, so the QS highlight no longer calls its skill
        an uncited draft."""
        principle = next(line for line in _section(_read(FORGER_SKILL), "## Identity & Principles").splitlines()
                         if line.startswith("- Zero hallucination tolerance"))
        assert principle == ("- Zero hallucination tolerance: every claim traces to the source, with a line-level "
                             "citation wherever the forge parses it and a T1-low label where it only reads it")
        # The install-time roster copy of the persona says the same (lane review finding 12).
        manifest = next(line for line in _read(FORGER_MANIFEST).splitlines() if line.startswith("principles:"))
        assert manifest.startswith(f'principles: "{principle[2:]}. ')
        greeting = _step("Greet, then dispatch or wait.")
        assert ("**QS** (fastest trial: a skill from a GitHub URL or package name in under a minute, its public API "
                "read from the source)") in greeting
        assert "uncited" not in _read(FORGER_SKILL)

    def test_second_workflow_offers_a_fresh_session_or_a_pipeline(self):
        """#1171: the fresh session is the remedy, its command carrying the
        rest of the chain, each option says what it trades, and the advice
        comes once per session."""
        dispatch = _activation().split("**Dispatch**", 1)[1]
        single = next(line for line in dispatch.splitlines() if line.startswith("- **Any other single code**"))
        for token in ("When another workflow already ran in this session and `{headless_mode}` is false, first say "
                      "in one line that context left over from that workflow can degrade this pick.",
                      "Then recommend the command to paste into a fresh session, carrying the rest of the chain from "
                      "this pick on (for example `@Ferris TS[cocoindex] EX`): it starts from a clean context, where "
                      "one workflow pasted alone (`@Ferris TS cocoindex`) keeps its own questions and a chain takes "
                      "its workflows' default answers.",
                      "When the rest of the chain holds more than this pick (CA, RS and DS always run alone), the "
                      "other option is the rest of the chain run now as a pipeline (for example `TS[cocoindex] EX`), "
                      "which keeps this session's context and takes the default answers.",
                      "Invoke the skill in place, with its own questions, only when the user asks for that.",
                      "Give this advice once per session: every later single code runs in place without it."):
            assert token in single, token
        assert "two documented options" not in single
        # The standing reminder every menu display ends on stays word for word.
        assert ('then the line "Run each workflow in a fresh context window for best results."'
                in _section(_read(FORGER_SKILL), "## Capabilities"))

    def test_a_described_goal_gets_one_recommendation(self):
        """#1171 agent-cohesion-6: a goal, not a code, gets one code, alias or
        chain from the lifecycle fragment's Workflow Selection table, and a
        headless start that describes one halts naming it."""
        dispatch = _activation().split("**Dispatch**", 1)[1]
        assert dispatch.startswith(": when the user responds with a code, number, command or described goal, "
                                   "or the invocation carries one (step 6):")
        bullets = [line for line in dispatch.splitlines() if line.startswith("- **")]
        goal = next(line for line in bullets if line.startswith("- **A described goal**"))
        assert bullets.index(goal) == bullets.index(next(b for b in bullets
                                                         if b.startswith("- **Any other single code**"))) - 1
        for token in ("not a code, number, alias, chain or a request that names one workflow plainly",
                      "load `knowledge/skill-lifecycle.md` and answer in one line with the one code, alias or chain "
                      "its Workflow Selection table (Example 1) recommends for that goal, written as a pick Dispatch "
                      "runs, with a `<...>` placeholder for each input it needs (the table's `AN → CS (batch)` reads "
                      "`AN[<project-path>] CS`), then wait for the pick",
                      "With no forge tier yet (`derived.tier` null), a recommendation that holds AN, BS, CS, SS, TS, "
                      "US or AS (every alias does) puts SF ahead of it as step 6 writes a first-run pick",
                      "When the invocation carries `--headless` or `-H`, run nothing and HARD HALT: \"**No workflow "
                      "named.** A headless start runs the code, alias or chain it names. For that goal, start me with "
                      "`<recommendation>`.\""):
            assert token in goal, token
        assert "{headless_mode}" not in goal  # a start headless only by preference waits at the menu
        assert "### Example 1: Workflow Selection Decision" in _read(LIFECYCLE)
        picks = _step("Greet, then dispatch or wait.").split("When the invocation carries a pick", 1)[1]
        picks = picks.split("greet in one line", 1)[0]
        assert "a goal it describes, such as `I want skills for my whole monorepo`, which goes to Dispatch's " \
               "described-goal bullet" in picks

    def test_ki_offers_to_explain_a_fragment(self):
        """#1171 enhancement-9: KI ends with an offer, and a named fragment is
        explained with the codes whose workflows use it, from the Knowledge
        Map."""
        ki = _inline("KI")
        assert ki.count("\n") == 1  # still one line
        display = ki.index("Load and display `{project-root}/_bmad/skf/knowledge/skf-knowledge-index.csv`")
        offer = ki.index("then offer in one line to explain any fragment by name")
        assert display < offer < ki.index("If the CSV is missing")
        assert ("When the user names one, load its `fragment_file` (a `knowledge/` path, resolved as **Conventions** "
                "say), explain it briefly and name the menu codes whose workflows put it to work, as the Key "
                "Workflows column of the Knowledge Map in `knowledge/overview.md` lists them.") in ki
        assert "| Key Workflows " in _read(REPO / "src" / "knowledge" / "overview.md")

    def test_no_prose_that_no_step_acts_on(self):
        """#1171 leanness-2, leanness-3 and architecture-6."""
        text = _read(FORGER_SKILL)
        critical = _section(text, "## Critical Actions")
        assert [line for line in critical.splitlines() if line.startswith("- ")][0].endswith(
            "to its own run folder under `{project-root}/_bmad-output/.skf-run/`.")
        assert len([line for line in critical.splitlines() if line.startswith("- ")]) == 2
        for gone in ("skf-knowledge-index.csv` to select", "reading from knowledge/ and workflow files elsewhere",
                     "`references/` holds the pipeline run procedure", "these rows carry no registered skill",
                     "It loads the config, resolves its folders", "for gate-type resolution"):
            assert gone not in text, gone
        assert ("e.g. `shared/references/pipeline-contracts.md` and `knowledge/skill-lifecycle.md`."
                in _section(text, "## Conventions"))

    def test_ws_reads_one_status_call(self):
        """#608 determinism-5: forge-status.py joins the briefs, the inventory,
        the test verdicts, the export manifest and the stopped chain's offer
        (test-skf-forge-status.py runs the call as written), so WS globs and
        reads none of them itself."""
        ws = _inline("WS")
        [call] = re.findall(r"`(uv run [^`]+)`", ws)
        assert call.startswith("uv run scripts/forge-status.py ")
        # The script finds the inventory under the project root: WS resolves no path itself.
        assert '--project-root "{project-root}"' in call
        assert "<inventory>" not in ws and "skf-skill-inventory.py" not in ws
        for source in ("the briefs", "the skills SKF generated", "their test verdicts", "the export manifest",
                       "a stopped pipeline's offer"):
            assert source in ws, source
        assert "skill-brief.yaml" not in ws and "skf-test-skill-result-latest.json" not in ws

    def test_ws_reads_the_tier_and_the_pending_chain_again(self):
        """SF or a stopped pipeline in the same session changes both after
        activation, and WS is an inline action the second-workflow warning
        does not cover."""
        ws = _inline("WS")
        assert "Read every source again each time WS runs" in ws
        assert "`derived.tier` and `derived.tier_source` from the On Activation step 2 preflight call, run again" in ws
        assert "a stopped pipeline's offer (the On Activation step 5 call)" in ws
        assert "resume offer from On Activation" not in ws

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
        assert "Test Skill's `skf-test-skill/references/init.md` §1b the test threshold each pipeline uses" in invocation
        assert ("A circuit breaker halts the pipeline on the gate a workflow's result fails: TS on any verdict but "
                "PASS, VS on zero coverage.") in invocation
        assert "falls below its quality threshold" not in invocation

    def test_shows_each_alias_with_its_arguments(self):
        """The alias lines take the arguments the parser binds, as the Pipelines paragraph shows them."""
        invocation = _section(_read(LIFECYCLE), "## Pipeline Invocation")
        pipelines = next(p for p in _read(FORGER_SKILL).split("\n\n") if p.startswith("**Pipelines.**"))
        for alias in parse_pipeline.ALIASES:
            [form] = re.findall(rf"`({re.escape(alias)}(?: <[^>`]+>)*)`", pipelines)
            assert re.search(rf"^{re.escape(form)}\s+#", invocation, re.M), form
        chain = ("A chain of codes whose first workflow lacks its input, such as `QS TS EX`, asks for that input "
                 "before any workflow runs (`SF` and `SS` take none), and a headless one halts there instead.")
        assert chain in invocation
        # The codes no bracket completes, as parse-pipeline.py's first_input reports them.
        for token in ("only as `forge <repo-url-or-path> <skill-name>`", "`RS` and `DS` need more than one bracket",
                      "a headless chain led by `CS` leaves the brief to create-skill"):
            assert token in invocation, token
        assert parse_pipeline.FORGE_FORM == "forge <repo-url-or-path> <skill-name>"
        assert set(parse_pipeline.ON_THEIR_OWN) == {"RS", "DS"}

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
