# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Skill Inventory — Scan skills directory and produce structured inventory.

Scans the skills output folder, reads manifests and metadata, resolves active
versions via symlinks, and outputs a JSON inventory. Reused by 9+ skills.

CLI: python3 skf-skill-inventory.py <skills-output-folder>
     python3 skf-skill-inventory.py <skills-output-folder> --skill <name>
     python3 skf-skill-inventory.py <skills-output-folder> --manifest-only
     python3 skf-skill-inventory.py <skills-output-folder> --match-target <url-or-name>

The --match-target mode deterministically computes coexistence matches: it
normalizes scheme / trailing .git / trailing slash, derives the expected kebab
skill name, compares case-insensitively, and emits a top-level `matches[]`
array. This replaces the equivalent normalize/derive/compare that a consuming
prompt would otherwise perform by hand (identical (target, inventory) always
yields the same match set).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


def read_json_file(path):
    """Read a JSON file, returning (data, None) or (None, error)."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f), None
    except FileNotFoundError:
        return None, f"Not found: {path}"
    except json.JSONDecodeError as e:
        return None, f"JSON parse error in {path}: {e}"


def resolve_active_version(skill_group_dir):
    """Resolve the active version for a skill group directory.

    Returns (version_string, resolved_path) or (None, None).
    """
    active_link = skill_group_dir / "active"
    if active_link.is_symlink() or active_link.is_dir():
        target = active_link.resolve()
        if target.is_dir():
            return target.name, target
    return None, None


def scan_skill_group(skill_group_dir, skill_name):
    """Scan a single skill group directory and return its inventory entry."""
    entry = {
        "name": skill_name,
        "path": str(skill_group_dir),
        "versions": [],
        "active_version": None,
        "active_path": None,
        "metadata": None,
        "has_skill_md": False,
        "has_provenance_map": False,
        "has_context_snippet": False,
        "errors": [],
    }

    # Check for version directories (contain a skill-name subdirectory)
    for child in sorted(skill_group_dir.iterdir()):
        if child.is_dir() and child.name != "active" and not child.name.startswith("."):
            # Check if this is a version dir (contains skill-name subdir or SKILL.md)
            skill_subdir = child / skill_name
            if skill_subdir.is_dir():
                entry["versions"].append(child.name)
            elif (child / "SKILL.md").exists():
                # Flat version dir without skill-name nesting
                entry["versions"].append(child.name)

    # Resolve active version
    active_ver, active_path = resolve_active_version(skill_group_dir)
    if active_ver:
        entry["active_version"] = active_ver
        # The active path points to the version dir; skill files are in version/skill-name/
        skill_pkg = active_path / skill_name
        if skill_pkg.is_dir():
            entry["active_path"] = str(skill_pkg)
        elif (active_path / "SKILL.md").exists():
            entry["active_path"] = str(active_path)
        else:
            entry["active_path"] = str(active_path)

    # If no versions found, check for flat layout (SKILL.md at group root)
    if not entry["versions"]:
        if (skill_group_dir / "SKILL.md").exists():
            entry["versions"].append("flat")
            entry["active_version"] = "flat"
            entry["active_path"] = str(skill_group_dir)

    # Load metadata from active path
    active_dir = Path(entry["active_path"]) if entry["active_path"] else None
    if active_dir and active_dir.is_dir():
        entry["has_skill_md"] = (active_dir / "SKILL.md").exists()
        entry["has_provenance_map"] = (active_dir / "provenance-map.json").exists()
        entry["has_context_snippet"] = (active_dir / "context-snippet.md").exists()

        metadata_path = active_dir / "metadata.json"
        meta, meta_err = read_json_file(metadata_path)
        if meta:
            entry["metadata"] = {
                "version": meta.get("version"),
                "language": meta.get("language"),
                "source_authority": meta.get("source_authority"),
                "source_repo": meta.get("source_repo"),
                "generated_by": meta.get("generated_by"),
                "confidence_tier": meta.get("confidence_tier"),
                "exports_total": meta.get("stats", {}).get("exports_total"),
            }
        elif meta_err and "Not found" not in meta_err:
            entry["errors"].append(meta_err)

    return entry


def normalize_url(value):
    """Normalize a URL / path / source_repo for case-insensitive comparison.

    Lowercase; strip an ``http://`` / ``https://`` scheme; strip a trailing
    ``.git`` suffix and any trailing slashes. Deterministic and idempotent, so
    ``https://github.com/Foo/Bar.git/`` and ``github.com/foo/bar`` normalize to
    the same value. Mirrors step-auto-scope §0c's URL-match normalization.
    """
    if not value:
        return ""
    s = str(value).strip().lower()
    for scheme in ("https://", "http://"):
        if s.startswith(scheme):
            s = s[len(scheme):]
            break
    s = s.rstrip("/")
    if s.endswith(".git"):
        s = s[:-4]
    s = s.rstrip("/")
    return s


def _kebab(segment):
    """Kebab-case, lowercase a single name segment (§6 skill-name rule).

    Lowercase, drop a trailing ``.git``, collapse every run of non-alphanumeric
    characters (``.``, ``_``, spaces, ...) to a single hyphen, and strip leading
    / trailing hyphens. ``docs.example.com`` -> ``docs-example-com`` (mirrors
    §0a's dot-to-hyphen), ``Bar`` -> ``bar``, ``my_project`` -> ``my-project``.
    """
    s = str(segment).strip().lower()
    if s.endswith(".git"):
        s = s[:-4]
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def derive_name(target):
    """Derive the expected skill name from a target URL / path / bare name.

    Mirrors step-auto-scope §6 (repo/package name = the last non-empty path
    segment, kebab-lowercased) and §0a (a bare doc hostname has its dots turned
    into hyphens). Both cases funnel through :func:`_kebab`, so
    ``github.com/x/bar-baz`` -> ``bar-baz`` and ``docs.example.com`` ->
    ``docs-example-com``. Returns "" when no segment can be derived.
    """
    if not target:
        return ""
    s = str(target).strip().lower()
    for scheme in ("https://", "http://"):
        if s.startswith(scheme):
            s = s[len(scheme):]
            break
    s = s.rstrip("/")
    if s.endswith(".git"):
        s = s[:-4]
    s = s.rstrip("/")
    segments = [seg for seg in s.split("/") if seg]
    if not segments:
        return ""
    return _kebab(segments[-1])


def compute_matches(skills, target):
    """Return the deterministic coexistence match set for ``target``.

    For each inventory skill, a hit fires when either the normalized
    ``metadata.source_repo`` equals the normalized target (URL match) or the
    derived expected name equals the skill's name, case-insensitively (name
    match). Each match entry is
    ``{name, active_version, source_repo, active_path, match_reason}`` where
    ``match_reason`` is ``"url"``, ``"name"``, or ``"both"``.
    """
    norm_target = normalize_url(target)
    derived = derive_name(target)
    matches = []
    for entry in skills:
        source_repo = None
        meta = entry.get("metadata")
        if meta:
            source_repo = meta.get("source_repo")
        url_match = (
            bool(source_repo)
            and norm_target != ""
            and normalize_url(source_repo) == norm_target
        )
        name_match = (
            bool(derived)
            and str(entry.get("name") or "").strip().lower() == derived
        )
        if not (url_match or name_match):
            continue
        if url_match and name_match:
            reason = "both"
        elif url_match:
            reason = "url"
        else:
            reason = "name"
        matches.append({
            "name": entry.get("name"),
            "active_version": entry.get("active_version"),
            "source_repo": source_repo,
            "active_path": entry.get("active_path"),
            "match_reason": reason,
        })
    return matches


def scan_inventory(skills_folder, skill_filter=None, manifest_only=False, match_target=None):
    """Scan the skills output folder and produce an inventory."""
    skills_dir = Path(skills_folder)

    if not skills_dir.is_dir():
        return {
            "status": "error",
            "error": f"Skills directory not found: {skills_dir}",
            "code": "DIR_NOT_FOUND",
        }

    result = {
        "status": "ok",
        "skills_folder": str(skills_dir),
        "manifest": None,
        "manifest_error": None,
        "skills": [],
        "summary": {
            "total_skills": 0,
            "total_versions": 0,
            "with_metadata": 0,
            "with_provenance": 0,
        },
    }

    # Load export manifest
    manifest_path = skills_dir / ".export-manifest.json"
    manifest, manifest_err = read_json_file(manifest_path)
    if manifest:
        result["manifest"] = manifest
    else:
        result["manifest_error"] = manifest_err

    if manifest_only:
        return result

    # Determine which skills to scan
    skill_names = set()

    # From manifest exports
    if manifest and "exports" in manifest:
        skill_names.update(manifest["exports"].keys())

    # From directory listing
    for child in skills_dir.iterdir():
        if child.is_dir() and not child.name.startswith("."):
            skill_names.add(child.name)

    # Apply filter
    if skill_filter:
        if skill_filter in skill_names:
            skill_names = {skill_filter}
        else:
            return {
                "status": "error",
                "error": f"Skill '{skill_filter}' not found in {skills_dir}",
                "code": "SKILL_NOT_FOUND",
                "available": sorted(skill_names),
            }

    # Scan each skill group
    for name in sorted(skill_names):
        skill_group_dir = skills_dir / name
        if skill_group_dir.is_dir():
            entry = scan_skill_group(skill_group_dir, name)
            result["skills"].append(entry)

    # Compute summary
    result["summary"]["total_skills"] = len(result["skills"])
    result["summary"]["total_versions"] = sum(len(s["versions"]) for s in result["skills"])
    result["summary"]["with_metadata"] = sum(1 for s in result["skills"] if s["metadata"])
    result["summary"]["with_provenance"] = sum(1 for s in result["skills"] if s["has_provenance_map"])

    # Coexistence matching (opt-in via --match-target; additive top-level key).
    if match_target is not None:
        result["matches"] = compute_matches(result["skills"], match_target)

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: python3 skf-skill-inventory.py <skills-output-folder> "
            "[--skill <name>] [--manifest-only] [--match-target <url-or-name>]",
            file=sys.stderr,
        )
        sys.exit(1)

    folder = sys.argv[1]
    skill = None
    manifest_only = "--manifest-only" in sys.argv
    match_target = None

    if "--skill" in sys.argv:
        idx = sys.argv.index("--skill")
        if idx + 1 < len(sys.argv):
            skill = sys.argv[idx + 1]

    if "--match-target" in sys.argv:
        idx = sys.argv.index("--match-target")
        if idx + 1 < len(sys.argv):
            match_target = sys.argv[idx + 1]

    result = scan_inventory(
        folder,
        skill_filter=skill,
        manifest_only=manifest_only,
        match_target=match_target,
    )
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "ok" else 1)
