# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Skill Inventory — Scan skills directory and produce structured inventory.

Scans the skills output folder, reads manifests and metadata, resolves active
versions via symlinks, and outputs a JSON inventory. Read by drop-skill and
rename-skill (roster, and the ownership of each skill folder and its forge
folder), create-skill, quick-skill and create-stack-skill (the write check
before a version is written), analyze-source (coexistence matches), and the
flat-layout fallback of update-skill, export-skill, audit-skill and test-skill
(the ownership gate before a flat skill is migrated).

CLI: uv run skf-skill-inventory.py <skills-output-folder>
     uv run skf-skill-inventory.py <skills-output-folder> --skill <name>
     uv run skf-skill-inventory.py <skills-output-folder> --manifest-only
     uv run skf-skill-inventory.py <skills-output-folder> --match-target <url-or-name>
     uv run skf-skill-inventory.py <skills-output-folder> --forge-data-folder <path>
     uv run skf-skill-inventory.py <skills-output-folder> --skill <name> --write-check
         [--write-version <version>] [--forge-data-folder <path>]

Exit 0 when `status` is "ok" (a write check exits 0 whatever its verdict);
exit 1 on an error (`DIR_NOT_FOUND`, `SKILL_NOT_FOUND` for `--skill`, or
`USAGE` for a write-check flag used wrongly or `--forge-data-folder` without
a value).

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
  `{name}/` package and `.skf-` staging names there). A folder that holds no
  file (only neutral clutter, `.skf-` names or folders like itself) is never
  foreign: an interrupted SKF run leaves one before it writes metadata.json.

The existing `errors` list also names a linked folder (never checked for a
marker), a folder in the skill folder that SKF cannot list or search (listed
as foreign) and a `metadata.json` that cannot be read. The top-level `not_skf_output` lists the scanned names whose `skf_skill` is
false that still look like a skill (a root `SKILL.md` or a `{v}/{name}/`
folder). `versions`, `active_version` and `active_path` keep their structural
meaning for every entry, except that the package folders of a flat SKF skill
(`references/{name}/`, for example) are never read as versions.

Forge folders. With `--forge-data-folder`, the top-level `forge_groups[]`
classifies `{forge_data_folder}/{name}` for every scanned name (`name`,
`path`, `ownership`, `foreign_entries`, `errors`; see `classify_forge_group`),
and `same_folder` says whether both settings name one folder. When they do,
`forge_groups` is empty and each skill folder is classified once, accepting
SKF's forge files too. The path given is echoed as `forge_data_folder`.

Write check. `--skill <name> --write-check [--write-version <v>]` returns
`write_check` (see `write_check`); the writers run it before creating any
directory.

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
# and skf-validate-rename-name.py (test/test-skf-skill-inventory.py pins the copies).
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


# Keep identical to FORGE_GROUP_DIRS in skf-merge-ccc-exclusions.py
# (test/test-skf-skill-inventory.py pins the copies).
FORGE_GROUP_DIRS = frozenset({"_campaign", "improvement-queue"})
# Keep identical to FORGE_VERSION_ANCHORS in skf-merge-ccc-exclusions.py
# (test/test-skf-skill-inventory.py pins the copies).
FORGE_VERSION_ANCHORS = frozenset({"provenance-map.json", "evidence-report.md", "extraction-rules.yaml"})
# The other names SKF writes into a forge version folder
# (knowledge/version-paths.md, forge_data_folder tree).
FORGE_VERSION_FILES = FORGE_VERSION_ANCHORS | frozenset({
    "evidence-report-fallback.md", "extraction-snapshot.json", ".manual-inventory.json",
    ".test-skill.lock"})
FORGE_REPORT_RE = re.compile(r"^(test-report|drift-report)(-.+)?\.md$")


