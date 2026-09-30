# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Skill Inventory — Scan skills directory and produce structured inventory.

Scans the skills output folder, reads manifests and metadata, resolves active
versions via symlinks, and outputs a JSON inventory. Read by drop-skill and
rename-skill (roster, the ownership of each skill folder and its forge
folder, the purge and rename verdicts, and the guarded delete),
create-skill, quick-skill and create-stack-skill (the write check before a
version is written), analyze-source (coexistence matches), the flat-layout
fallback of update-skill, export-skill, audit-skill and test-skill (the
ownership gate before a flat skill is migrated), and test-skill's report
(the discovery catalog).

CLI: uv run skf-skill-inventory.py <skills-output-folder>
     uv run skf-skill-inventory.py <skills-output-folder> --skill <name>
     uv run skf-skill-inventory.py <skills-output-folder> --manifest-only
     uv run skf-skill-inventory.py <skills-output-folder> --match-target <url-or-name>
     uv run skf-skill-inventory.py <skills-output-folder> --forge-data-folder <path>
     uv run skf-skill-inventory.py <skills-output-folder> --skill <name> --write-check
         [--write-version <version>] [--forge-data-folder <path>]
     uv run skf-skill-inventory.py <skills-output-folder> --skill <name> --purge-check
         [--purge-version <version>] --forge-data-folder <path>
     uv run skf-skill-inventory.py <skills-output-folder> --skill <name> --rename-check
         --forge-data-folder <path>
     uv run skf-skill-inventory.py guarded-delete --root <folder> [--root <folder>] [<path>...]
     uv run skf-skill-inventory.py resolve <skills-output-folder> --skill <name>
         --forge-data-folder <path> [--version <version>]
     uv run skf-skill-inventory.py version normalize <version>
     uv run skf-skill-inventory.py version order <a> <b>
     uv run skf-skill-inventory.py version next-patch <version>
     uv run skf-skill-inventory.py version bump --prior <version>
         --prior-libraries <a,b> --libraries <a,c>
     uv run skf-skill-inventory.py version primary <candidates.json|->

Exit 0 when `status` is "ok" (a write, purge or rename check exits 0
whatever its verdict, and a guarded delete whatever its `purge_status`);
exit 1 on an error (`DIR_NOT_FOUND`, `SKILL_NOT_FOUND` for `--skill` or
`resolve`, `USAGE` for a flag used wrongly, two check flags in one call,
`--forge-data-folder` without a value or missing from a purge or rename
check, and for `version`: `NOT_A_VERSION`, `NOT_INCREASING` or
`BAD_INPUT`).

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
as foreign) and a `metadata.json` that cannot be read. The top-level `not_skf_output` lists the scanned names (never `_batch` or a `.skf-` name) whose `skf_skill` is
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

Purge and rename checks. `--skill <name> --purge-check [--purge-version
<v>]` returns `purge_check` (see `purge_check`): whether drop-skill may
purge the whole skill or one version, the rule that refused it, and the
folders the purge deletes and leaves in place. `--skill <name>
--rename-check` returns `rename_check` (see `rename_check`): whether
rename-skill may move the skill, and whether its forge folder moves with
it. Both need `--forge-data-folder` and apply the same version rule as the
write check (`0.1.0-rc/` is never version `0.1.0`).

Guarded delete. `guarded-delete --root <folder>... [<path>...]` deletes
each path that is a plain folder inside a root, reached through no link,
and reports each outcome and a `purge_status` (see `guarded_delete`); with
no path it deletes nothing and reports "success". drop-skill's purge and
rename-skill's delete of the old folders go through it, with the skills
and forge folders as roots.

