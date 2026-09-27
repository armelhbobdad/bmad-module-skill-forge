# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Skill Inventory — Scan skills directory and produce structured inventory.

Scans the skills output folder, reads manifests and metadata, resolves active
versions via symlinks, and outputs a JSON inventory. Read by drop-skill and
rename-skill (roster and ownership), analyze-source (coexistence matches), and
the flat-layout fallback of update-skill, export-skill, audit-skill and
test-skill (the ownership gate before a flat skill is migrated).

CLI: uv run skf-skill-inventory.py <skills-output-folder>
     uv run skf-skill-inventory.py <skills-output-folder> --skill <name>
     uv run skf-skill-inventory.py <skills-output-folder> --manifest-only
     uv run skf-skill-inventory.py <skills-output-folder> --match-target <url-or-name>

Exit 0 when `status` is "ok"; exit 1 on an error (`DIR_NOT_FOUND`, or
`SKILL_NOT_FOUND` for `--skill`).

Ownership. The skills folder can hold skills SKF did not generate (a module's
own skills, skills installed from elsewhere). Only a `metadata.json` carrying
an SKF marker (`generated_by` naming an SKF generator, `tool_versions.skf`, or
`skill_type` with `forge_tier` or `confidence_tier`) proves that SKF generated
a skill, at the group root (flat layout) or at `{v}/{name}/metadata.json`
(versioned layout). The versioned layout, an `active` link, a manifest key or
a result file are not proof on their own. Each `skills[]` entry adds:

