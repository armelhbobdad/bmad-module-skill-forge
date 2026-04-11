# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Manifest Ops — CRUD operations on the export manifest.

Reads, adds, updates, removes entries in .export-manifest.json.
Used by export-skill, drop-skill, and rename-skill.

CLI: python3 skf-manifest-ops.py <skills-folder> <command> [args]

Commands:
  read                          — Read entire manifest
  get <skill-name>              — Get a single skill entry
  set <skill-name> <version>    — Add/update skill with active version
  remove <skill-name>           — Remove skill from manifest
  deprecate <skill-name> [ver]  — Mark skill or version as deprecated
  rename <old-name> <new-name>  — Rename a skill entry
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def read_manifest(manifest_path):
    """Read manifest file, returning (data, None) or (None, error).

    Handles both v1 (flat list) and v2 (dict) manifest formats.
    V1 manifests are migrated in-place to v2 on next write.
    Legacy `platforms` field at the version level is renamed to `ides`.
    """
    try:
        with open(manifest_path) as f:
            data = json.load(f)
        if data.get("schema_version") != "2":
            data = _migrate_v1_to_v2(data)
        data = _normalize_platforms_to_ides(data)
        return data, None
    except FileNotFoundError:
        return {"schema_version": "2", "exports": {}, "updated_at": None}, None
    except json.JSONDecodeError as e:
        return None, f"Manifest JSON parse error: {e}"


def _migrate_v1_to_v2(data):
    """Migrate a v1 manifest to v2 format in memory."""
    data["schema_version"] = "2"
    for skill_name, entry in data.get("exports", {}).items():
        versions = entry.get("versions", [])
        if isinstance(versions, list):
            active = entry.get("active_version", "")
            deprecated = entry.get("deprecated", False)
            new_versions = {}
            for v in versions:
                status = "active" if v == active and not deprecated else "archived"
                new_versions[v] = {
                    "ides": [],
                    "last_exported": data.get("updated_at", ""),
                    "status": "deprecated" if deprecated and v == active else status,
                }
            entry["versions"] = new_versions
        entry.pop("deprecated", None)
        entry.pop("deprecated_versions", None)
    return data


def _normalize_platforms_to_ides(data):
    """Rename legacy `platforms` key → `ides` on each version entry.

    Pre-rename v2 manifests used `platforms` for the list of IDE identifiers
    the version was exported to. The field was ambiguous (IDE name vs context
    file vs skill root), so it was renamed to `ides` to match
    `config.yaml.ides`. Existing manifests are upgraded on next read.
    """
    for entry in data.get("exports", {}).values():
        versions = entry.get("versions", {})
        if not isinstance(versions, dict):
            continue
        for v_data in versions.values():
            if not isinstance(v_data, dict):
                continue
            if "platforms" in v_data:
                legacy = v_data.pop("platforms")
                if "ides" not in v_data:
                    v_data["ides"] = legacy
    return data


def write_manifest(manifest_path, data):
    """Write manifest file atomically via write-to-temp-then-rename."""
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    manifest_path = Path(manifest_path)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=manifest_path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, manifest_path)
    except Exception:
        os.unlink(tmp_path)
        raise


def cmd_read(manifest_path):
    data, err = read_manifest(manifest_path)
    if err:
        return {"status": "error", "error": err}
    return {"status": "ok", "manifest": data}


def cmd_get(manifest_path, skill_name):
    data, err = read_manifest(manifest_path)
    if err:
        return {"status": "error", "error": err}
    exports = data.get("exports", {})
    if skill_name not in exports:
        return {"status": "not_found", "skill": skill_name, "available": sorted(exports.keys())}
    return {"status": "ok", "skill": skill_name, "entry": exports[skill_name]}