Resolve. `resolve` returns `resolve` (see `resolve_skill`) for one skill:
the manifest's `active_version`, the `active` link's target, the version a
reading workflow uses and why (the Manifest-lag guard of
knowledge/version-paths.md, with each version's provenance `generated_at`),
`forge_version`, the metadata.json, provenance-map.json and
evidence-report.md paths (versioned first, flat as the fallback), and every
version newest first with its manifest status and the counts drop-skill and
rename-skill read. `--version` names the version instead (an operator's
choice). It reads, never writes, and does not decide ownership.

Version. `version` turns version strings into one answer: `normalize`
reduces a version or range to one folder name (`^18.2.0` gives `18.2.0`,
build metadata stripped), `order` compares two (`1.10.0` above `1.9.0`),
`next-patch` gives the next patch version, `bump` the compose-mode stack
version after a prior one (major when a library was removed, else minor,
refused when not above it), and `primary` the code-mode primary library of
a stack and the version it gives, ties broken by a fixed rule.

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
import shutil
import stat
import sys
from datetime import datetime, timedelta, timezone
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
# and skf-enumerate-stack-skills.py
# (test/test-skf-skill-inventory.py pins the copies).
SKF_GENERATORS = frozenset({"quick-skill", "create-skill", "create-stack-skill"})
# The flat package a migration moves into {v}/{name}/ (knowledge/version-paths.md).
FLAT_PACKAGE_ENTRIES = frozenset({"SKILL.md", "metadata.json", "context-snippet.md",
                                  "references", "scripts", "assets"})
# OS and VCS clutter that never decides who owns a skill folder.
NEUTRAL_GROUP_ENTRIES = frozenset({".DS_Store", ".gitkeep", ".gitignore", ".gitattributes",
                                   "Thumbs.db", "desktop.ini"})


# Keep identical to _has_skf_metadata in skf-merge-ccc-exclusions.py
# and skf-enumerate-stack-skills.py
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


# Keep identical to _is_link_or_junction in skf-atomic-write.py, skf-enumerate-stack-skills.py,
# skf-validate-rename-name.py, skf-source-tree.py and skf-tessl-review.py
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
# and skf-enumerate-stack-skills.py
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
# (knowledge/version-paths.md, forge_data_folder tree), and
# .manual-inventory.json, which update-skill kept there before it kept
# that inventory beside its lock.
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


# Keep identical to _looks_like_skill in skf-enumerate-stack-skills.py
# (test/test-skf-skill-inventory.py pins the copies).
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
        listed = _version_entries(own["foreign_entries"], version)
        if listed:
            return refuse("not-skf-output", "version",
                          "is not a version SKF generated, or holds entries SKF did not "
                          "generate: " + ", ".join(listed), group / version)
    out["marked_active_version"] = _marked_active_version(group, skill_name)
    return out


def _version_entries(entries, version):
    """The `foreign_entries` that are version folder `version` or inside it.

    A linked version folder is listed by its bare name (`v`), one SKF did not
    generate as `v/` and an entry SKF did not put in a marked one as
    `v/<entry>`. A prefix of another version is not that version: `0.1.0-rc/`
    is never version `0.1.0`.
    """
    return [e for e in entries if e == version or e == version + "/" or e.startswith(version + "/")]


def _is_reserved_group(skill_name):
    """True for SKF's own `_batch` folder and its `.skf-` staging names, never a skill."""
    return skill_name == "_batch" or ".skf-" in skill_name


def purge_check(skills_folder, skill_name, forge_folder, version=None):
    """Decide whether drop-skill may purge `skill_name`, whole or one version.

    Returns {name, version, scope, verdict, reason, folder, detail,
    offending_entries, ownership, foreign_entries, errors, same_folder,
    forge_ownership, forge_foreign_entries, forge_errors,
    affected_directories, forge_left_in_place}. `verdict` is "ok" or
    "not-skf-output". A purge deletes only what SKF generated, so `reason`
    names the rule that refused it:

    - "reserved-name": `_batch` or a `.skf-` name, SKF's own folders.
    - "skill-foreign": the skill folder is not SKF output (no marker, a link,
      not a folder, or a folder SKF cannot list; `detail` says which).
    - "skill-mixed-whole": a whole-skill purge of a skill folder that also
      holds entries SKF did not generate.
    - "skill-version-not-skf": version folder `version` is a link or not SKF
      output (`v` or `v/` in `foreign_entries`).
    - "skill-version-mixed": version folder `version` holds entries SKF did
      not put there (`v/<entry>`).
    - "forge-mixed-whole" and "forge-version-mixed": the same two rules for
      the skill's forge folder, when the two settings name different folders.

    A forge folder SKF did not generate (`foreign`, a link or a path that is
    not a folder), SKF's own `reserved` folder, and a forge version folder
    listed as `v` or `v/` do not refuse the purge: the purge leaves them in
    place and `forge_left_in_place` names the path. `affected_directories`
    lists the folders a purge at this scope deletes, whatever the verdict
    (a deprecate keeps them): the skill folder, or its version folder, then
    the forge one, each only when something is there, with no trailing
    separator, and the forge one never when both settings name one folder.
    """
    skills_dir, forge_dir = Path(skills_folder), Path(forge_folder)
    group, forge_group = skills_dir / skill_name, forge_dir / skill_name
    same = _same_folder(skills_dir, forge_dir)
    scope = "skill" if version is None else "version"
    out = {"name": skill_name, "version": version, "scope": scope, "verdict": "ok", "reason": None,
           "folder": str(group), "detail": None, "offending_entries": [], "ownership": "absent",
           "foreign_entries": [], "errors": [], "same_folder": same, "forge_ownership": None,
           "forge_foreign_entries": [], "forge_errors": [], "affected_directories": [],
           "forge_left_in_place": None}

    def refuse(reason, detail, folder, entries=()):
        if out["verdict"] == "ok":
            out.update(verdict="not-skf-output", reason=reason, detail=detail, folder=str(folder),
                       offending_entries=list(entries))

    if _is_reserved_group(skill_name):
        refuse("reserved-name", "is a name SKF keeps for its own files, never a skill's", group)
        return out
    target = group if version is None else group / version
    if os.path.lexists(group):
        own = classify_ownership(group, skill_name, same)
        out.update(ownership=own["ownership"], foreign_entries=own["foreign_entries"], errors=own["errors"])
        if own["ownership"] == "foreign":
            refuse("skill-foreign", "; ".join(own["errors"]) or "has no SKF marker in its `metadata.json`",
                   group)
        elif own["ownership"] == "mixed" and version is None:
            refuse("skill-mixed-whole", "also holds entries SKF did not generate: "
                   + ", ".join(own["foreign_entries"]), group, own["foreign_entries"])
        elif own["ownership"] == "mixed":
            listed = _version_entries(own["foreign_entries"], version)
            inside = [e for e in listed if e.startswith(version + "/") and e != version + "/"]
            if inside:
                refuse("skill-version-mixed", "holds entries SKF did not generate: " + ", ".join(inside),
                       target, inside)
            elif listed:
                refuse("skill-version-not-skf", "is a link or has no SKF marker in its `metadata.json`",
                       target, listed)
    if os.path.lexists(target):
        out["affected_directories"].append(str(target))
    if same:
        return out

    forge = classify_forge_group(forge_group, skill_name)
    out.update(forge_ownership=forge["ownership"], forge_foreign_entries=forge["foreign_entries"],
               forge_errors=forge["errors"])
    forge_target = forge_group if version is None else forge_group / version
    leave = forge["ownership"] in ("foreign", "reserved")
    if forge["ownership"] == "mixed" and version is None:
        refuse("forge-mixed-whole", "also holds entries SKF did not generate: "
               + ", ".join(forge["foreign_entries"]), forge_group, forge["foreign_entries"])
    elif forge["ownership"] == "mixed":
        listed = _version_entries(forge["foreign_entries"], version)
        inside = [e for e in listed if e.startswith(version + "/") and e != version + "/"]
        if inside:
            refuse("forge-version-mixed", "holds entries SKF did not generate: " + ", ".join(inside),
                   forge_target, inside)
        leave = bool(listed) and not inside
    if not os.path.lexists(forge_target):
        return out
    if leave:
        out["forge_left_in_place"] = str(forge_target)
    else:
        out["affected_directories"].append(str(forge_target))
    return out


def rename_check(skills_folder, skill_name, forge_folder):
    """Decide whether rename-skill may move `skill_name` to a new name.

    Rename copies `{skills_output_folder}/{name}/` and its forge folder, then
    deletes the old ones, so it moves only a skill SKF generated in the
    versioned layout. Returns {name, verdict, reason, folder, detail,
    offending_entries, ownership, skf_skill, flat_skf, foreign_entries,
    errors, same_folder, forge_ownership, forge_foreign_entries,
    forge_errors, forge_move, forge_left_in_place}. `verdict` is "ok",
    "not-skf-output" or "flat-layout" (the halt reason a refusal uses);
    `reason` names the first rule that refused it:

    - "reserved-name": `_batch` or a `.skf-` name.
    - "absent": nothing at the skill folder.
    - "foreign": the skill folder is not SKF output (no marker, a link, not
      a folder, or one SKF cannot list; `detail` says which), or holds SKF's
      files but no skill SKF generated.
    - "mixed": it also holds entries SKF did not generate.
    - "flat-layout": it still uses the flat layout.
    - "forge-link", "forge-not-a-folder", "forge-unreadable": the forge
      folder is a link, is not a folder, or cannot be listed.
    - "forge-mixed": the forge folder also holds entries SKF did not
      generate.

    When both settings name one folder the skill folder is the forge folder,
    so no forge rule applies and nothing else moves. Otherwise `forge_move`
    is true when the forge folder is SKF output or holds no file of its own
    ("skf" or "empty"), and `forge_left_in_place` names a forge folder SKF
    did not generate, or SKF's own reserved one, which keeps its name.
    """
    skills_dir, forge_dir = Path(skills_folder), Path(forge_folder)
    group, forge_group = skills_dir / skill_name, forge_dir / skill_name
    same = _same_folder(skills_dir, forge_dir)
    out = {"name": skill_name, "verdict": "ok", "reason": None, "folder": str(group), "detail": None,
           "offending_entries": [], "ownership": "absent", "skf_skill": False, "flat_skf": False,
           "foreign_entries": [], "errors": [], "same_folder": same, "forge_ownership": None,
           "forge_foreign_entries": [], "forge_errors": [], "forge_move": False,
           "forge_left_in_place": None}

    def refuse(verdict, reason, detail, folder=group, entries=()):
        out.update(verdict=verdict, reason=reason, detail=detail, folder=str(folder),
                   offending_entries=list(entries))
        return out

    if _is_reserved_group(skill_name):
        return refuse("not-skf-output", "reserved-name", "is a name SKF keeps for its own files, never a skill's")
    if not os.path.lexists(group):
        return refuse("not-skf-output", "absent", "has no folder in the skills folder")
    own = classify_ownership(group, skill_name, same)
    out.update(ownership=own["ownership"], skf_skill=own["skf_skill"], flat_skf=own["flat_skf"],
               foreign_entries=own["foreign_entries"], errors=own["errors"])
    if own["ownership"] == "foreign":
        return refuse("not-skf-output", "foreign",
                      "; ".join(own["errors"]) or "has no SKF marker in its `metadata.json`")
    if own["ownership"] == "mixed":
        return refuse("not-skf-output", "mixed", "also holds entries SKF did not generate: "
                      + ", ".join(own["foreign_entries"]), group, own["foreign_entries"])
    if not own["skf_skill"]:  # SKF's files, such as a brief, but no skill it generated
        return refuse("not-skf-output", "foreign", "has no SKF marker in its `metadata.json`")
    if own["flat_skf"]:
        return refuse("flat-layout", "flat-layout", "still uses the flat layout")
    if same:
        return out
    forge = classify_forge_group(forge_group, skill_name)
    out.update(forge_ownership=forge["ownership"], forge_foreign_entries=forge["foreign_entries"],
               forge_errors=forge["errors"])
    if forge["errors"] and forge["ownership"] != "reserved":
        if _is_link_or_junction(forge_group):
            reason = "forge-link"
        elif not forge_group.is_dir():
            reason = "forge-not-a-folder"
        else:
            reason = "forge-unreadable"
        return refuse("not-skf-output", reason, "; ".join(forge["errors"]), forge_group)
    if forge["ownership"] == "mixed":
        return refuse("not-skf-output", "forge-mixed", "also holds entries SKF did not generate: "
                      + ", ".join(forge["foreign_entries"]), forge_group, forge["foreign_entries"])
    out["forge_move"] = forge["ownership"] in ("skf", "empty")
    if forge["ownership"] in ("foreign", "reserved"):
        out["forge_left_in_place"] = str(forge_group)
    return out


# --------------------------------------------------------------------------
# Guarded delete: a purge deletes only plain folders inside SKF's folders
# --------------------------------------------------------------------------

LINK_REFUSAL = "a link; SKF never deletes through a link"


def _strip_trailing_separators(path):
    """`path` without the trailing separators that make a delete follow a link."""
    separators = "/" + os.sep + (os.altsep or "")
    return path.rstrip(separators) or path


def _parts_below(root, path):
    """The folder names from `root` down to `path`, or None when `path` is not below `root`.

    Both are made absolute without resolving links (a link at or above a
    root is the user's configuration) and compared case-insensitively where
    the platform is.
    """
    root_abs, path_abs = os.path.abspath(root), os.path.abspath(path)
    try:
        inside = os.path.commonpath([os.path.normcase(root_abs), os.path.normcase(path_abs)])
    except ValueError:  # another drive on Windows
        return None
    if inside != os.path.normcase(root_abs) or os.path.normcase(path_abs) == inside:
        return None
    return Path(os.path.relpath(path_abs, root_abs)).parts


def _tree_bytes(path):
    """The bytes of the files under `path`, a link counted as itself and never followed."""
    total = 0
    for folder, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(folder, name)).st_size
            except OSError:
                pass
    return total