# Keep identical to _has_forge_evidence in skf-merge-ccc-exclusions.py
# (test/test-skf-skill-inventory.py pins the copies).
def _has_forge_evidence(group_dir: Path, name: str) -> bool:
    """True when forge group `group_dir` holds evidence that SKF generated it.

    Evidence is `.skf-` in the name, SKF's own `_campaign` or
    `improvement-queue` folder, a skill brief (`skill-brief.yaml*` or
    `.brief-draft.json`) or a `*-result*.json` file directly in the group, or
    a provenance map, evidence report, extraction rules or `*-result*.json`
    file directly in a folder of the group (`.skf-` staging folders aside).
    A linked group, folder or file is never evidence.
    """
    if _is_link_or_junction(group_dir):
        return False
    if ".skf-" in name or name in FORGE_GROUP_DIRS:
        return True
    try:
        children = list(group_dir.iterdir())
    except OSError:
        return False
    for child in children:
        entry = child.name
        if _is_link_or_junction(child):
            continue
        if child.is_file():
            if (entry.startswith("skill-brief.yaml") or entry == ".brief-draft.json"
                    or RESULT_JSON_RE.match(entry)):
                return True
        elif child.is_dir() and ".skf-" not in entry:
            try:
                inner = list(child.iterdir())
            except OSError:
                continue
            if any((f.name in FORGE_VERSION_ANCHORS or RESULT_JSON_RE.match(f.name))
                   and not _is_link_or_junction(f) and f.is_file() for f in inner):
                return True
    return False


def _is_forge_version_name(entry):
    """True for a name SKF writes into a forge version folder."""
    return (entry in FORGE_VERSION_FILES or bool(FORGE_REPORT_RE.match(entry))
            or bool(RESULT_JSON_RE.match(entry)) or entry.endswith("-tmp"))


def _is_forge_root_name(entry, evidence):
    """True for a file SKF writes directly into a forge group.

    A brief or a result file always is. The legacy flat artifacts (a
    provenance map, evidence report, extraction rules or test or drift
    report at the group root) count only beside other evidence.
    """
    if (entry.startswith("skill-brief.yaml") or entry == ".brief-draft.json"
            or RESULT_JSON_RE.match(entry)):
        return True
    return evidence and (entry in FORGE_VERSION_ANCHORS or bool(FORGE_REPORT_RE.match(entry)))


def _holds_no_file(folder):
    """True when `folder` holds no file: only neutral clutter, `.skf-` names
    and folders that hold no file themselves (a link is content).

    That is all an interrupted SKF run leaves before it writes a package's
    metadata.json; deleting or writing into such a folder loses no file. A
    folder SKF cannot list or search holds content too.
    """
    try:
        children = list(folder.iterdir())
    except OSError:
        return False
    for child in children:
        name = child.name
        if name in NEUTRAL_GROUP_ENTRIES or ".skf-" in name:
            continue
        try:
            if _is_link_or_junction(child) or not child.is_dir() or not _holds_no_file(child):
                return False
        except OSError:  # a folder it cannot search: pathlib raises there before Python 3.14
            return False
    return True


def _forge_folder_entries(folder, group_evidence, package=None):
    """(verdict, entries SKF did not write as `v/<entry>`) for folder `v` of a forge group.

    A folder is marked when it directly holds a provenance map, evidence
    report, extraction rules or `*-result*.json` file. SKF's per-version
    names count inside a marked folder or in a group with evidence, except
    `package`: in a skills-side version folder (both settings name one
    folder) the skill's own package is SKF output only when marked, even
    when its name looks like a forge name such as `*-tmp`.
    Verdicts: "skf", "mixed" (marked, plus other entries), "empty" (not
    marked, nothing else) or "foreign".
    """
    v = folder.name
    try:
        children = sorted(folder.iterdir(), key=lambda p: p.name)
    except OSError:
        return "foreign", []
    marked = any((c.name in FORGE_VERSION_ANCHORS or RESULT_JSON_RE.match(c.name))
                 and not _is_link_or_junction(c) and c.is_file() for c in children)
    skf_named = marked or group_evidence
    inner = []
    for child in children:
        name = child.name
        if name in NEUTRAL_GROUP_ENTRIES or ".skf-" in name:
            continue
        if _is_link_or_junction(child):
            inner.append(f"{v}/{name}")
            continue
        if skf_named and name != package and _is_forge_version_name(name):
            continue
        if child.is_dir() and _holds_no_file(child):
            continue
        inner.append(f"{v}/{name}/" if child.is_dir() else f"{v}/{name}")
    if marked:
        return ("mixed" if inner else "skf"), inner
    return ("foreign" if inner else "empty"), inner


