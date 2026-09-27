# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Enumerate Stack Skills — inventory skill packages + resolve exports.

Replaces the LLM-orchestrated "Exports resolution order" cascade in
`src/skf-create-stack-skill/references/parallel-extract.md` §0. The stage
prose previously asked the model to walk three fallback sources per
constituent skill (metadata.json → references/ → SKILL.md prose) and emit
the cascade decisions inline. That's an N-way implicit-read trap: for a
compose-mode stack with K skills the model must read up to K × 3 files
just to settle the inventory, before any actual per-skill usage analysis
runs.

This helper does the deterministic part once: scan the skills root,
resolve each skill's `exports[]` via the cascade, hash metadata.json
where present, and emit a structured JSON inventory. The per-skill
subagent fan-out at §1+ of parallel-extract.md remains unchanged — the
subprocesses read this inventory's cached result instead of re-reading
SKILL.md, then extract usage patterns per skill (the part that does
benefit from LLM judgment).

Subcommand:
  enumerate <skills-root> [--pairs] [--reliability]
      Emit JSON {"skills": [...], "cycles": [...], "warnings": [...],
      "not_skf_output": [...]} for the skill folders under <skills-root>.

Ownership. A stack roster reads only the skills SKF generated: a package
counts only when its metadata.json carries an SKF marker (generated_by
naming an SKF generator, tool_versions.skf, or skill_type with forge_tier
or confidence_tier), the rule skf-skill-inventory.py applies (the marker
functions are pinned copies of its own). For each top-level folder (dot
names, `_batch` and `.skf-` names aside) the package is the first marked
candidate of: the version the `active` link names (a real folder directly
in the group), the version folders from highest to lowest (`active`,
links and `.skf-` names aside), then a flat root SKILL.md beside a marked
root metadata.json. A versioned package is always `{version}/{name}/`,
named after the folder. The export manifest is never read.

A folder with no marked candidate is left out of `skills[]`: listed in
`not_skf_output` when it looks like a skill (a root SKILL.md or a
`{version}/{name}/` folder), or, when a candidate's metadata.json or
version folder cannot be read, named in one warning instead, because SKF
cannot tell whether it generated that folder. A linked package inside a
version is never SKF output either, and its metadata.json is never read.
A top-level link is never SKF output: it is listed in `not_skf_output`
when it looks like a skill, and a broken one, or one SKF cannot read
through, is skipped. `not_skf_output` is always present, sorted, and
never counts toward `warnings`, `--pairs` or `--reliability`.

Each `skills[]` entry carries:
  name           — the top-level folder name
  path           — the package relative to skills-root, forward-slash:
                   `x/active/x`, `x/{version}/x` or `x` (flat)
  exports        — exports list resolved via cascade
  exports_source — "metadata|references|skill-md|unknown"
  confidence     — "T1|T2|T1-low" (mapped from exports_source)
  metadata_hash  — "sha256:" digest of the package's metadata.json; never
                   null for an enumerated package, whose metadata.json is
                   always readable