def _remove_tree(path):
    """shutil.rmtree, clearing a read-only bit (Windows) and retrying once."""

    def retry(func, target, _error):
        os.chmod(target, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
        func(target)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:
        shutil.rmtree(path, onerror=retry)


def _delete_one(roots, path):
    """("deleted", bytes), ("absent", None) or ("failed", reason) for one path of guarded_delete."""
    if not Path(path).parts:  # "" or "." would name the working folder
        return "failed", "names no folder"
    if ".." in Path(path).parts:
        return "failed", "has a `..` part; SKF deletes only a plain path"
    below = [(root, parts) for root in roots if (parts := _parts_below(root, path)) is not None]
    if not below:
        return "failed", "is not inside " + " or ".join(roots) + "; SKF deletes only inside its folders"
    root, parts = max(below, key=lambda b: len(os.path.abspath(b[0])))  # the closest root
    for i in range(1, len(parts) + 1):
        step = Path(root, *parts[:i])
        if _is_link_or_junction(step):
            return "failed", LINK_REFUSAL if i == len(parts) else f"{step} is {LINK_REFUSAL}"
    if not os.path.lexists(path):
        return "absent", None
    if not os.path.isdir(path):
        return "failed", "is not a folder; SKF deletes only folders here"
    size = _tree_bytes(path)
    try:
        _remove_tree(path)
    except OSError as e:
        return "failed", f"cannot delete it: {e}"
    if os.path.lexists(path):
        return "failed", "is still there after the delete"
    return "deleted", size


def guarded_delete(roots, paths):
    """Delete each folder of `paths` that lies inside one of `roots`, as drop-skill's purge.

    rename-skill deletes its old folders the same way. Each path loses its
    trailing separators first. It is refused, and listed in
    `delete_failures` with the reason, when it names no folder or has a
    `..` part, is not below a root (a root itself included), is a link or
    junction or lies below one between the closest root and it (SKF never
    deletes through a link: the delete would reach the files the link points
    to), or is not a folder. A path with nothing at it goes to
    `already_absent`. Otherwise its size is measured, the folder is deleted
    and checked gone: then it goes to `files_deleted`, else to
    `delete_failures`. Returns {roots, files_deleted, already_absent,
    delete_failures, attempted, bytes_freed, purge_status}: `attempted`
    counts the paths deleted or refused, and `purge_status` is "failed" when
    it is above 0 and nothing was deleted, "partial" when some were, else
    "success" (no path at all included: a purge whose folders are already
    gone has nothing to delete).
    """
    deleted, absent, failures, freed = [], [], [], 0
    for raw in paths:
        path = _strip_trailing_separators(raw)
        outcome, detail = _delete_one(roots, path)
        if outcome == "deleted":
            deleted.append(path)
            freed += detail
        elif outcome == "absent":
            absent.append(path)
        else:
            failures.append({"path": path, "error": detail})
    attempted = len(deleted) + len(failures)
    if attempted and not deleted:
        status = "failed"
    elif failures:
        status = "partial"
    else:
        status = "success"
    return {"roots": list(roots), "files_deleted": deleted, "already_absent": absent,
            "delete_failures": failures, "attempted": attempted, "bytes_freed": freed,
            "purge_status": status}


def _marked_version_names(skill_group_dir, skill_name):
    """The names of the marked version folders of a group (`.skf-` names aside)."""
    try:
        children = list(skill_group_dir.iterdir())
    except OSError:
        return []
    return sorted(c.name for c in children
                  if ".skf-" not in c.name and c.is_dir() and _is_marked_version(c, skill_name))


# --------------------------------------------------------------------------
# Versions: normalize, order, next patch, compose-mode bump, primary library
# --------------------------------------------------------------------------

# What may follow the dotted numbers of a version: a pre-release tag such as
# `-rc.1`, `rc1` or `.dev0`, identifiers split by `.` or `-`.
PRE_RELEASE_RE = re.compile(r"[-._]?[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*")
BUILD_RE = re.compile(r"[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*")
# A comparator of a range: npm, Python, Ruby and Cargo operators, then a version.
COMPARATOR_RE = re.compile(r"(===|==|>=|<=|~=|~>|!=|\^|~|>|<|=)?\s*([^\s,]+)")
COMPARATOR_SEPARATOR_RE = re.compile(r"\s*,?\s*")
UPPER_BOUND_OPERATORS = frozenset({"<", "<=", "!="})
# Trailing wildcard components (`1.2.x`, `1.*`), dropped before a bound is read.
WILDCARD_TAIL_RE = re.compile(r"(?:\.[xX*])+$")
WILDCARDS = frozenset({"x", "X", "*"})


def _parse_plain_version(text):
    """(release, pre, build) for a plain version string, else None.

    A leading `v` is dropped and the build metadata after `+` split off.
    `release` holds the dotted numbers, padded to three (`2.0` is `2.0.0`);
    `pre` is whatever follows them (`-rc.1`, `rc1`, `.dev0`) as written, or "".
    A trailing wildcard component (`1.2.x`) is not a plain version.
    """
    s = str(text).strip()
    s, plus, build = s.partition("+")
    if plus and not BUILD_RE.fullmatch(build):
        return None
    m = re.match(r"[vV]?(\d+(?:\.\d+)*)", s)
    if not m:
        return None
    pre = s[m.end():]
    if pre and (not PRE_RELEASE_RE.fullmatch(pre) or re.match(r"\.[xX](?:\.|$)", pre)):
        return None
    release = [str(int(part)) for part in m.group(1).split(".")]
    release += ["0"] * (3 - len(release))
    return release, pre, (build or None)


def _version_text(parsed):
    release, pre, _ = parsed
    return ".".join(release) + pre


def _order_key(parsed):
    """Sort key: numbers compared as numbers (1.10.0 above 1.9.0), a release
    above its pre-releases, pre-release identifiers compared with their digit
    runs as numbers (rc10 above rc2) and ranked below letters, as in semver."""
    release, pre, _ = parsed
    nums = [int(part) for part in release]
    while nums and nums[-1] == 0:
        nums.pop()
    if not pre:
        return (tuple(nums), (1,))
    ids = tuple(
        tuple((0, int(run)) if run.isdigit() else (1, run) for run in re.findall(r"\d+|\D+", ident))
        for ident in pre.lstrip("-._").split("."))
    return (tuple(nums), (0,) + ids)


def _lower_bound(spec):
    """The lower bound of one comparator set (`>=1.2, <2`, `^18.2.0`, `1.0 - 2.0`),
    as a parsed version, or the reason there is none (a string)."""
    spec = spec.strip()
    hyphen = re.fullmatch(r"(\S+)\s+-\s+(\S+)", spec)
    if hyphen:
        comparators = [(">=", hyphen.group(1)), ("<=", hyphen.group(2))]
    else:
        comparators, pos = [], 0
        while pos < len(spec):
            m = COMPARATOR_RE.match(spec, pos)
            if not m:
                return f"not a version or range: {spec!r}"
            comparators.append((m.group(1) or "", m.group(2)))
            pos = COMPARATOR_SEPARATOR_RE.match(spec, m.end()).end()
    if not comparators:
        return "empty version"
    lows = []
    for op, token in comparators:
        if token in WILDCARDS:
            continue  # admits any version: no bound
        parsed = _parse_plain_version(WILDCARD_TAIL_RE.sub("", token))
        if parsed is None:
            return f"not a version: {token!r}"
        if op not in UPPER_BOUND_OPERATORS:
            lows.append(parsed)
    if not lows:
        return f"names no lower bound: {spec!r}"
    return max(lows, key=_order_key)


def _reduce_version(text):
    """((release, pre, build), rule) for a version or range, or a reason string.

    `rule` is "version" for a plain version and "range" for a specifier
    reduced to its lower bound: the version it names after `^`, `~`, `~=`,
    `~>`, `>=`, `>`, `=` or `==` (a `>` bound kept as written), the highest
    such bound when a set has several, the lowest over `||` alternatives, and
    trailing `x` or `*` components read as 0. `workspace:` and `npm:<name>@`
    prefixes are dropped. A specifier with no lower bound (`<2.0.0`, `*`,
    `latest`, a URL or a path) has none.
    """
    spec = str(text).strip()
    if spec.startswith("workspace:"):
        spec = spec[len("workspace:"):].strip()
    if spec.startswith("npm:") and "@" in spec[5:]:
        spec = spec.rsplit("@", 1)[1].strip()
    if not spec:
        return "empty version"
    plain = _parse_plain_version(spec)
    if plain is not None:
        return plain, "version"
    bounds = []
    for alternative in spec.split("||"):
        bound = _lower_bound(alternative)
        if isinstance(bound, str):
            return bound
        bounds.append(bound)
    return min(bounds, key=_order_key), "range"


def _reduce_or_raise(text):
    """The parsed version `text` reduces to; ValueError when it names none."""
    reduced = _reduce_version(text)
    if isinstance(reduced, str):
        raise ValueError(f"{text!r}: {reduced}")
    return reduced[0]


def normalize_version(text):
    """Reduce a version or a range specifier to one version folder name.

    Returns {input, normalized, rule, build_metadata, reason}: `normalized`
    is null and `reason` says why when the input names no version. See
    `_reduce_version` for the rules; build metadata is stripped as the
    Version Sanitization rules of knowledge/version-paths.md say.
    """
    out = {"input": text, "normalized": None, "rule": None, "build_metadata": None, "reason": None}
    reduced = _reduce_version(text)
    if isinstance(reduced, str):
        out["reason"] = reduced
        return out
    parsed, rule = reduced
    out.update(normalized=_version_text(parsed), rule=rule, build_metadata=parsed[2])
    return out


ORDER_WORDS = {-1: "lower", 0: "equal", 1: "higher"}


class NotIncreasingError(ValueError):
    """A computed version that is not above the version it follows."""


def _sign(a, b):
    return (a > b) - (a < b)


def order_versions(a, b):
    """How version `a` orders against version `b`.

    Returns {a, b, order, major_minor, higher}: `order` and `major_minor` (the
    same test on the first two numbers only) are "lower", "equal" or
    "higher", read as "a is ... than b"; `higher` is the higher normalized
    version, null when they are equal. Raises ValueError when either names no
    version.
    """
    pa, pb = _reduce_or_raise(a), _reduce_or_raise(b)
    cmp = _sign(_order_key(pa), _order_key(pb))
    mm = _sign(tuple(int(p) for p in pa[0][:2]), tuple(int(p) for p in pb[0][:2]))
    return {"a": normalize_version(a), "b": normalize_version(b), "order": ORDER_WORDS[cmp],
            "major_minor": ORDER_WORDS[mm],
            "higher": None if cmp == 0 else _version_text(pa if cmp > 0 else pb)}


def next_patch(text):
    """The next patch version after `text`: the release of a pre-release
    (`1.2.3-rc.1` gives `1.2.3`, as semver's patch increment does), else the
    third number plus one (`1.2.3` gives `1.2.4`; a fourth number is dropped).
    Raises ValueError when `text` names no version."""
    parsed = _reduce_or_raise(text)
    release, pre, _ = parsed
    if pre:
        nxt = ".".join(release)
    else:
        nxt = f"{release[0]}.{release[1]}.{int(release[2]) + 1}"
    if _order_key(_parse_plain_version(nxt)) <= _order_key(parsed):
        raise NotIncreasingError(f"next patch {nxt} is not above {_version_text(parsed)}")
    return {"input": text, "normalized": _version_text(parsed), "next_patch": nxt}


def compose_bump(prior, prior_libraries, libraries):
    """The compose-mode stack version after `prior` (create-stack-skill S11).

    Major when a library of `prior_libraries` is not in `libraries` (removed
    or replaced), else minor. Returns {prior, prior_normalized, bump, version,
    removed, added}. Raises ValueError when `prior` names no version or the
    result is not above it (NotIncreasingError).
    """
    parsed = _reduce_or_raise(prior)
    release = parsed[0]
    before, after = set(prior_libraries), set(libraries)
    removed, added = sorted(before - after), sorted(after - before)
    if removed:
        bump, version = "major", f"{int(release[0]) + 1}.0.0"
    else:
        bump, version = "minor", f"{release[0]}.{int(release[1]) + 1}.0"
    if _order_key(_parse_plain_version(version)) <= _order_key(parsed):
        raise NotIncreasingError(f"{version} is not above the prior version {_version_text(parsed)}")
    return {"prior": prior, "prior_normalized": _version_text(parsed), "bump": bump,
            "version": version, "removed": removed, "added": added}


def primary_library(candidates):
    """The code-mode primary library of a stack and the version it gives (S11).

    `candidates` is a list of {name, import_count, version}. The primary is
    the highest `import_count`. On a tie, a candidate whose version reduces
    to one (see `normalize_version`) goes first, then the lowest name,
    compared case-insensitively. `version` falls back to 1.0.0 when the
    primary has none. Returns {primary, import_count, version_input, version,
    fallback, tied, reason}; `reason` is "highest-import-count",
    "tie-usable-version", "tie-name-order" or "no-candidates". Raises
    ValueError on a malformed candidate.
    """
    rows = []
    for c in candidates:
        if not isinstance(c, dict) or not isinstance(c.get("name"), str) or not c["name"]:
            raise ValueError(f"each candidate needs a name: {c!r}")
        count = c.get("import_count", 0)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"import_count must be a whole number: {c!r}")
        version = c.get("version")
        if version is not None and not isinstance(version, str):
            raise ValueError(f"version must be a string or null: {c!r}")
        usable = version is not None and not isinstance(_reduce_version(version), str)
        rows.append((c["name"], count, version, usable))
    if not rows:
        return {"primary": None, "import_count": None, "version_input": None,
                "version": "1.0.0", "fallback": True, "tied": [], "reason": "no-candidates"}
    top = max(r[1] for r in rows)
    tied = [r for r in rows if r[1] == top]
    pool = [r for r in tied if r[3]] or tied
    name, count, version, usable = min(pool, key=lambda r: (r[0].casefold(), r[0]))
    if len(tied) == 1:
        reason = "highest-import-count"
    elif len(pool) == 1:
        reason = "tie-usable-version"
    else:
        reason = "tie-name-order"
    return {"primary": name, "import_count": count, "version_input": version,
            "version": normalize_version(version)["normalized"] if usable else "1.0.0",
            "fallback": not usable, "tied": sorted((r[0] for r in tied), key=lambda n: (n.casefold(), n)),
            "reason": reason}


