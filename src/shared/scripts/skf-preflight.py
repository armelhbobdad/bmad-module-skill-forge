# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""SKF Preflight — Config and sidecar loader for all SKF skills.

Loads config.yaml, validates sidecar_path, loads preferences.yaml and
forge-tier.yaml, and outputs a unified JSON blob for step consumption.
Ferris (skf-forger) runs it at activation and again for WS, with
--allow-missing-sidecar.

CLI — invoke via `uv run` so the PEP 723 PyYAML dependency declared
above is auto-resolved on first call and cached. `docs/getting-started.md`
documents uv as the runtime prerequisite for exactly this. Bare
`python3` falls back to a defensive ImportError handler that emits
`{"error": "PyYAML not installed...", "code": "MISSING_DEPENDENCY"}`
on stdout — that fallback is the safety net, not the canonical path:

  uv run skf-preflight.py <project-root>
  uv run skf-preflight.py <project-root> --config-path <alt-config>
  uv run skf-preflight.py <project-root> --allow-missing-sidecar

--allow-missing-sidecar: a sidecar folder that does not exist yet (a first
run, before skf-setup writes it) is not a halt. The run goes on with empty
preferences and forge tier, and `sidecar.missing` is true.

Folder values: the BMAD Method installer writes each folder in config.yaml
as `{project-root}/<value>`, and the standalone installer writes it relative
to the project root. `config` keeps each raw value and adds its absolute
path: `output_folder_resolved`, `skills_output_folder_resolved`,
`forge_data_folder_resolved` ("" for an empty value) and
`sidecar_path_resolved`. A sidecar_path that still holds a placeholder once
`{project-root}` is expanded, such as `{sidecar_path}` or the `{value}` of
`{project-root}/{value}`, halts with SIDECAR_UNDEFINED, flag or not.

Output: JSON to stdout with all resolved config variables and sidecar state.
`sidecar.preferences` and `sidecar.forge_tier` are {} for a file that is
not there yet, and `sidecar.preferences_error` or
`sidecar.forge_tier_error` appears only for a file that is there but did not
load. `derived` holds what a greeting needs: `tier`, `tier_source`,
`compact_greeting`, `headless_mode` (true only for `headless_mode: true` in
preferences.yaml) and `is_first_run`.
Exit 0 on success, exit 1 on a hard halt, whose `code` is CONFIG_MISSING
(no config.yaml: SKF is not installed, so the error names the installer),
CONFIG_MALFORMED (config.yaml is there but cannot be read or is not a YAML
mapping), SIDECAR_UNDEFINED or, without --allow-missing-sidecar,
SIDECAR_MISSING.
"""

from __future__ import annotations

import json
import re
import stat
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print(
        json.dumps({
            "error": "PyYAML not installed. Invoke via `uv run` (auto-resolves PEP 723 deps — see docs/getting-started.md) or install manually with `pip install pyyaml`.",
            "code": "MISSING_DEPENDENCY",
        }),
    )
    sys.exit(1)


# skf-setup halts on a missing config.yaml and never writes one: only the
# installer does. Ferris's config guard and skf-setup's
# on-activation:config-missing reason name the same two commands.
INSTALL_REMEDY = (
    "From the project root, run npx bmad-module-skill-forge install "
    "(or npx bmad-method install and add SKF), then run the skf-setup skill."
)

# The BMAD Method installer writes folder values as `{project-root}/<value>`
# (module.yaml's `result`). Only a whole leading segment is the placeholder.
PROJECT_ROOT_RE = re.compile(r"\A\{project-root\}(?:[/\\]+|\Z)")
PLACEHOLDER_RE = re.compile(r"\{[^{}]*\}")
FOLDER_KEYS = ("output_folder", "skills_output_folder", "forge_data_folder")


def load_yaml_file(path):
    """Load a YAML mapping, returning (data, None) or (None, error_string).

    An empty file reads as an empty mapping. A file that is not there raises
    FileNotFoundError, which each caller reads its own way: CONFIG_MISSING
    for config.yaml, empty defaults for a sidecar file. Every file this
    script loads is a mapping of keys, so a file that is there but cannot be
    read, or whose top level is a list or a scalar, is an error instead of a
    crash.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        raise
    except yaml.YAMLError as e:
        return None, f"YAML parse error in {path}: {e}"
    except (OSError, ValueError) as e:
        # A folder named like the file, a parent folder that cannot be
        # searched, no read permission, or bytes that are not UTF-8.
        return None, f"Cannot read {path}: {e}"
    if data is None:
        return {}, None
    if not isinstance(data, dict):
        return None, f"Not a YAML mapping: {path} holds a {type(data).__name__}"
    return data, None


def load_sidecar_file(path):
    """Load a sidecar file. One that is not there yet reads as {}."""
    try:
        return load_yaml_file(path)
    except FileNotFoundError:
        return {}, None


def resolve_folder(value, project_root):
    """Return (absolute path, placeholder) for a folder value from config.yaml.

    A leading `{project-root}` segment becomes the project root, and a
    relative path is joined to it. `placeholder` is the first `{...}` token
    left after that, or None. An empty value gives ("", None).
    """
    if not value:
        return "", None
    value = str(value)
    anchored = PROJECT_ROOT_RE.match(value)
    rest = value[anchored.end():] if anchored else value
    placeholder = PLACEHOLDER_RE.search(rest)
    path = Path(rest)
    if not path.is_absolute():
        path = project_root / path
    return str(path), placeholder.group(0) if placeholder else None


def folder_missing(path):
    """True when no folder is at `path`.

    A folder that cannot be checked, such as one under a parent folder that
    cannot be searched, counts as there, so the reads that follow report why
    its files did not load. Path.is_dir() raises for that on Python 3.12 and
    returns False on 3.14.
    """
    try:
        return not stat.S_ISDIR(path.stat().st_mode)
    except (FileNotFoundError, NotADirectoryError):
        return True
    except (OSError, ValueError):
        return False