def classify_forge_group(group_dir, skill_name):
    """Decide whether SKF generated forge group `group_dir` ({forge_data_folder}/{name}).

    Returns {name, path, ownership, foreign_entries, errors}. `ownership`:
    "absent" (nothing at the path), "reserved" (SKF's own `_campaign` or
    `improvement-queue` folder, never a skill's), "skf" (SKF evidence and
    nothing else), "mixed" (evidence plus entries SKF did not write), "empty"
    (no evidence and nothing SKF did not write) or "foreign" (no evidence
    and entries SKF did not write; a link or a path that is not a folder,
    even with a reserved name, with the reason in `errors`). Whether the
    group holds SKF output at all is `_has_forge_evidence`, the rule the ccc
    helper shares. A folder in the group is listed as `v/` when SKF wrote
    nothing in it, and its entries as `v/<entry>` when it is marked; a
    linked entry is listed by its bare name.
    """
    result = {"name": skill_name, "path": str(group_dir), "ownership": "absent",
              "foreign_entries": [], "errors": []}
    if not os.path.lexists(group_dir):
        return result
    result["ownership"] = "foreign"
    if _is_link_or_junction(group_dir):
        result["errors"].append(
            f"forge folder is a link; SKF never moves or deletes through it: {group_dir}")
        return result
    if not group_dir.is_dir():
        result["errors"].append(f"forge folder is not a folder: {group_dir}")
        return result
    if skill_name in FORGE_GROUP_DIRS:
        result["ownership"] = "reserved"
        return result
    try:
        children = sorted(group_dir.iterdir(), key=lambda p: p.name)
    except OSError as e:
        result["errors"].append(f"Cannot list {group_dir}: {e}")
        return result
    evidence = _has_forge_evidence(group_dir, skill_name)
    foreign = []
    for child in children:
        name = child.name
        if name in NEUTRAL_GROUP_ENTRIES or ".skf-" in name:
            continue
        if _is_link_or_junction(child):
            foreign.append(name)
        elif child.is_dir():
            verdict, inner = _forge_folder_entries(child, evidence)
            if verdict == "mixed":
                foreign.extend(inner)
            elif verdict == "foreign":
                foreign.append(name + "/")
        elif not _is_forge_root_name(name, evidence):
            foreign.append(name)
    result["foreign_entries"] = sorted(foreign)
    if evidence:
        result["ownership"] = "mixed" if foreign else "skf"
    else:
        result["ownership"] = "foreign" if foreign else "empty"
    return result


def _same_folder(skills_dir, forge_dir):
    """True when the skills and forge settings name one folder."""
    if forge_dir is None:
        return False
    try:
        if skills_dir.exists() and forge_dir.exists():
            return os.path.samefile(skills_dir, forge_dir)
    except OSError:
        pass
    return (os.path.normcase(os.path.abspath(skills_dir))
            == os.path.normcase(os.path.abspath(forge_dir)))