def _version_folder_key(name):
    """Newest-first sort key for version folder names; a name that is not a
    version sorts after every version, by name."""
    parsed = _parse_plain_version(name)
    if parsed is None:
        return (0, (), name)
    return (1, _order_key(parsed), name)


# --------------------------------------------------------------------------
# Resolve: the version a reading workflow uses, and its paths
# --------------------------------------------------------------------------

ISO_TIME_RE = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})"
    r"(?:[Tt ](\d{2}):(\d{2})(?::(\d{2})(?:[.,](\d+))?)?)?"
    r"\s*([Zz]|[+-]\d{2}(?::?\d{2})?)?")


# Keep identical to _parse_iso_utc in skf-load-provenance.py
# (test/test-skf-skill-inventory.py pins the copies).
def _parse_iso_utc(value):
    """An ISO-8601 date or date-time as an aware UTC datetime, else None.

    A time without a zone is read as UTC, a date alone as its midnight UTC.
    """
    if not isinstance(value, str):
        return None
    m = ISO_TIME_RE.fullmatch(value.strip())
    if not m:
        return None
    year, month, day, hour, minute, second, fraction, zone = m.groups()
    offset = timedelta(0)
    if zone and zone not in ("Z", "z"):
        digits = zone[1:].replace(":", "")
        offset = timedelta(hours=int(digits[:2]), minutes=int(digits[2:] or 0))
        if zone[0] == "-":
            offset = -offset
    try:
        moment = datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0),
                          int(second or 0), int((fraction or "0")[:6].ljust(6, "0")))
        return (moment - offset).replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError):  # no such date, or out of datetime's range
        return None