def run_preflight(project_root, config_path=None, allow_missing_sidecar=False):
    """Run preflight checks and return a result dict.

    `allow_missing_sidecar` turns a missing sidecar folder into empty
    defaults instead of the SIDECAR_MISSING halt.
    """
    project_root = Path(project_root).resolve()

    # 1. Load config.yaml
    if config_path:
        cfg_path = Path(config_path)
    else:
        cfg_path = project_root / "_bmad" / "skf" / "config.yaml"

    try:
        config, err = load_yaml_file(cfg_path)
    except FileNotFoundError:
        return {
            "status": "hard-halt",
            "error": f"Cannot initialize. SKF is not installed in this project ({cfg_path} not found). {INSTALL_REMEDY}",
            "code": "CONFIG_MISSING",
        }
    if err:
        # An update install restores an existing config.yaml as it is, so
        # this error names the file to repair instead of the installer.
        return {
            "status": "hard-halt",
            "error": (
                f"Cannot initialize. {' '.join(err.split())}. "
                "Repair the file, or restore it from version control, and retry."
            ),
            "code": "CONFIG_MALFORMED",
        }

    # 2. Resolve config variables
    resolved = {
        "project_root": str(project_root),
        "config_path": str(cfg_path),
        "project_name": config.get("project_name", ""),
        "output_folder": config.get("output_folder", ""),
        "user_name": config.get("user_name", ""),
        "communication_language": config.get("communication_language", "English"),
        "document_output_language": config.get("document_output_language", "English"),
        "sidecar_path": config.get("sidecar_path", ""),
        "skills_output_folder": config.get("skills_output_folder", ""),
        "forge_data_folder": config.get("forge_data_folder", ""),
    }
    for key in FOLDER_KEYS:
        resolved[f"{key}_resolved"] = resolve_folder(resolved[key], project_root)[0]

    # 3. Validate sidecar_path, before the folder check, so that
    # --allow-missing-sidecar never reads an unresolved path as a first run.
    # The advice is the standalone installer's relative value: unquoted, a
    # value that starts with {project-root} would be a YAML flow mapping.
    sidecar_path, placeholder = resolve_folder(resolved["sidecar_path"], project_root)
    if not sidecar_path or placeholder:
        found = f"holds the placeholder {placeholder}" if placeholder else "is not defined"
        return {
            "status": "hard-halt",
            "error": (
                f"Cannot initialize. sidecar_path {found} in {cfg_path}. "
                "Set sidecar_path to _bmad/_memory/forger-sidecar, a path from the project root, and retry. "
                "This is a known installer issue with prompt: false config variables."
            ),
            "code": "SIDECAR_UNDEFINED",
            "config": resolved,
        }

    sidecar_dir = Path(sidecar_path)
    sidecar_missing = folder_missing(sidecar_dir)
    if sidecar_missing and not allow_missing_sidecar:
        return {
            "status": "hard-halt",
            "error": f"Sidecar directory not found: {sidecar_dir}. Run skf-setup to initialize.",
            "code": "SIDECAR_MISSING",
            "config": resolved,
        }

    resolved["sidecar_path_resolved"] = str(sidecar_dir)

    # 4. Load sidecar files. A missing folder (allowed above) or a file not
    # written yet reads as empty defaults with no error: the installer writes
    # preferences.yaml, and skf-setup creates the folder and forge-tier.yaml
    # on its first run. An `*_error` field is left for a file that is there
    # but did not load.
    sidecar = {"missing": sidecar_missing}

    prefs_path = sidecar_dir / "preferences.yaml"
    prefs, prefs_err = ({}, None) if sidecar_missing else load_sidecar_file(prefs_path)
    if prefs_err:
        sidecar["preferences"] = None
        sidecar["preferences_error"] = prefs_err
    else:
        sidecar["preferences"] = prefs

    tier_path = sidecar_dir / "forge-tier.yaml"
    tier, tier_err = ({}, None) if sidecar_missing else load_sidecar_file(tier_path)
    if tier_err:
        sidecar["forge_tier"] = None
        sidecar["forge_tier_error"] = tier_err
    else:
        sidecar["forge_tier"] = tier

    # 5. Derive convenience fields
    tier_value = None
    if tier:
        tier_value = tier.get("tier")

    compact_greeting = False
    if prefs:
        compact_greeting = prefs.get("compact_greeting", False) is True

    headless_mode = False
    if prefs:
        headless_mode = prefs.get("headless_mode", False) is True

    tier_override = None
    if prefs:
        tier_override = prefs.get("tier_override")

    return {
        "status": "ok",
        "config": resolved,
        "sidecar": sidecar,
        "derived": {
            "tier": tier_override or tier_value,
            "tier_source": "override" if tier_override else ("detected" if tier_value else None),
            "compact_greeting": compact_greeting,
            "headless_mode": headless_mode,
            "is_first_run": tier_value is None,
        },
    }


USAGE = "Usage: uv run skf-preflight.py <project-root> [--config-path <path>] [--allow-missing-sidecar]"


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1].startswith("--"):
        print(USAGE, file=sys.stderr)
        sys.exit(1)

    proj_root = sys.argv[1]
    cfg_path = None

    if "--config-path" in sys.argv:
        idx = sys.argv.index("--config-path")
        if idx + 1 < len(sys.argv):
            cfg_path = sys.argv[idx + 1]

    result = run_preflight(proj_root, cfg_path, allow_missing_sidecar="--allow-missing-sidecar" in sys.argv)
    print(json.dumps(result, indent=2))
    sys.exit(1 if result["status"] == "hard-halt" else 0)