Exports resolution cascade (must match parallel-extract.md §0):

  1. metadata.json — if present, valid JSON, and contains an `exports[]`
     array: use the list, mark exports_source="metadata", compute
     metadata_hash = sha256: + sha256(metadata.json content).
     The metadata.json hash is computed even if exports[] is empty —
     callers may want to detect "exports intentionally empty" vs
     "no metadata at all".

  2. references/*.md — scan top-level `*.md` files under references/
     for an `## API` or `## Exports` section. Bulleted list items in
     that section become exports. Set exports_source="references"
     (metadata_hash stays the digest of metadata.json when one was read).

  3. SKILL.md prose — look for an `## Exports` or `## API Surface`
     section and parse its bulleted list. Set exports_source="skill-md"
     (metadata_hash stays the digest of metadata.json when one was read).

  4. None of the above — exports=[], exports_source="unknown",
     confidence="T1-low", append a warning
     `"<skill-name>: no exports found via any resolution path"`.

Confidence mapping:
  metadata    → T1     (structured manifest, trustworthy)
  references  → T2     (heuristic reconstruction, lower trust)
  skill-md    → T2     (prose parsing, comparable trust to references)
  unknown     → T1-low (degraded extraction; nothing found)

Cycle detection:

  metadata.json may declare `composes: ["<skill-name>", ...]` referencing
  other skill packages in this skills-root (compose mode). If A composes
  B and B composes A — directly or transitively — append the cycle's
  starting node to `cycles[]` and emit a warning. Cycles do not abort
  enumeration; the inventory still lists every skill.

Warnings:

  Each starts `<name>: `: a metadata.json or version folder that cannot
  be read (on a candidate passed over, or on a folder SKF cannot tell it
  generated), an SKF package with no SKILL.md, no exports found via any
  resolution path, a folder that cannot be resolved, and composes cycles.

Per-skill errors (malformed metadata.json, OSError, etc.) are captured
as warnings on the top-level result; they do not exit the process.

Optional derived output (additive flags — off by default, so existing
consumers that read only skills/cycles/warnings are unaffected):

  --pairs
      Attach the complete set of unique library pairs derived from the
      inventory: `pairs = [{"library_a": a, "library_b": b}, ...]` over
      `itertools.combinations` of the sorted, deduplicated skill names,
      plus `pair_count == N*(N-1)/2`. This is the deterministic
      combinatorics the refine-architecture gap-analysis prompt used to
      do in-context (where a dropped pair is a silently missed
      integration gap). Sorting the names first makes ordering
      independent of directory-scan order and byte-stable across runs.

  --reliability
      Attach the inventory reliability verdict computed from the counts
      the script already owns, over the skills SKF generated and their
      warnings; `not_skf_output` never counts:
        skill_count       — len(skills)
        warning_count     — len(warnings)
        unreliable_ratio  — warning_count / (skill_count + warning_count),
                            or 0.0 when the inventory is empty
        inventory_reliable — unreliable_ratio <= 0.20 (the RELIABILITY
                            THRESHOLD lives here, in one unit-tested place,
                            so consuming prompts read a boolean instead of
                            re-deriving a ratio + threshold comparison).
      The raw counts are emitted alongside the boolean so a caller's halt
      message can still render "{warning_count} warning(s) across
      {skill_count} skill(s)".

Exit codes:
  0  enumeration succeeded (including zero skills found)
  1  user error (bad skills-root path)

CLI:
  uv run skf-enumerate-stack-skills.py enumerate <skills-root> [--pairs] [--reliability]
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import re
import stat
import sys
from pathlib import Path


# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------


SOURCE_METADATA = "metadata"
SOURCE_REFERENCES = "references"
SOURCE_SKILL_MD = "skill-md"
SOURCE_UNKNOWN = "unknown"

# Inventory reliability policy (single source of truth). If the fraction of
# skip/malformed warnings exceeds this threshold, the inventory is deemed
# unreliable. The gate is `ratio <= THRESHOLD` (i.e. a ratio of exactly 0.20
# is still reliable) so a single malformed skill in a small 3-5 skill
# inventory does not trip the halt.
RELIABILITY_THRESHOLD = 0.20

_CONFIDENCE_BY_SOURCE = {
    SOURCE_METADATA: "T1",
    SOURCE_REFERENCES: "T2",
    SOURCE_SKILL_MD: "T2",
    SOURCE_UNKNOWN: "T1-low",
}

# Section headings recognised in the references/ cascade and the SKILL.md
# cascade. Case-sensitive — these are the canonical SKF heading forms
# documented in parallel-extract.md §0.
_REFERENCES_HEADINGS = ("## API", "## Exports")
_SKILL_MD_HEADINGS = ("## Exports", "## API Surface")

# Bulleted list-item pattern. Permissive: `- foo`, `* foo`, `+ foo`, with
# optional surrounding backticks on the name. We capture the first
# token-like identifier as the export name and stop at whitespace,
# punctuation, or the end-of-backtick.
_LIST_ITEM_RE = re.compile(
    r"^\s*[-*+]\s+`?([A-Za-z_][A-Za-z0-9_.]*)`?",
)

# H2 boundary — any `## ...` line ends the current section.
_H2_BOUNDARY_RE = re.compile(r"^## ")


# --------------------------------------------------------------------------
# Hashing helper
# --------------------------------------------------------------------------


def _sha256_of_bytes(data: bytes) -> str:
    """SHA-256 hex digest with `sha256:` prefix (SKF convention)."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------
# Resolution: metadata.json
# --------------------------------------------------------------------------


def _normalize_exports(raw) -> list[str]:
    """Coerce an exports[] payload (list of strings OR list of {name,...})
    to a flat deduplicated list of names in declaration order.

    Matches skf-render-quick-metadata.py's normalisation so the cascade
    is consistent across the codebase.
    """
    out: list[str] = []
    seen: set[str] = set()
    if not isinstance(raw, list):
        return out
    for item in raw:
        name: str | None = None
        if isinstance(item, str):
            name = item
        elif isinstance(item, dict):
            v = item.get("name")
            if isinstance(v, str):
                name = v
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _resolve_from_metadata(skill_dir: Path) -> tuple[list[str] | None, str | None, list[str], list[str]]:
    """Try to resolve exports from metadata.json.

    Returns (exports, metadata_hash, composes, warnings).
      exports        — list of names if metadata.json was readable AND
                       contained an `exports[]` array (may be empty);
                       None if metadata.json absent or malformed.
      metadata_hash  — sha256: digest of metadata.json content, or None
                       if file absent / unreadable.
      composes       — list of constituent skill names (for cycle
                       detection); empty list if absent.
      warnings       — per-skill warnings (malformed JSON, etc.)
    """
    meta_path = skill_dir / "metadata.json"
    if not meta_path.is_file():
        return None, None, [], []

    warnings: list[str] = []
    try:
        raw_bytes = meta_path.read_bytes()
    except OSError as exc:
        warnings.append(f"failed to read metadata.json: {exc}")
        return None, None, [], warnings

    metadata_hash = _sha256_of_bytes(raw_bytes)

    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        warnings.append(f"metadata.json is not valid JSON: {exc}")
        # Hash is still useful — record it so callers can correlate
        # malformed files across runs.
        return None, metadata_hash, [], warnings

    if not isinstance(data, dict):
        warnings.append("metadata.json root is not an object")
        return None, metadata_hash, [], warnings

    composes_raw = data.get("composes")
    composes = [c for c in composes_raw if isinstance(c, str)] if isinstance(composes_raw, list) else []

    if "exports" not in data:
        # metadata.json exists and is valid JSON but lacks an exports
        # field — fall through to references/ cascade. Carry the hash
        # forward so callers see metadata existed.
        return None, metadata_hash, composes, warnings

    exports = _normalize_exports(data.get("exports"))
    return exports, metadata_hash, composes, warnings


# --------------------------------------------------------------------------
# Resolution: references/ and SKILL.md
# --------------------------------------------------------------------------


def _parse_list_section(content: str, headings: tuple[str, ...]) -> list[str]:
    """Extract bulleted items from the first matching `## <heading>` section.

    Returns names in document order, deduplicated. Returns [] if no
    matching heading is present.

    Section boundaries:
      - starts on the first line equal to one of `headings` (case-sensitive)
      - ends on the next `## ` h2 heading or end-of-file
    """
    out: list[str] = []
    seen: set[str] = set()
    in_section = False
    lines = content.splitlines()
    for line in lines:
        stripped = line.rstrip()
        if not in_section:
            if stripped in headings:
                in_section = True
            continue
        # In-section. Boundary check first, then list-item parse.
        if _H2_BOUNDARY_RE.match(line):
            break
        m = _LIST_ITEM_RE.match(line)
        if m:
            name = m.group(1)
            if name not in seen:
                seen.add(name)
                out.append(name)
    return out


def _resolve_from_references(skill_dir: Path) -> list[str]:
    """Scan references/*.md for `## API` / `## Exports` sections.

    Files are walked in sorted order (deterministic across runs). The
    union of bulleted items from all matching sections is returned,
    deduplicated, in scan order.
    """
    refs_dir = skill_dir / "references"
    if not refs_dir.is_dir():
        return []
    out: list[str] = []
    seen: set[str] = set()
    for md_path in sorted(refs_dir.glob("*.md")):
        try:
            content = md_path.read_text(encoding="utf-8")
        except OSError:
            continue
        for name in _parse_list_section(content, _REFERENCES_HEADINGS):
            if name not in seen:
                seen.add(name)
                out.append(name)
    return out


def _resolve_from_skill_md(skill_dir: Path) -> list[str]:
    """Parse SKILL.md for an `## Exports` / `## API Surface` section."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return []
    try:
        content = skill_md.read_text(encoding="utf-8")
    except OSError:
        return []
    return _parse_list_section(content, _SKILL_MD_HEADINGS)


# --------------------------------------------------------------------------
# Per-skill resolution (cascade orchestrator)
# --------------------------------------------------------------------------


def resolve_skill(skill_dir: Path, skill_name: str) -> tuple[dict, list[str], list[str]]:
    """Build the result entry for a single skill directory.

    Returns (entry, composes, warnings).
      entry      — the dict that will land in result["skills"][]
      composes   — list of skill names this one declares as composed (cycle input)
      warnings   — strings to append to result["warnings"][]
    """
    warnings: list[str] = []

    # 1. metadata.json
    exports, metadata_hash, composes, meta_warnings = _resolve_from_metadata(skill_dir)
    warnings.extend(f"{skill_name}: {w}" for w in meta_warnings)

    if exports is not None:
        source = SOURCE_METADATA
    else:
        # 2. references/
        ref_exports = _resolve_from_references(skill_dir)
        if ref_exports:
            exports = ref_exports
            source = SOURCE_REFERENCES
        else:
            # 3. SKILL.md prose
            sk_exports = _resolve_from_skill_md(skill_dir)
            if sk_exports:
                exports = sk_exports
                source = SOURCE_SKILL_MD
            else:
                # 4. None found
                exports = []
                source = SOURCE_UNKNOWN
                warnings.append(f"{skill_name}: no exports found via any resolution path")

    entry = {
        "name": skill_name,
        "path": skill_name,  # forward-slash relative path under skills-root
        "exports": exports,
        "exports_source": source,
        "confidence": _CONFIDENCE_BY_SOURCE[source],
        "metadata_hash": metadata_hash,
    }
    return entry, composes, warnings


# --------------------------------------------------------------------------
# Cycle detection (composes graph)
# --------------------------------------------------------------------------


def detect_cycles(graph: dict[str, list[str]]) -> list[str]:
    """Find nodes that participate in a `composes` cycle.

    Returns a sorted list of nodes from which a cycle is reachable.
    Each cycle is represented once by the lexicographically-smallest
    node on it — keeps output deterministic across runs without
    requiring callers to interpret a path.

    Algorithm: DFS with WHITE/GRAY/BLACK colouring. A back-edge to a
    GRAY ancestor identifies a cycle; we record the ancestor.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    colour: dict[str, int] = {node: WHITE for node in graph}
    on_path: list[str] = []
    cycle_nodes: set[str] = set()

    def dfs(node: str) -> None:
        colour[node] = GRAY
        on_path.append(node)
        for nbr in graph.get(node, []):
            if nbr not in graph:
                # composes-target not in this skills-root; treat as
                # external, no cycle contribution.
                continue
            c = colour[nbr]
            if c == WHITE:
                dfs(nbr)
            elif c == GRAY:
                # Back-edge → cycle. Record the smallest node on the
                # cycle path from nbr onward.
                idx = on_path.index(nbr)
                cycle_nodes.add(min(on_path[idx:]))
        on_path.pop()
        colour[node] = BLACK

    for node in sorted(graph):
        if colour[node] == WHITE:
            dfs(node)

    return sorted(cycle_nodes)


# --------------------------------------------------------------------------
# Version-nested layout resolution
# --------------------------------------------------------------------------


def _version_sort_key(name: str) -> tuple:
    """Sort key for version directory names — higher sorts as newer.

    Parses the leading dotted numeric core (`N.N.N`); a pre-release suffix
    (`-rc1`, `-beta.2`, ...) ranks below the same core release. Names without
    a numeric core rank lowest. Deterministic tie-break on the raw name.
    """
    core, _, pre = name.partition("-")
    nums: list[int] = []
    for part in core.split("."):
        if part.isdigit():
            nums.append(int(part))
        else:
            break
    return (tuple(nums), 0 if pre == "" else -1, name)


# Keep identical to SKF_GENERATORS in skf-skill-inventory.py
# (test/test-skf-skill-inventory.py pins the copies).
SKF_GENERATORS = frozenset({"quick-skill", "create-skill", "create-stack-skill"})


# Keep identical to _has_skf_metadata in skf-skill-inventory.py
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


# Keep identical to _is_link_or_junction in skf-skill-inventory.py
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


# Keep identical to _is_marked_version in skf-skill-inventory.py
# (test/test-skf-skill-inventory.py pins the copies).
def _is_marked_version(version_dir: Path, name: str) -> bool:
    """True when `version_dir/name/metadata.json` carries an SKF marker.

    SKF never links a version folder or the package inside one: a linked
    one is not its output, whatever the metadata behind the link says.
    """
    package = version_dir / name
    return (not _is_link_or_junction(version_dir) and not _is_link_or_junction(package)
            and _has_skf_metadata(package / "metadata.json"))


# Keep identical to _looks_like_skill in skf-skill-inventory.py
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


def _metadata_problem(package: Path) -> str | None:
    """What keeps `package/metadata.json` from being read, or None.

    None when the file is absent or holds a JSON object; otherwise the
    reason, so a corrupt metadata.json on an SKF skill is counted as a
    warning instead of silently reading as "not SKF output".
    """
    meta_path = package / "metadata.json"
    try:
        # os.stat, not Path.is_file: from Python 3.14 pathlib reads a file
        # SKF cannot reach as absent instead of raising.
        if not stat.S_ISREG(os.stat(meta_path).st_mode):
            return None
        data = json.loads(meta_path.read_bytes().decode("utf-8"))
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as exc:
        return f"failed to read ({exc})"
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return f"is not valid JSON ({exc})"
    if not isinstance(data, dict):
        return "root is not an object"
    return None


def _active_version_dir(child: Path) -> Path | None:
    """The version folder `child/active` names, when it is a folder directly in `child`.

    `active` as a link counts only when it resolves to a real folder
    directly in the group whose name holds no `.skf-`; a real `active/`
    folder counts as itself.
    """
    active = child / "active"
    if _is_link_or_junction(active):
        try:
            target = active.resolve(strict=True)
            group = child.resolve(strict=True)
        except (OSError, RuntimeError):
            return None
        version = child / target.name
        if (target.parent != group or ".skf-" in target.name or not target.is_dir()
                or _is_link_or_junction(version)):
            return None
        return version
    if active.is_dir():
        return active
    return None


def _skf_package(child: Path, name: str) -> tuple[Path | None, list[str]]:
    """The package SKF generated that a stack roster reads, and what it could not read.

    Candidates, in order: the version `active` names, the version folders
    from highest to lowest (`active`, links and `.skf-` names aside), then a
    flat root `SKILL.md`. The first whose `metadata.json` carries an SKF
    marker wins (`{v}/{name}/metadata.json`, or the root one for the flat
    layout). Returns (package, problems): package is None when no candidate
    is marked; problems names each candidate passed over because SKF could
    not read it, its metadata.json or its version folder. A linked package
    is never SKF output (`_is_marked_version`), so it is passed over without
    a problem and its metadata.json is never read.
    """
    problems: list[str] = []

    def marked(version: Path) -> bool:
        package = version / name
        try:
            os.listdir(version)  # raises on every Python when SKF cannot search it
            if _is_marked_version(version, name):
                return True
            if _is_link_or_junction(package):
                return False
        except OSError as exc:
            problems.append(f"{name}/{version.name} cannot be read ({exc})")
            return False
        problem = _metadata_problem(package)
        if problem:
            problems.append(f"{name}/{version.name}/{name}/metadata.json {problem}")
        return False

    active = _active_version_dir(child)
    if active is not None and marked(active):
        return child / "active" / name, problems
    try:
        entries = list(child.iterdir())
    except OSError as exc:
        entries = []
        problems.append(f"{name} cannot be listed ({exc})")
    versions: list[Path] = []
    for entry in entries:
        if (entry.name == "active" or ".skf-" in entry.name
                or (active is not None and entry.name == active.name)):
            continue
        try:
            if _is_link_or_junction(entry) or not entry.is_dir():
                continue
            # os.stat raises on every Python when SKF cannot search `entry`;
            # from 3.14, Path.is_dir would read such a folder as empty.
            if not stat.S_ISDIR(os.stat(entry / name).st_mode):
                continue
        except (FileNotFoundError, NotADirectoryError):
            continue
        except OSError:
            pass  # a folder SKF cannot search may hold a version: marked() names it
        versions.append(entry)
    for vdir in sorted(versions, key=lambda d: _version_sort_key(d.name), reverse=True):
        if marked(vdir):
            return vdir / name, problems
    if (child / "SKILL.md").is_file():
        if _has_skf_metadata(child / "metadata.json"):
            return child, problems
        problem = _metadata_problem(child)
        if problem:
            problems.append(f"{name}/metadata.json {problem}")
    return None, problems


# --------------------------------------------------------------------------
# Enumeration entry point
# --------------------------------------------------------------------------


def enumerate_stack_skills(skills_root: Path) -> dict:
    """Walk `skills_root`, build inventory, detect cycles, return result."""
    result: dict = {"skills": [], "cycles": [], "warnings": [], "not_skf_output": []}
    compose_graph: dict[str, list[str]] = {}

    try:
        children = sorted(skills_root.iterdir())
    except OSError as exc:
        # Shouldn't reach here if CLI validated skills_root.is_dir(),
        # but handle defensively for direct API callers.
        result["warnings"].append(f"failed to read skills root: {exc}")
        return result

    for child in children:
        name = child.name
        if name.startswith(".") or name == "_batch" or ".skf-" in name:
            continue  # hidden folders and SKF's own batch and staging names

        # A linked top-level folder is never SKF output: SKF never links a
        # skill folder. List it when it looks like a skill; a broken link,
        # or one SKF cannot read through, holds nothing to list.
        if _is_link_or_junction(child):
            try:
                if _looks_like_skill(child, name):
                    result["not_skf_output"].append(name)
            except OSError:
                pass
            continue
        if not child.is_dir():
            continue

        try:
            skill_dir, problems = _skf_package(child, name)
            foreign = skill_dir is None and not problems and _looks_like_skill(child, name)
        except Exception as exc:  # noqa: BLE001 — per-skill failures are warnings, not fatal
            # An unreadable folder raises OSError; a metadata.json nested
            # too deeply for the JSON parser raises RecursionError.
            result["warnings"].append(f"{name}: failed to resolve package dir ({exc})")
            continue
        if skill_dir is None:
            if problems:
                result["warnings"].append(
                    f"{name}: SKF cannot tell whether it generated this skill: "
                    + "; ".join(problems))
            elif foreign:
                result["not_skf_output"].append(name)
            continue
        rel = skill_dir.relative_to(skills_root).as_posix()
        if problems:
            result["warnings"].append(
                f"{name}: " + "; ".join(problems) + f"; read the SKF package at {rel} instead")
        if not (skill_dir / "SKILL.md").is_file():
            result["warnings"].append(f"{name}: the SKF package at {rel} has no SKILL.md")
            continue

        try:
            entry, composes, skill_warnings = resolve_skill(skill_dir, name)
        except Exception as exc:  # noqa: BLE001 — per-skill failures are warnings, not fatal
            result["warnings"].append(f"{name}: enumeration failed: {exc}")
            continue

        # The resolved package location, forward-slash and relative to
        # skills_root: `x/active/x`, `x/{version}/x` or `x` (flat).
        entry["path"] = rel
        result["skills"].append(entry)
        result["warnings"].extend(skill_warnings)
        compose_graph[name] = composes

    result["cycles"] = detect_cycles(compose_graph)
    for cycle_node in result["cycles"]:
        result["warnings"].append(
            f"{cycle_node}: composes cycle detected"
        )
    return result


# --------------------------------------------------------------------------
# Derived output: unique library pairs (--pairs)
# --------------------------------------------------------------------------


def compute_pairs(skills: list[dict]) -> list[dict]:
    """Deterministic unique library pairs from an inventory's skills[].

    Returns `[{"library_a": a, "library_b": b}, ...]` over every
    combination of the sorted, deduplicated skill names — exactly
    N*(N-1)/2 entries for N distinct names. Sorting first makes the order
    independent of directory-scan order and byte-stable across runs; the
    dedup guards against a pathological repeated name yielding a duplicate
    pair. Never drops or duplicates a pair, unlike in-context enumeration
    at larger N.
    """
    names = sorted({e["name"] for e in skills})
    return [
        {"library_a": a, "library_b": b}
        for a, b in itertools.combinations(names, 2)
    ]


# --------------------------------------------------------------------------
# Derived output: inventory reliability verdict (--reliability)
# --------------------------------------------------------------------------


def compute_reliability(skill_count: int, warning_count: int) -> dict:
    """Reliability verdict from the inventory's own counts.

    `unreliable_ratio` = warning_count / (skill_count + warning_count),
    or 0.0 for an empty inventory (no ZeroDivisionError). The inventory is
    reliable when that ratio is <= RELIABILITY_THRESHOLD (boundary
    inclusive). Emits the raw counts too so a caller's halt message can
    render "{warning_count} warning(s) across {skill_count} skill(s)".
    """
    total = skill_count + warning_count
    unreliable_ratio = (warning_count / total) if total else 0.0
    return {
        "inventory_reliable": unreliable_ratio <= RELIABILITY_THRESHOLD,
        "unreliable_ratio": unreliable_ratio,
        "skill_count": skill_count,
        "warning_count": warning_count,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_enumerate(args: argparse.Namespace) -> int:
    skills_root = Path(args.skills_root)
    if not skills_root.is_dir():
        print(
            f"error: skills root not a directory: {skills_root}",
            file=sys.stderr,
        )
        return 1
    result = enumerate_stack_skills(skills_root)
    # Additive derived output — attached only when the flag is set, so the
    # default shape stays {skills, cycles, warnings, not_skf_output}.
    if args.pairs:
        result["pairs"] = compute_pairs(result["skills"])
        result["pair_count"] = len(result["pairs"])
    if args.reliability:
        result.update(
            compute_reliability(len(result["skills"]), len(result["warnings"]))
        )
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-enumerate-stack-skills",
        description=(
            "Enumerate skill packages under a skills root and resolve "
            "each package's exports via the metadata.json → references/ "
            "→ SKILL.md cascade."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_enum = sub.add_parser(
        "enumerate",
        help="walk skills-root and emit JSON inventory",
    )
    p_enum.add_argument(
        "skills_root",
        help="directory holding skill folders; only packages SKF generated are enumerated",
    )
    p_enum.add_argument(
        "--pairs",
        action="store_true",
        help=(
            "additionally emit `pairs[]` (unique {library_a, library_b} "
            "combinations over the sorted skill names) and `pair_count`"
        ),
    )
    p_enum.add_argument(
        "--reliability",
        action="store_true",
        help=(
            "additionally emit the reliability verdict "
            "(`inventory_reliable`, `unreliable_ratio`, `skill_count`, "
            f"`warning_count`; threshold {RELIABILITY_THRESHOLD})"
        ),
    )
    p_enum.set_defaults(func=_cmd_enumerate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