def _utc_text(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _provenance_time(path):
    """(generated_at, source) for a provenance map: its `generated_at` field in
    UTC ("provenance-map"), else the file's modification time ("mtime"), else
    (None, None) when there is no map."""
    data, err = read_json_file(path)
    if err is None and isinstance(data, dict):
        moment = _parse_iso_utc(data.get("generated_at"))
        if moment is not None:
            return _utc_text(moment), "provenance-map"
    try:
        if path.is_file():
            return _utc_text(datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)), "mtime"
    except OSError:
        pass
    return None, None


def _active_link_version(skill_group_dir):
    """(version, error) for the `active` link of a skill folder.

    The version is the name of the folder the link leads to when that folder
    sits directly in the skill folder (not a `.skf-` name). A broken or
    looping link, or one that leads anywhere else, gives (None, reason); no
    link gives (None, None). A real `active/` folder is not a link.
    """
    active = skill_group_dir / "active"
    if not _is_link_or_junction(active):
        if active.is_dir():
            return None, f"`active` is a folder, not a link: {active}"
        return None, None
    try:
        target = active.resolve(strict=True)
        group = skill_group_dir.resolve(strict=True)
    except (OSError, RuntimeError):
        return None, f"`active` link is broken: {active}"
    if target.parent != group or ".skf-" in target.name or not target.is_dir():
        return None, f"`active` link does not lead to a version folder of the skill: {active}"
    return target.name, None


