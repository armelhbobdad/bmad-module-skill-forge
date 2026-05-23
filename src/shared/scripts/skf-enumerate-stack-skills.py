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
  enumerate <skills-root>
      Emit JSON {"skills": [...], "cycles": [...], "warnings": [...]}
      describing every subdirectory of <skills-root> that resolves to a
      skill package. Both layouts from knowledge/version-paths.md are
      supported: the flat layout (<child>/SKILL.md) and the version-nested
      layout (<child>/active/<name>/SKILL.md via the `active` symlink, or
      <child>/<version>/<name>/SKILL.md by highest version). Each entry
      carries:

        name             — skill name (top-level subdirectory name)
        path             — relative path to the resolved package under
                           skills-root, forward-slash
        exports          — exports list resolved via cascade
        exports_source   — "metadata|references|skill-md|unknown"
        confidence       — "T1|T2|T1-low" (mapped from exports_source)
        metadata_hash    — sha256: prefix on metadata.json digest, or null

Exports resolution cascade (must match parallel-extract.md §0):

  1. metadata.json — if present, valid JSON, and contains an `exports[]`
     array: use the list, mark exports_source="metadata", compute
     metadata_hash = sha256: + sha256(metadata.json content).
     The metadata.json hash is computed even if exports[] is empty —
     callers may want to detect "exports intentionally empty" vs
     "no metadata at all".

  2. references/*.md — scan top-level `*.md` files under references/
     for an `## API` or `## Exports` section. Bulleted list items in
     that section become exports. Set exports_source="references",
     metadata_hash=null.

  3. SKILL.md prose — look for an `## Exports` or `## API Surface`
     section and parse its bulleted list. Set exports_source="skill-md",
     metadata_hash=null.

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

Symlink handling:

  A skill directory may itself be a symlink (e.g. an "active" pointer).
  If the target is unreadable (broken symlink, permission denied, etc.),
  emit a warning and skip the entry — do not crash the whole scan.

Per-skill errors (malformed metadata.json, OSError, etc.) are captured
as warnings on the top-level result; they do not exit the process.

Exit codes:
  0  enumeration succeeded (including zero skills found)
  1  user error (bad skills-root path)

CLI:
  uv run skf-enumerate-stack-skills.py enumerate <skills-root>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------


SOURCE_METADATA = "metadata"
SOURCE_REFERENCES = "references"
SOURCE_SKILL_MD = "skill-md"
SOURCE_UNKNOWN = "unknown"

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


def _inner_package(version_dir: Path) -> Path | None:
    """Within a version directory, return the inner package dir holding SKILL.md.

    Matches the `{version}/{skill-name}/SKILL.md` shape from
    knowledge/version-paths.md. Returns None if no inner dir has a SKILL.md.
    """
    try:
        for inner in sorted(version_dir.iterdir()):
            if inner.is_dir() and (inner / "SKILL.md").is_file():
                return inner
    except OSError:
        return None
    return None


def _resolve_package_dir(child: Path) -> Path | None:
    """Resolve the agentskills package dir (the one containing SKILL.md).

    Supports both layouts defined in knowledge/version-paths.md:
      - flat:           {child}/SKILL.md
      - version-nested: {child}/active/{skill-name}/SKILL.md (via the `active`
                        symlink) or {child}/{version}/{skill-name}/SKILL.md.

    For the nested layout the `active` symlink wins; otherwise the highest
    version directory by semver precedence is used. Returns None when no
    SKILL.md is reachable (caller skips the entry as a non-package).
    """
    # Flat layout — direct SKILL.md.
    if (child / "SKILL.md").is_file():
        return child

    # Nested layout — prefer the stable `active` pointer.
    active = child / "active"
    if active.is_dir():  # is_dir() follows the symlink; False if broken
        pkg = _inner_package(active)
        if pkg is not None:
            return pkg

    # Fallback — highest version directory.
    try:
        version_dirs = [
            d for d in child.iterdir() if d.is_dir() and d.name != "active"
        ]
    except OSError:
        return None
    for vdir in sorted(version_dirs, key=lambda d: _version_sort_key(d.name), reverse=True):
        pkg = _inner_package(vdir)
        if pkg is not None:
            return pkg
    return None


# --------------------------------------------------------------------------
# Enumeration entry point
# --------------------------------------------------------------------------


def enumerate_stack_skills(skills_root: Path) -> dict:
    """Walk `skills_root`, build inventory, detect cycles, return result."""
    result: dict = {"skills": [], "cycles": [], "warnings": []}
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
        if name.startswith("."):
            continue

        # Symlink fallback — a child-level symlink (e.g. a top-level `active`
        # pointer) must resolve to a readable directory. If it's broken, warn
        # and skip; otherwise keep the original path so the reported `path`
        # stays relative to skills_root.
        if child.is_symlink():
            try:
                target = child.resolve(strict=True)
            except (FileNotFoundError, RuntimeError, OSError) as exc:
                result["warnings"].append(
                    f"{name}: symlink target unreadable ({exc})"
                )
                continue
            if not target.is_dir():
                result["warnings"].append(
                    f"{name}: symlink target is not a directory"
                )
                continue
        elif not child.is_dir():
            continue

        # Resolve the package dir across flat and version-nested layouts
        # (knowledge/version-paths.md). Subdirs with no reachable SKILL.md
        # (e.g. `shared/`, `knowledge/`) are skipped silently — not packages.
        try:
            skill_dir = _resolve_package_dir(child)
        except OSError as exc:
            result["warnings"].append(f"{name}: failed to resolve package dir ({exc})")
            continue
        if skill_dir is None:
            continue

        try:
            entry, composes, skill_warnings = resolve_skill(skill_dir, name)
        except Exception as exc:  # noqa: BLE001 — per-skill failures are warnings, not fatal
            result["warnings"].append(f"{name}: enumeration failed: {exc}")
            continue

        # Reflect the resolved package location (forward-slash, relative to
        # skills_root) — for the nested layout this is the `{active_skill}`
        # path, for the flat layout just the skill name.
        try:
            entry["path"] = skill_dir.relative_to(skills_root).as_posix()
        except ValueError:
            entry["path"] = name

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
        help="directory containing skill packages (each subdir has SKILL.md)",
    )
    p_enum.set_defaults(func=_cmd_enumerate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