def _version_foreign_entries(version_dir, skill_name, errors, also_forge=False):
    """The entries of a marked version folder SKF did not put there, as `v/<entry>`.

    SKF writes only the `{name}/` package and `.skf-` staging names into a
    version folder (and, with `also_forge`, its forge per-version files);
    neutral clutter is ignored. Directories end in `/`, a linked entry is
    listed by its bare name.
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
        if also_forge and not _is_link_or_junction(child) and _is_forge_version_name(name):
            continue
        if _is_link_or_junction(child) or not child.is_dir():
            found.append(f"{version_dir.name}/{name}")
        else:
            found.append(f"{version_dir.name}/{name}/")
    return found


def _read_error(folder, name):
    """The OSError that keeps SKF from listing `folder` or searching it for `name`, else None.

    os.listdir needs read permission on `folder` and os.lstat of `folder/name`
    search permission. Both raise on every Python version, where pathlib's
    is_dir and is_symlink return False inside a folder they cannot search
    from Python 3.14 on and raise before it.
    """
    try:
        os.listdir(folder)
        os.lstat(os.path.join(folder, name))
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as e:
        return e
    return None


def classify_ownership(skill_group_dir, skill_name, also_forge=False):
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
    `_batch` or a `.skf-` folder is SKF output. A folder that holds no file
    (only neutral clutter, `.skf-` names or folders like itself) is never
    foreign: an interrupted SKF run leaves one before it writes metadata.json.
    With `also_forge` (both settings name one folder), SKF's forge files
    count too, as ccc's kinds union does: a brief or result file at the
    root, forge per-version files in a version folder, and forge evidence;
    the skill's own `v/{name}/` package still counts only when marked.
    A folder SKF cannot list or search is foreign, and `errors` names it.
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
    try:
        forge_evidence = also_forge and _has_forge_evidence(skill_group_dir, skill_name)
    except OSError:  # a folder it cannot search; the loop below names it
        forge_evidence = False
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
        if child.is_dir():
            error = _read_error(child, skill_name)
            if error is not None:  # checked first: the checks below read inside it
                result["errors"].append(f"Cannot read {child}: {error}")
                foreign.append(name + "/")
                continue
        if ".skf-" in name or (child.is_file() and RESULT_JSON_RE.match(name)):
            continue
        if root_marker and name in FLAT_PACKAGE_ENTRIES:
            continue  # checked first: references/{name}/ is not a version
        is_dir = child.is_dir()
        if also_forge and not is_dir and _is_forge_root_name(name, forge_evidence or root_marker):
            continue
        if is_dir and _is_marked_version(child, skill_name):
            marked_version = True
            foreign.extend(_version_foreign_entries(child, skill_name, result["errors"], also_forge))
            continue
        if is_dir and also_forge:
            verdict, inner = _forge_folder_entries(child, forge_evidence, skill_name)
            if verdict != "foreign":
                foreign.extend(inner)
                continue
        if is_dir and _holds_no_file(child):
            continue  # an interrupted run's staging or empty package folders
        foreign.append(name + "/" if is_dir else name)
    result["flat_skf"] = root_marker and (skill_group_dir / "SKILL.md").is_file()
    result["skf_skill"] = marked_version or result["flat_skf"]
    result["foreign_entries"] = sorted(foreign)
    try:
        evidence = _has_skf_evidence(skill_group_dir, skill_name)
    except OSError:  # a folder it cannot search, named in `errors` above
        evidence = marked_version or root_marker
    if evidence or forge_evidence:
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


def scan_skill_group(skill_group_dir, skill_name, also_forge=False):
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

    ownership = classify_ownership(skill_group_dir, skill_name, also_forge)
    entry["errors"].extend(ownership.pop("errors"))
    entry.update(ownership)

    try:
        children = sorted(skill_group_dir.iterdir())
    except OSError:
        children = []  # classify_ownership already reported it

    # Check for version directories (contain a skill-name subdirectory). In a
    # flat SKF skill the package's own folders are never versions, even when
    # one holds a same-named subfolder such as references/{name}/. Inside a
    # folder SKF cannot search, the os.path checks return False on every
    # Python version (classify_ownership names that folder in `errors`).
    package_dirs = FLAT_PACKAGE_ENTRIES if entry["flat_skf"] else frozenset()
    for child in children:
        if child.name in package_dirs:
            continue
        if child.is_dir() and child.name != "active" and not child.name.startswith("."):
            # Check if this is a version dir (contains skill-name subdir or SKILL.md)
            skill_subdir = child / skill_name
            if os.path.isdir(skill_subdir):
                entry["versions"].append(child.name)
            elif os.path.exists(child / "SKILL.md"):
                # Flat version dir without skill-name nesting
                entry["versions"].append(child.name)

    # Resolve active version
    active_ver, active_path = resolve_active_version(skill_group_dir)
    if active_ver:
        entry["active_version"] = active_ver
        # The active path points to the version dir; skill files are in version/skill-name/
        skill_pkg = active_path / skill_name
        if os.path.isdir(skill_pkg):
            entry["active_path"] = str(skill_pkg)
        elif os.path.exists(active_path / "SKILL.md"):
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
    if active_dir and os.path.isdir(active_dir):
        entry["has_skill_md"] = os.path.exists(active_dir / "SKILL.md")
        entry["has_provenance_map"] = os.path.exists(active_dir / "provenance-map.json")
        entry["has_context_snippet"] = os.path.exists(active_dir / "context-snippet.md")

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


def _marked_active_version(skill_group_dir, skill_name):
    """The version folder `active` names when SKF generated it, else None.

    `active` counts only as a link to a folder directly in the group (not a
    `.skf-` name, not a link) whose package is marked, or as a real `active/`
    folder holding a marked package, reported as "active".
    """
    active = skill_group_dir / "active"
    if _is_link_or_junction(active):
        try:
            target = active.resolve(strict=True)
            group = skill_group_dir.resolve(strict=True)
        except (OSError, RuntimeError):
            return None
        version = skill_group_dir / target.name
        if (target.parent != group or ".skf-" in target.name or not target.is_dir()
                or not _is_marked_version(version, skill_name)):
            return None
        return target.name
    if active.is_dir() and _is_marked_version(active, skill_name):
        return "active"
    return None


def write_check(skills_folder, skill_name, version=None, forge_folder=None):
    """Decide whether a writer may add `{name}/{version}/{name}/` and flip `active`.

    Returns {name, version, verdict, reason, folder, detail, foreign_entries,
    marked_active_version}. `verdict` is "ok", "not-skf-output" or
    "flat-layout" (the halt reason a refusal uses); `reason` names the rule
    that decided (None for "ok"). Nothing at the skill folder is a new skill.
    A folder that holds only what an interrupted SKF run leaves is written
    into; a mixed folder is written into when the target version is new or
    SKF's own. `forge_folder` only decides whether both settings name one
    folder, so SKF's forge files there count as SKF output.
    """
    skills_dir = Path(skills_folder)
    forge_dir = Path(forge_folder) if forge_folder else None
    group = skills_dir / skill_name
    out = {"name": skill_name, "version": version, "verdict": "ok", "reason": None,
           "folder": str(group), "detail": None, "foreign_entries": [],
           "marked_active_version": None}

    def refuse(verdict, reason, detail, folder=None):
        out.update(verdict=verdict, reason=reason, detail=detail)
        if folder is not None:
            out["folder"] = str(folder)
        return out

    if skill_name == "_batch" or ".skf-" in skill_name or skill_name in FORGE_GROUP_DIRS:
        reserved_at = (forge_dir / skill_name) if (forge_dir and skill_name in FORGE_GROUP_DIRS) else group
        return refuse("not-skf-output", "reserved-name",
                      "is a name SKF keeps for its own files, never a skill's", reserved_at)
    if not os.path.lexists(group):
        return out
    if _is_link_or_junction(group):
        return refuse("not-skf-output", "link", "is a link; SKF never writes through a link")
    if not group.is_dir():
        return refuse("not-skf-output", "not-a-folder", "is not a folder")
    own = classify_ownership(group, skill_name, _same_folder(skills_dir, forge_dir))
    out["foreign_entries"] = own["foreign_entries"]
    if own["errors"]:
        return refuse("not-skf-output", "unreadable", "; ".join(own["errors"]))
    if own["flat_skf"] and not _marked_version_names(group, skill_name):
        return refuse("flat-layout", "flat-layout", "still uses the flat layout")
    if not own["skf_skill"] and own["foreign_entries"]:
        return refuse("not-skf-output", "not-skf-output",
                      "has no SKF marker in any `metadata.json` and holds entries SKF did not "
                      "generate: " + ", ".join(own["foreign_entries"]))
    if version is not None:
        listed = [e for e in own["foreign_entries"]
                  if e == version or e == version + "/" or e.startswith(version + "/")]
        if listed:
            return refuse("not-skf-output", "version",
                          "is not a version SKF generated, or holds entries SKF did not "
                          "generate: " + ", ".join(listed), group / version)
    out["marked_active_version"] = _marked_active_version(group, skill_name)
    return out


def _marked_version_names(skill_group_dir, skill_name):
    """The names of the marked version folders of a group (`.skf-` names aside)."""
    try:
        children = list(skill_group_dir.iterdir())
    except OSError:
        return []
    return sorted(c.name for c in children
                  if ".skf-" not in c.name and c.is_dir() and _is_marked_version(c, skill_name))


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


def scan_inventory(skills_folder, skill_filter=None, manifest_only=False, match_target=None,
                   forge_data_folder=None):
    """Scan the skills output folder and produce an inventory."""
    skills_dir = Path(skills_folder)
    forge_dir = Path(forge_data_folder) if forge_data_folder else None
    same_folder = _same_folder(skills_dir, forge_dir)

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
            entry = scan_skill_group(skill_group_dir, name, same_folder)
            result["skills"].append(entry)
            if not entry["skf_skill"] and _looks_like_skill(skill_group_dir, name):
                not_skf_output.append(name)
    result["not_skf_output"] = not_skf_output
    # Forge folders (opt-in via --forge-data-folder; additive top-level keys).
    if forge_dir is not None:
        result["forge_data_folder"] = str(forge_dir)
        result["same_folder"] = same_folder
        result["forge_groups"] = [] if same_folder else [
            classify_forge_group(forge_dir / name, name) for name in sorted(skill_names)]

    # Compute summary
    result["summary"]["total_skills"] = len(result["skills"])
    result["summary"]["total_versions"] = sum(len(s["versions"]) for s in result["skills"])
    result["summary"]["with_metadata"] = sum(1 for s in result["skills"] if s["metadata"])
    result["summary"]["with_provenance"] = sum(1 for s in result["skills"] if s["has_provenance_map"])

    # Coexistence matching (opt-in via --match-target; additive top-level key).
    if match_target is not None:
        result["matches"] = compute_matches(result["skills"], match_target)

    return result


USAGE = ("Usage: uv run skf-skill-inventory.py <skills-output-folder> "
         "[--skill <name>] [--manifest-only] [--match-target <url-or-name>] "
         "[--forge-data-folder <path>]\n"
         "       uv run skf-skill-inventory.py <skills-output-folder> --skill <name> "
         "--write-check [--write-version <version>] [--forge-data-folder <path>]")


def _flag_value(argv, flag, required=False):
    """The value after `flag`, or None when the flag is absent.

    A flag without a value reads as absent, as it always has, unless
    `required`: `--forge-data-folder`, `--write-version` and, in write-check
    mode, `--skill` raise ValueError instead (a missing value, or the next
    flag in its place), so a caller never gets a verdict it did not ask for.
    """
    if flag not in argv:
        return None
    idx = argv.index(flag)
    if idx + 1 < len(argv) and not (required and argv[idx + 1].startswith("--")):
        return argv[idx + 1]
    if required:
        raise ValueError(f"{flag} needs a value")
    return None


def _safe_segment(value):
    """True for a single path segment: not empty, `.` or `..`, and no separator."""
    return bool(value) and value not in (".", "..") and "/" not in value and "\\" not in value


def main(argv):
    if len(argv) < 1:
        print(USAGE, file=sys.stderr)
        return 1
    folder = argv[0]
    write = "--write-check" in argv
    try:
        skill = _flag_value(argv, "--skill", required=write)
        match_target = _flag_value(argv, "--match-target")
        forge_data_folder = _flag_value(argv, "--forge-data-folder", required=True)
        write_version = _flag_value(argv, "--write-version", required=True)
        if write and folder.startswith("--"):
            raise ValueError("--write-check needs <skills-output-folder> first")
        if write and not skill:
            raise ValueError("--write-check needs --skill <name>")
        if write_version is not None and not write:
            raise ValueError("--write-version needs --write-check")
        if write and not _safe_segment(skill):
            raise ValueError(f"--skill must be one folder name: {skill!r}")
        if write_version is not None and not _safe_segment(write_version):
            raise ValueError(f"--write-version must be one folder name: {write_version!r}")
    except ValueError as e:
        print(json.dumps({"status": "error", "error": str(e), "code": "USAGE"}, indent=2))
        print(USAGE, file=sys.stderr)
        return 1
    if write:
        skills_dir = Path(folder)
        if os.path.lexists(skills_dir) and not skills_dir.is_dir():
            result = {"status": "error", "error": f"Skills directory not found: {skills_dir}",
                      "code": "DIR_NOT_FOUND"}
        else:
            forge_dir = Path(forge_data_folder) if forge_data_folder else None
            result = {"status": "ok", "skills_folder": str(skills_dir),
                      "forge_data_folder": forge_data_folder,
                      "same_folder": _same_folder(skills_dir, forge_dir),
                      "write_check": write_check(skills_dir, skill, write_version, forge_data_folder)}
    else:
        result = scan_inventory(
            folder,
            skill_filter=skill,
            manifest_only="--manifest-only" in argv,
            match_target=match_target,
            forge_data_folder=forge_data_folder,
        )
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