def _manifest_versions(entry, updated_at):
    """(active_version, last_exported, {version: status}) from one manifest entry.

    A v2 entry maps each version to its record; a v1 entry lists versions
    and marks the active one deprecated with `deprecated: true`, as
    skf-manifest-ops.py migrates it.
    """
    if not isinstance(entry, dict):
        return None, None, {}
    active = entry.get("active_version")
    active = active if isinstance(active, str) and active else None
    versions = entry.get("versions")
    statuses, last_exported = {}, None
    if isinstance(versions, dict):
        for v, record in versions.items():
            status = record.get("status") if isinstance(record, dict) else None
            statuses[v] = status if isinstance(status, str) else None
        record = versions.get(active) if active else None
        if isinstance(record, dict) and isinstance(record.get("last_exported"), str):
            last_exported = record["last_exported"]
    elif isinstance(versions, list):
        deprecated = entry.get("deprecated") is True
        for v in versions:
            if isinstance(v, str):
                statuses[v] = ("deprecated" if deprecated else "active") if v == active else "archived"
        last_exported = updated_at if isinstance(updated_at, str) else None
    return active, last_exported, statuses


def _disk_versions(skill_group_dir, skill_name):
    """The version folders of a skill folder: each folder directly in it that
    holds a `{name}/` folder (not `active`, a `.skf-` or dot name, or a flat
    package folder beside a root SKILL.md)."""
    try:
        children = list(skill_group_dir.iterdir())
    except OSError:
        return []
    flat = (skill_group_dir / "SKILL.md").is_file()
    found = []
    for child in children:
        name = child.name
        if (name.startswith(".") or _is_active_pointer(name) or ".skf-" in name
                or (flat and name in FLAT_PACKAGE_ENTRIES)):
            continue
        if child.is_dir() and (child / skill_name).is_dir():
            found.append(name)
    return found


def _artifact(versioned, flat):
    """{path, source, versioned, flat}: the first of the two paths that is a
    file, versioned first; `path` and `source` are null when neither is."""
    for source, path in (("versioned", versioned), ("flat", flat)):
        if path is not None and path.is_file():
            return {"path": str(path), "source": source,
                    "versioned": str(versioned) if versioned else None, "flat": str(flat)}
    return {"path": None, "source": None,
            "versioned": str(versioned) if versioned else None, "flat": str(flat)}


RESOLVE_DETAILS = {
    "requested": "the caller asked for version {chosen}",
    "manifest-and-link": "the manifest and the `active` link both name {chosen}",
    "manifest-lags-link": ("the manifest names {manifest} but the `active` link names {chosen}, "
                           "which a writing workflow flipped after the last export; using the "
                           "link (run export-skill to reconcile the manifest)"),
    "manifest": "the manifest names {chosen}",
    "link": "the `active` link names {chosen}; the manifest does not list the skill",
    "flat-layout": "the skill still uses the flat layout (SKILL.md at the skill folder root)",
    "newest-on-disk": ("neither the manifest nor an `active` link names a version on disk; "
                       "{chosen} is the newest version folder"),
    "missing": "no version of the skill is on disk",
}