- `ownership`: "skf" (SKF evidence and nothing else), "mixed" (SKF evidence
  plus entries SKF did not generate) or "foreign" (no SKF evidence). Evidence
  is a marked version, a marked root `metadata.json`, the `_batch` folder, or
  `.skf-` in the folder name (`_has_skf_evidence`, which the ccc helper
  shares, so setup's ccc exclusions cover exactly these groups). A linked
  folder is always "foreign", and a linked version folder, or a linked
  package inside one, is never SKF output.
- `skf_skill`: a marked version, or a flat skill with a marked root.
- `flat_skf`: a root `SKILL.md` beside a marked root `metadata.json`; the
  only flat layout a workflow may migrate.
- `foreign_entries`: the entries SKF did not generate, sorted; directories
  end in `/`, a linked entry is listed by its bare name, and an entry inside
  a marked version folder `v` is listed as `v/<entry>` (SKF puts only the
  `{name}/` package and `.skf-` staging names there).

The existing `errors` list also names a linked folder (never checked for a
marker) and a `metadata.json` that cannot be read. The top-level `not_skf_output` lists the scanned names whose `skf_skill` is
false that still look like a skill (a root `SKILL.md` or a `{v}/{name}/`
folder). `versions`, `active_version` and `active_path` keep their structural
meaning for every entry, except that the package folders of a flat SKF skill
(`references/{name}/`, for example) are never read as versions.

The --match-target mode deterministically computes coexistence matches: it
normalizes scheme / trailing .git / trailing slash, derives the expected kebab
skill name, compares case-insensitively, and emits a top-level `matches[]`
array (each match carries the skill's `skf_skill`). This replaces the
equivalent normalize/derive/compare that a consuming prompt would otherwise
perform by hand (identical (target, inventory) always yields the same match
set).
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
    except (OSError, ValueError) as e:
        # A directory named like the file, a permission error, or bytes that
        # are not UTF-8: report it instead of crashing the whole scan.
        return None, f"Cannot read {path}: {e}"


# Keep identical to RESULT_JSON_RE in skf-merge-ccc-exclusions.py
# (test/test-skf-skill-inventory.py pins the copies).
RESULT_JSON_RE = re.compile(r"^([a-z0-9][a-z0-9-]*)-result(-latest|-\d[^/]*)?\.json$")
# Keep identical to SKF_GENERATORS in skf-merge-ccc-exclusions.py
# (test/test-skf-skill-inventory.py pins the copies).
SKF_GENERATORS = frozenset({"quick-skill", "create-skill", "create-stack-skill"})
# The flat package a migration moves into {v}/{name}/ (knowledge/version-paths.md).
FLAT_PACKAGE_ENTRIES = frozenset({"SKILL.md", "metadata.json", "context-snippet.md",
                                  "references", "scripts", "assets"})
# OS and VCS clutter that never decides who owns a skill folder.
NEUTRAL_GROUP_ENTRIES = frozenset({".DS_Store", ".gitkeep", ".gitignore", ".gitattributes",
                                   "Thumbs.db", "desktop.ini"})


# Keep identical to _has_skf_metadata in skf-merge-ccc-exclusions.py
# (test/test-skf-skill-inventory.py pins the copies).
def _has_skf_metadata(path: Path) -> bool:
    """True when a flat skill's metadata.json carries an SKF marker."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    generated_by = data.get("generated_by")
    if isinstance(generated_by, str) and generated_by in SKF_GENERATORS:
        return True
    tool_versions = data.get("tool_versions")
    if isinstance(tool_versions, dict) and "skf" in tool_versions:
        return True
    return (data.get("skill_type") in ("single", "individual", "stack")
            and ("forge_tier" in data or "confidence_tier" in data))


# Keep identical to _is_link_or_junction in skf-atomic-write.py
# (test/test-skf-skill-inventory.py pins the copies).
def _is_link_or_junction(p: Path) -> bool:
    """True for POSIX symlinks AND Windows junctions/symlinks.

    `Path.is_symlink()` is False for Windows junctions; os.readlink succeeds
    for both symlinks and junctions (since CPython 3.8 on Windows). A regular
    directory raises OSError on readlink, which is the signal we want to
    refuse replacement. On Windows, any other reparse point (a cloud-sync
    placeholder, a deduplicated file, an app execution alias) raises
    ValueError: it does not redirect to another path, so it is not a link.
    """
    if p.is_symlink():
        return True
    if not p.exists() and not p.is_symlink():
        return False
    try:
        os.readlink(p)
        return True
    except (OSError, ValueError):
        return False


def _is_active_pointer(name):
    """True for the `active` link name and the flip helper's `active.skf-*` names."""
    return name == "active" or name.startswith("active.skf-")


# Keep identical to _is_marked_version in skf-merge-ccc-exclusions.py
# (test/test-skf-skill-inventory.py pins the copies).
def _is_marked_version(version_dir: Path, name: str) -> bool:
    """True when `version_dir/name/metadata.json` carries an SKF marker.

    SKF never links a version folder or the package inside one: a linked
    one is not its output, whatever the metadata behind the link says.
    """
    package = version_dir / name
    return (not _is_link_or_junction(version_dir) and not _is_link_or_junction(package)
            and _has_skf_metadata(package / "metadata.json"))


# Keep identical to _has_skf_evidence in skf-merge-ccc-exclusions.py
# (test/test-skf-skill-inventory.py pins the copies).
def _has_skf_evidence(group_dir: Path, name: str) -> bool:
    """True when skill group `group_dir` holds evidence that SKF generated it.

    Evidence is the `_batch` name, `.skf-` in the name, a marked root
    `metadata.json`, or a marked version folder (`.skf-` staging folders
    aside). The versioned layout, an `active` link, a manifest key or a
    result file are not evidence on their own, and a linked group holds none.
    """
    if _is_link_or_junction(group_dir):
        return False
    if name == "_batch" or ".skf-" in name:
        return True
    if _has_skf_metadata(group_dir / "metadata.json"):
        return True
    try:
        children = list(group_dir.iterdir())
    except OSError:
        return False
    return any(".skf-" not in child.name and child.is_dir() and _is_marked_version(child, name)
               for child in children)


def _version_foreign_entries(version_dir, skill_name, errors):
    """The entries of a marked version folder SKF did not put there, as `v/<entry>`.

    SKF writes only the `{name}/` package and `.skf-` staging names into a
    version folder; neutral clutter is ignored. Directories end in `/`, a
    linked entry is listed by its bare name.
    """
    try:
        children = sorted(version_dir.iterdir(), key=lambda p: p.name)
    except OSError as e:
        errors.append(f"Cannot list {version_dir}: {e}")
        return [version_dir.name + "/"]
    found = []
    for child in children:
        name = child.name
        if name == skill_name or name in NEUTRAL_GROUP_ENTRIES or ".skf-" in name:
            continue
        if _is_link_or_junction(child) or not child.is_dir():
            found.append(f"{version_dir.name}/{name}")
        else:
            found.append(f"{version_dir.name}/{name}/")
    return found


def classify_ownership(skill_group_dir, skill_name):
    """Decide whether SKF generated the skill group `skill_group_dir`.

    Returns {ownership, skf_skill, flat_skf, foreign_entries, errors}.
    Whether the group holds SKF output at all is `_has_skf_evidence`, the
    rule the ccc helper shares. Only a marked metadata.json is proof there:
    the versioned layout or an `active` link alone does not count, because a
    module skill can sit in that layout (an earlier SKF migrated such skills
    without asking), and a manifest key does not count because the folder on
    disk may have changed since the export. A top-level entry of the group
    is SKF output when it is a version folder `v` whose `v/{name}/metadata.json`
    is marked (neither `v` nor `v/{name}` a link), an `active` or
    `active.skf-*` link (or a real `active/` folder holding a marked
    package), a name containing `.skf-`, a result file, or, beside a marked
    root metadata.json, one of the flat package entries. Neutral clutter is
    ignored; anything else is foreign. Inside a marked version folder,
    anything but the `{name}/` package, a `.skf-` name or neutral clutter is
    foreign too, listed as `v/<entry>`. Everything inside
    `_batch` or a `.skf-` folder is SKF output.
    """
    result = {
        "ownership": "foreign",
        "skf_skill": False,
        "flat_skf": False,
        "foreign_entries": [],
        "errors": [],
    }
    if _is_link_or_junction(skill_group_dir):
        result["errors"].append(
            f"skill folder is a link; SKF never moves or deletes through it: {skill_group_dir}"
        )
        return result
    try:
        children = sorted(skill_group_dir.iterdir(), key=lambda p: p.name)
    except OSError as e:
        result["errors"].append(f"Cannot list {skill_group_dir}: {e}")
        return result
    whole_group = skill_name == "_batch" or ".skf-" in skill_name
    root_marker = _has_skf_metadata(skill_group_dir / "metadata.json")
    marked_version = False
    foreign = []
    for child in children:
        name = child.name
        if name in NEUTRAL_GROUP_ENTRIES or whole_group:
            continue
        if _is_link_or_junction(child):
            if not _is_active_pointer(name):
                foreign.append(name)
            continue
        if ".skf-" in name or (child.is_file() and RESULT_JSON_RE.match(name)):
            continue
        if root_marker and name in FLAT_PACKAGE_ENTRIES:
            continue  # checked first: references/{name}/ is not a version
        is_dir = child.is_dir()
        if is_dir and (child / skill_name).is_dir():
            if _is_marked_version(child, skill_name):
                marked_version = True
                foreign.extend(_version_foreign_entries(child, skill_name, result["errors"]))
            else:
                foreign.append(name + "/")
            continue
        foreign.append(name + "/" if is_dir else name)
    result["flat_skf"] = root_marker and (skill_group_dir / "SKILL.md").is_file()
    result["skf_skill"] = marked_version or result["flat_skf"]
    result["foreign_entries"] = sorted(foreign)
    if _has_skf_evidence(skill_group_dir, skill_name):
        result["ownership"] = "mixed" if foreign else "skf"
    return result


def _looks_like_skill(skill_group_dir, skill_name):
    """True when a group holds a root SKILL.md or a {v}/{name}/ folder."""
    if (skill_group_dir / "SKILL.md").is_file():
        return True
    try:
        return any(child.is_dir() and (child / skill_name).is_dir()
                   for child in skill_group_dir.iterdir())
    except OSError:
        return False


def resolve_active_version(skill_group_dir):
    """Resolve the active version for a skill group directory.

    Returns (version_string, resolved_path) or (None, None).
    """
    active_link = skill_group_dir / "active"
    if active_link.is_symlink() or active_link.is_dir():
        try:
            target = active_link.resolve()
        except (OSError, RuntimeError):  # a link loop
            return None, None
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

    ownership = classify_ownership(skill_group_dir, skill_name)
    entry["errors"].extend(ownership.pop("errors"))
    entry.update(ownership)

    try:
        children = sorted(skill_group_dir.iterdir())
    except OSError:
        children = []  # classify_ownership already reported it

    # Check for version directories (contain a skill-name subdirectory). In a
    # flat SKF skill the package's own folders are never versions, even when
    # one holds a same-named subfolder such as references/{name}/.
    package_dirs = FLAT_PACKAGE_ENTRIES if entry["flat_skf"] else frozenset()
    for child in children:
        if child.name in package_dirs:
            continue
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
        if meta_err:
            if "Not found" not in meta_err:
                entry["errors"].append(meta_err)
        elif not isinstance(meta, dict):
            entry["errors"].append(f"metadata.json is not a JSON object: {metadata_path}")
        elif meta:
            stats = meta.get("stats")
            entry["metadata"] = {
                "version": meta.get("version"),
                "language": meta.get("language"),
                "source_authority": meta.get("source_authority"),
                "source_repo": meta.get("source_repo"),
                "generated_by": meta.get("generated_by"),
                "confidence_tier": meta.get("confidence_tier"),
                "exports_total": stats.get("exports_total") if isinstance(stats, dict) else None,
            }

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
    ``{name, active_version, source_repo, active_path, match_reason, skf_skill}``
    where ``match_reason`` is ``"url"``, ``"name"``, or ``"both"`` and
    ``skf_skill`` says whether SKF generated the matched skill (only those can
    be merged into through update-skill).
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
            "skf_skill": bool(entry.get("skf_skill")),
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
    exports = manifest.get("exports") if isinstance(manifest, dict) else None
    if isinstance(exports, dict):
        skill_names.update(exports.keys())

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
    not_skf_output = []
    for name in sorted(skill_names):
        skill_group_dir = skills_dir / name
        if skill_group_dir.is_dir():
            entry = scan_skill_group(skill_group_dir, name)
            result["skills"].append(entry)
            if not entry["skf_skill"] and _looks_like_skill(skill_group_dir, name):
                not_skf_output.append(name)
    result["not_skf_output"] = not_skf_output

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
            "Usage: uv run skf-skill-inventory.py <skills-output-folder> "
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
