# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""SKF Preflight — Config and sidecar loader for all SKF skills.

Loads config.yaml, validates sidecar_path, loads preferences.yaml and
forge-tier.yaml, and outputs a unified JSON blob for step consumption.

CLI: python3 skf-preflight.py <project-root>
     python3 skf-preflight.py <project-root> --config-path <alt-config>

Output: JSON to stdout with all resolved config variables and sidecar state.
Exit 0 on success, exit 1 on hard-halt conditions (missing config, bad sidecar).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print(
        json.dumps({"error": "PyYAML not installed. Run: pip install pyyaml", "code": "MISSING_DEPENDENCY"}),
    )
    sys.exit(1)


def load_yaml_file(path):
    """Load a YAML file, returning (data, None) or (None, error_string)."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        return data or {}, None
    except FileNotFoundError:
        return None, f"File not found: {path}"
    except yaml.YAMLError as e:
        return None, f"YAML parse error in {path}: {e}"


def run_preflight(project_root, config_path=None):
    """Run preflight checks and return a result dict."""
    project_root = Path(project_root).resolve()

    # 1. Load config.yaml
    if config_path:
        cfg_path = Path(config_path)
    else:
        cfg_path = project_root / "_bmad" / "skf" / "config.yaml"

    config, err = load_yaml_file(cfg_path)
    if err:
        return {
            "status": "hard-halt",
            "error": f"Cannot initialize. SKF config not found at {cfg_path}. Run the skf-setup skill to initialize your forge environment.",
            "code": "CONFIG_MISSING",
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

    # 3. Validate sidecar_path
    sidecar_path = resolved["sidecar_path"]
    if not sidecar_path or sidecar_path == "{sidecar_path}":
        return {
            "status": "hard-halt",
            "error": (
                "Cannot initialize. sidecar_path is not defined in your installed config.yaml. "
                f"Add sidecar_path: {project_root}/_bmad/_memory/forger-sidecar to your project "
                "config.yaml and retry. This is a known installer issue with prompt: false config variables."
            ),
            "code": "SIDECAR_UNDEFINED",
            "config": resolved,
        }

    sidecar_dir = Path(sidecar_path)
    if not sidecar_dir.is_absolute():
        sidecar_dir = project_root / sidecar_path

    if not sidecar_dir.is_dir():
        return {
            "status": "hard-halt",
            "error": f"Sidecar directory not found: {sidecar_dir}. Run skf-setup to initialize.",
            "code": "SIDECAR_MISSING",
            "config": resolved,
        }

    resolved["sidecar_path_resolved"] = str(sidecar_dir)

    # 4. Load sidecar files
    sidecar = {}

    prefs_path = sidecar_dir / "preferences.yaml"
    prefs, prefs_err = load_yaml_file(prefs_path)
    if prefs_err:
        sidecar["preferences"] = None
        sidecar["preferences_error"] = prefs_err
    else:
        sidecar["preferences"] = prefs

    tier_path = sidecar_dir / "forge-tier.yaml"
    tier, tier_err = load_yaml_file(tier_path)
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
            "is_first_run": tier_value is None,
        },
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 skf-preflight.py <project-root> [--config-path <path>]", file=sys.stderr)
        sys.exit(1)

    proj_root = sys.argv[1]
    cfg_path = None

    if "--config-path" in sys.argv:
        idx = sys.argv.index("--config-path")
        if idx + 1 < len(sys.argv):
            cfg_path = sys.argv[idx + 1]

    result = run_preflight(proj_root, cfg_path)
    print(json.dumps(result, indent=2))
    sys.exit(1 if result["status"] == "hard-halt" else 0)