def resolve_skill(skills_folder, skill_name, forge_data_folder, version=None):
    """Resolve the version a reading workflow uses for `skill_name`, and its paths.

    Implements Reading Workflows in knowledge/version-paths.md. The chosen
    version and `reason`, first that applies:

    - "requested": `version` was given.
    - "manifest-and-link": the manifest's `active_version` and the `active`
      link name the same version, and its package is on disk.
    - "manifest-lags-link": they differ and the link's version has its
      package on disk (the Manifest-lag guard: the link wins).
    - "manifest": the manifest's version has its package on disk (no link,
      or the link names a version with no package).
    - "link": the manifest does not list the skill; the link's version has
      its package on disk.
    - "flat-layout": no version resolved and SKILL.md sits at the skill
      folder root; `chosen_version` and `forge_version` are null.
    - "newest-on-disk": no version resolved, but a version folder holds the
      package; the newest one.
    - "missing": nothing on disk; the manifest's version, else the link's,
      else null.

    `candidates` describes the manifest's and the link's version (package
    on disk, provenance map, its `generated_at` in UTC or the file's mtime).
    `paths` gives metadata.json, provenance-map.json and evidence-report.md,
    each the versioned path when that file exists, else the flat one
    (`{skill_group}/metadata.json`, `{forge_group}/<file>`), else null.
    `versions` lists the manifest's and the on-disk versions newest first,
    with the manifest status of each; `counts` and `newest_non_deprecated`
    (the newest manifest version whose status is not "deprecated") read
    them. Returns None when neither the manifest nor the skills folder
    knows the skill.
    """
    skills_dir, forge_dir = Path(skills_folder), Path(forge_data_folder)
    group, forge_group = skills_dir / skill_name, forge_dir / skill_name
    errors = []
    manifest, manifest_error = read_json_file(skills_dir / ".export-manifest.json")
    if manifest_error and manifest_error.startswith("Not found"):
        manifest_error = None
    if manifest is not None and not isinstance(manifest, dict):
        manifest, manifest_error = None, "the export manifest is not a JSON object"
    exports = manifest.get("exports") if isinstance(manifest, dict) else None
    entry = exports.get(skill_name) if isinstance(exports, dict) else None
    manifest_version, last_exported, statuses = _manifest_versions(
        entry, manifest.get("updated_at") if isinstance(manifest, dict) else None)
    if manifest_version is not None and not _safe_segment(manifest_version):
        errors.append(f"the manifest's active_version is not a folder name: {manifest_version!r}")
        manifest_version = None
    if not isinstance(entry, dict) and not os.path.lexists(group):
        return None
    is_group = group.is_dir()
    link_version, link_error = _active_link_version(group) if is_group else (None, None)
    if link_error:
        errors.append(link_error)
    on_disk = _disk_versions(group, skill_name) if is_group else []

    def has_package(v):
        return v is not None and (group / v / skill_name).is_dir()

    listed = sorted(set(statuses) | set(on_disk), key=_version_folder_key, reverse=True)
    newest_on_disk = next((v for v in listed if v in on_disk), None)
    if version is not None:
        chosen, reason = version, "requested"
    elif has_package(link_version) and link_version == manifest_version:
        chosen, reason = link_version, "manifest-and-link"
    elif has_package(link_version) and manifest_version is not None:
        chosen, reason = link_version, "manifest-lags-link"
    elif has_package(manifest_version):
        chosen, reason = manifest_version, "manifest"
    elif has_package(link_version):
        chosen, reason = link_version, "link"
    elif is_group and (group / "SKILL.md").is_file():
        chosen, reason = None, "flat-layout"
    elif newest_on_disk is not None:
        chosen, reason = newest_on_disk, "newest-on-disk"
    else:
        chosen, reason = manifest_version or link_version, "missing"

    def candidate(v):
        if v is None:
            return None
        provenance = forge_group / v / "provenance-map.json"
        generated_at, source = _provenance_time(provenance)
        return {"version": v, "skill_package_exists": has_package(v),
                "provenance_map": str(provenance) if provenance.is_file() else None,
                "generated_at": generated_at, "generated_at_source": source}

    package = group / chosen / skill_name if chosen else None
    forge_version = forge_group / chosen if chosen else None
    if reason == "flat-layout":
        package = group
    counts = {"total": len(listed), "manifest": len(statuses), "on_disk": len(on_disk),
              "non_deprecated": sum(1 for s in statuses.values() if s != "deprecated"),
              "by_status": {}}
    for status in statuses.values():
        key = status if status is not None else "unknown"
        counts["by_status"][key] = counts["by_status"].get(key, 0) + 1
    return {
        "name": skill_name,
        "layout": "flat" if reason == "flat-layout" else ("versioned" if chosen else "none"),
        "chosen_version": chosen,
        "reason": reason,
        "detail": RESOLVE_DETAILS[reason].format(chosen=chosen, manifest=manifest_version),
        "active_version": manifest_version,
        "manifest_last_exported": last_exported,
        "symlink_target": link_version,
        "candidates": {"manifest": candidate(manifest_version), "symlink": candidate(link_version)},
        "skill_group": str(group),
        "skill_package": str(package) if package else None,
        "skill_package_exists": package is not None and package.is_dir(),
        "forge_group": str(forge_group),
        "forge_version": str(forge_version) if forge_version else None,
        "paths": {
            "metadata": _artifact(package / "metadata.json" if chosen else None,
                                  group / "metadata.json"),
            "provenance_map": _artifact(forge_version / "provenance-map.json" if chosen else None,
                                        forge_group / "provenance-map.json"),
            "evidence_report": _artifact(forge_version / "evidence-report.md" if chosen else None,
                                         forge_group / "evidence-report.md"),
        },
        "versions": [{"version": v, "status": statuses.get(v), "in_manifest": v in statuses,
                      "on_disk": v in on_disk} for v in listed],
        "newest_non_deprecated": next(
            (v for v in listed if v in statuses and statuses[v] != "deprecated"), None),
        "newest_on_disk": newest_on_disk,
        "counts": counts,
        "manifest_error": manifest_error,
        "errors": errors,
    }


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
            if (not entry["skf_skill"] and name != "_batch" and ".skf-" not in name
                    and _looks_like_skill(skill_group_dir, name)):
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
         "--write-check [--write-version <version>] [--forge-data-folder <path>]\n"
         "       uv run skf-skill-inventory.py <skills-output-folder> --skill <name> "
         "--purge-check [--purge-version <version>] --forge-data-folder <path>\n"
         "       uv run skf-skill-inventory.py <skills-output-folder> --skill <name> "
         "--rename-check --forge-data-folder <path>\n"
         "       uv run skf-skill-inventory.py guarded-delete --root <folder> [--root <folder>] "
         "[<path>...]\n"
         "       uv run skf-skill-inventory.py resolve <skills-output-folder> --skill <name> "
         "--forge-data-folder <path> [--version <version>]\n"
         "       uv run skf-skill-inventory.py version normalize <version>\n"
         "       uv run skf-skill-inventory.py version order <a> <b>\n"
         "       uv run skf-skill-inventory.py version next-patch <version>\n"
         "       uv run skf-skill-inventory.py version bump --prior <version> "
         "--prior-libraries <a,b> --libraries <a,c>\n"
         "       uv run skf-skill-inventory.py version primary <candidates.json|->")


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


def _usage_error(message):
    print(json.dumps({"status": "error", "error": message, "code": "USAGE"}, indent=2))
    print(USAGE, file=sys.stderr)
    return 1


def _check_flag_pairs(args, flags):
    """ValueError for an argument that is not one of `flags` followed by its value."""
    for i in range(0, len(args), 2):
        if args[i] not in flags:
            raise ValueError(f"unexpected argument: {args[i]!r}")


def _main_resolve(argv):
    """`resolve <skills-output-folder> --skill <name> --forge-data-folder <path> [--version <v>]`."""
    try:
        if not argv or argv[0].startswith("--"):
            raise ValueError("resolve needs <skills-output-folder> first")
        skill = _flag_value(argv, "--skill", required=True)
        forge_data_folder = _flag_value(argv, "--forge-data-folder", required=True)
        version = _flag_value(argv, "--version", required=True)
        _check_flag_pairs(argv[1:], ("--skill", "--forge-data-folder", "--version"))
        if not skill:
            raise ValueError("resolve needs --skill <name>")
        if not forge_data_folder:
            raise ValueError("resolve needs --forge-data-folder <path>")
        if not _safe_segment(skill):
            raise ValueError(f"--skill must be one folder name: {skill!r}")
        if version is not None and not _safe_segment(version):
            raise ValueError(f"--version must be one folder name: {version!r}")
    except ValueError as e:
        return _usage_error(str(e))
    skills_dir = Path(argv[0])
    if not skills_dir.is_dir():
        result = {"status": "error", "error": f"Skills directory not found: {skills_dir}",
                  "code": "DIR_NOT_FOUND"}
    else:
        resolved = resolve_skill(skills_dir, skill, forge_data_folder, version)
        if resolved is None:
            result = {"status": "error", "code": "SKILL_NOT_FOUND",
                      "error": f"Skill '{skill}' is neither in {skills_dir} nor in its export manifest"}
        else:
            result = {"status": "ok", "skills_folder": str(skills_dir),
                      "forge_data_folder": forge_data_folder, "resolve": resolved}
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ok" else 1