def cmd_set(manifest_path, skill_name, version):
    data, err = read_manifest(manifest_path)
    if err:
        return {"status": "error", "error": err}
    exports = data.setdefault("exports", {})
    existing = exports.get(skill_name, {})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Preserve existing versions dict, archive the previously-active version
    versions = existing.get("versions", {})
    if isinstance(versions, list):
        versions = {}  # Safety: handle any residual v1 data
    old_active = existing.get("active_version")
    if old_active and old_active in versions and old_active != version:
        versions[old_active]["status"] = "archived"

    # Add or update the new active version
    existing_version = versions.get(version, {})
    versions[version] = {
        "ides": existing_version.get("ides", existing_version.get("platforms", [])),
        "last_exported": today,
        "status": "active",
    }

    exports[skill_name] = {
        "active_version": version,
        "versions": versions,
    }
    write_manifest(manifest_path, data)
    return {"status": "ok", "action": "set", "skill": skill_name, "version": version}


def cmd_remove(manifest_path, skill_name):
    data, err = read_manifest(manifest_path)
    if err:
        return {"status": "error", "error": err}
    exports = data.get("exports", {})
    if skill_name not in exports:
        return {"status": "not_found", "skill": skill_name}
    removed = exports.pop(skill_name)
    write_manifest(manifest_path, data)
    return {"status": "ok", "action": "removed", "skill": skill_name, "removed_entry": removed}


def cmd_deprecate(manifest_path, skill_name, version=None):
    data, err = read_manifest(manifest_path)
    if err:
        return {"status": "error", "error": err}
    exports = data.get("exports", {})
    if skill_name not in exports:
        return {"status": "not_found", "skill": skill_name}
    versions = exports[skill_name].get("versions", {})
    if version:
        if version not in versions:
            return {"status": "error", "error": f"Version '{version}' not found for '{skill_name}'"}
        versions[version]["status"] = "deprecated"
    else:
        # Deprecate all versions
        for v in versions.values():
            v["status"] = "deprecated"
    write_manifest(manifest_path, data)
    return {"status": "ok", "action": "deprecated", "skill": skill_name, "version": version}


def cmd_rename(manifest_path, old_name, new_name):
    data, err = read_manifest(manifest_path)
    if err:
        return {"status": "error", "error": err}
    exports = data.get("exports", {})
    if old_name not in exports:
        return {"status": "not_found", "skill": old_name}
    if new_name in exports:
        return {"status": "error", "error": f"Target name '{new_name}' already exists in manifest"}
    exports[new_name] = exports.pop(old_name)
    write_manifest(manifest_path, data)
    return {"status": "ok", "action": "renamed", "from": old_name, "to": new_name}


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 skf-manifest-ops.py <skills-folder> <command> [args]", file=sys.stderr)
        print("Commands: read, get <name>, set <name> <version>, remove <name>, deprecate <name> [version], rename <old> <new>", file=sys.stderr)
        sys.exit(1)

    skills_folder = Path(sys.argv[1])
    command = sys.argv[2]
    manifest_path = skills_folder / ".export-manifest.json"

    if command == "read":
        result = cmd_read(manifest_path)
    elif command == "get" and len(sys.argv) >= 4:
        result = cmd_get(manifest_path, sys.argv[3])
    elif command == "set" and len(sys.argv) >= 5:
        result = cmd_set(manifest_path, sys.argv[3], sys.argv[4])
    elif command == "remove" and len(sys.argv) >= 4:
        result = cmd_remove(manifest_path, sys.argv[3])
    elif command == "deprecate" and len(sys.argv) >= 4:
        ver = sys.argv[4] if len(sys.argv) >= 5 else None
        result = cmd_deprecate(manifest_path, sys.argv[3], ver)
    elif command == "rename" and len(sys.argv) >= 5:
        result = cmd_rename(manifest_path, sys.argv[3], sys.argv[4])
    else:
        result = {"status": "error", "error": f"Unknown command or missing args: {command}"}

    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "ok" else 1)


if __name__ == "__main__":
    main()