def _library_list(value):
    return [name.strip() for name in value.split(",") if name.strip()]


def _read_candidates(source):
    """The candidate list of `version primary`, from a JSON file or `-` (stdin)."""
    try:
        text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, ValueError) as e:
        raise ValueError(f"cannot read candidates from {source}: {e}") from e
    if not isinstance(data, list):
        raise ValueError("candidates must be a JSON array of {name, import_count, version}")
    return data


def _main_version(argv):
    """`version normalize|order|next-patch|bump|primary ...`; exit 1 with
    `NOT_A_VERSION`, `NOT_INCREASING`, `BAD_INPUT` or `USAGE` on an error."""
    command, args = (argv[0], argv[1:]) if argv else (None, [])
    code = "NOT_A_VERSION"
    try:
        if command == "normalize" and len(args) == 1:
            result = normalize_version(args[0])
            if result["normalized"] is None:
                print(json.dumps({"status": "error", "error": result["reason"],
                                  "code": "NOT_A_VERSION", "command": command, **result}, indent=2))
                return 1
        elif command == "order" and len(args) == 2:
            result = order_versions(args[0], args[1])
        elif command == "next-patch" and len(args) == 1:
            result = next_patch(args[0])
        elif command == "bump":
            try:
                prior = _flag_value(args, "--prior", required=True)
                prior_libraries = _flag_value(args, "--prior-libraries", required=True)
                libraries = _flag_value(args, "--libraries", required=True)
                _check_flag_pairs(args, ("--prior", "--prior-libraries", "--libraries"))
                if prior is None or prior_libraries is None or libraries is None:
                    raise ValueError("bump needs --prior, --prior-libraries and --libraries")
            except ValueError as e:
                return _usage_error(str(e))
            result = compose_bump(prior, _library_list(prior_libraries), _library_list(libraries))
        elif command == "primary" and len(args) == 1:
            code = "BAD_INPUT"
            result = primary_library(_read_candidates(args[0]))
        else:
            return _usage_error(f"unknown version command or wrong arguments: {' '.join(argv)!r}")
    except NotIncreasingError as e:
        print(json.dumps({"status": "error", "error": str(e), "code": "NOT_INCREASING"}, indent=2))
        return 1
    except ValueError as e:
        print(json.dumps({"status": "error", "error": str(e), "code": code}, indent=2))
        return 1
    print(json.dumps({"status": "ok", "command": command, **result}, indent=2))
    return 0


def _main_guarded_delete(argv):
    """`guarded-delete --root <folder> [--root <folder>]... [<path>...]`; exit 0 whatever
    `purge_status` says (no path deletes nothing), exit 1 with `USAGE` on an error."""
    roots, paths = [], []
    try:
        i = 0
        while i < len(argv):
            if argv[i] == "--root":
                if i + 1 >= len(argv) or not argv[i + 1] or argv[i + 1].startswith("--"):
                    raise ValueError("--root needs a folder")
                roots.append(argv[i + 1])
                i += 2
                continue
            if argv[i].startswith("--"):
                raise ValueError(f"unexpected argument: {argv[i]!r}")
            paths.append(argv[i])
            i += 1
        if not roots:
            raise ValueError("guarded-delete needs --root <folder>")
    except ValueError as e:
        return _usage_error(str(e))
    print(json.dumps({"status": "ok", "command": "guarded-delete", **guarded_delete(roots, paths)}, indent=2))
    return 0


# The verdict flags: at most one per call, each with --skill <name>.
CHECK_FLAGS = ("--write-check", "--purge-check", "--rename-check")
CHECK_KEYS = {"--write-check": "write_check", "--purge-check": "purge_check", "--rename-check": "rename_check"}


def main(argv):
    if len(argv) < 1:
        print(USAGE, file=sys.stderr)
        return 1
    if argv[0] == "resolve":
        return _main_resolve(argv[1:])
    if argv[0] == "version":
        return _main_version(argv[1:])
    if argv[0] == "guarded-delete":
        return _main_guarded_delete(argv[1:])
    folder = argv[0]
    checks = [flag for flag in CHECK_FLAGS if flag in argv]
    check = checks[0] if checks else None
    try:
        if len(checks) > 1:
            raise ValueError("pass one of " + ", ".join(CHECK_FLAGS) + ", not several")
        skill = _flag_value(argv, "--skill", required=check is not None)
        match_target = _flag_value(argv, "--match-target")
        forge_data_folder = _flag_value(argv, "--forge-data-folder", required=True)
        versions = {flag: _flag_value(argv, flag, required=True)
                    for flag in ("--write-version", "--purge-version")}
        if check and folder.startswith("--"):
            raise ValueError(f"{check} needs <skills-output-folder> first")
        if check and not skill:
            raise ValueError(f"{check} needs --skill <name>")
        for flag, needs in (("--write-version", "--write-check"), ("--purge-version", "--purge-check")):
            if versions[flag] is not None and check != needs:
                raise ValueError(f"{flag} needs {needs}")
        if check in ("--purge-check", "--rename-check") and not forge_data_folder:
            raise ValueError(f"{check} needs --forge-data-folder <path>")
        if check and not _safe_segment(skill):
            raise ValueError(f"--skill must be one folder name: {skill!r}")
        for flag, value in versions.items():
            if value is not None and not _safe_segment(value):
                raise ValueError(f"{flag} must be one folder name: {value!r}")
    except ValueError as e:
        print(json.dumps({"status": "error", "error": str(e), "code": "USAGE"}, indent=2))
        print(USAGE, file=sys.stderr)
        return 1
    if check:
        skills_dir = Path(folder)
        if os.path.lexists(skills_dir) and not skills_dir.is_dir():
            result = {"status": "error", "error": f"Skills directory not found: {skills_dir}",
                      "code": "DIR_NOT_FOUND"}
        else:
            forge_dir = Path(forge_data_folder) if forge_data_folder else None
            if check == "--write-check":
                verdict = write_check(skills_dir, skill, versions["--write-version"], forge_data_folder)
            elif check == "--purge-check":
                verdict = purge_check(skills_dir, skill, forge_data_folder, versions["--purge-version"])
            else:
                verdict = rename_check(skills_dir, skill, forge_data_folder)
            result = {"status": "ok", "skills_folder": str(skills_dir),
                      "forge_data_folder": forge_data_folder,
                      "same_folder": _same_folder(skills_dir, forge_dir),
                      CHECK_KEYS[check]: verdict}
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
