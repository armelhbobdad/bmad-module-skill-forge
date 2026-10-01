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

Subcommands:
  enumerate <skills-root> [--pairs] [--reliability] [--expect-hashes FILE]
      Emit JSON {"skills": [...], "cycles": [...], "warnings": [...],
      "not_skf_output": [...]} for the skill folders under <skills-root>.
  candidates <skills-root> [--explicit a,b]
      Pick the compose-mode candidates and gate them against the same
      roster, in one call (see Candidates below).
  scope --skills a,b,c --in-scope a,b
      Split the unique pairs of an inventory's skills by the skills in
      scope (see Scope below).

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
named after the folder. `enumerate` never reads the export manifest;
`candidates` reads it only to pick candidates, and the package of each
one it keeps still comes from this roster.

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
  name            the top-level folder name
  path            the package relative to skills-root, forward-slash:
                  `x/active/x`, `x/{version}/x` or `x` (flat)
  exports         exports list resolved via cascade
  exports_source  "metadata|references|skill-md|unknown"
  confidence      "T1|T2|T1-low", the exports-source label (mapped from
                  exports_source, see Confidence mapping)
  evidence_tier   "T1|T1-low|T2|T3", the tier the package's own recorded
                  evidence supports (see Evidence tier)
  metadata_hash   "sha256:" digest of the package's metadata.json; never
                  null for an enumerated package, whose metadata.json is
                  always readable
  skill_type      metadata.json `skill_type`, when it is a string
  language        metadata.json `language`: a string, or a list of
                  strings (a stack may list its libraries' languages)
  confidence_tier metadata.json `confidence_tier`, when it belongs to the
                  scale its skill_type records: a forge tier
                  (Quick|Forge|Forge+|Deep) for a single skill (skill_type
                  single, individual or null), a confidence tier
                  (T1|T1-low|T2|T3) for a stack, either scale for any
                  other skill_type
  exports_documented
                  metadata.json `stats.exports_documented`, a whole number
  metadata_schema_version
                  metadata.json `spec_version`, the metadata schema the
                  package was written to (such as "1.3")
  source_repo     metadata.json `source_repo`, trimmed
  source_repo_basename
                  the repository name source_repo ends in (see Source
                  basenames)
  source_root     metadata.json `source_root`, trimmed
  source_root_basename
                  the last folder name of source_root (see Source
                  basenames)
Each metadata.json field is null when the file lacks it or holds a value
of another shape, so a caller never reopens metadata.json to read it.

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

  `confidence` says only where the exports list came from: every package
  whose metadata.json lists exports (even an empty list, which SKF's
  generators always write) reads T1, whatever evidence it rests on.

Evidence tier:

  `evidence_tier` is the largest bin of the package's metadata.json
  `confidence_distribution` (t1 is T1, t1_low T1-low, t2 T2, t3 T3). A tie
  goes to the weaker tier (T1-low over T1, T2 over T1-low, T3 over T2), so
  the tier never overstates confidence. A bin counts only when it holds a
  positive number; with none (the distribution is absent, not an object or
  all zero) the tier is T1-low, the conservative default. create-stack-skill
  picks a stack's own confidence_tier by the same rule. A docs-only skill
  whose bins are all T3 reads T3 here, while its `confidence` reads T1.

Source basenames:

  Lower case, from the last non-empty segment between `/` or `\\`
  separators, for matching a skill to a technology name.
  source_repo_basename also drops a trailing `.git`, and is null when
  source_repo holds no separator (it is then no URL, owner/repo pair or
  path). Either is null when no name remains (such as `.` or `..`).
  `https://github.com/Org/Repo.git/` and `Org/Repo` both give `repo`; a
  source_root of `packages/Core` gives `core`.

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

  --expect-hashes FILE
      Compare each skill's metadata_hash with the one FILE recorded for it
      and attach three sorted name lists: `changed_skills` (enumerated now
      with another metadata_hash), `missing_skills` (recorded, but not
      enumerated now: removed, or no longer readable) and `new_skills`
      (enumerated now, not recorded). FILE, or stdin for `-`, holds an
      earlier enumerate result (its skills[] entries give each name's
      metadata_hash) or an object mapping each skill name to its hash.
      Hashes compare as written. A caller that verifies skills over a long
      run re-enumerates with the result it started from, instead of
      re-reading each metadata.json modification time.

Candidates:

  Compose mode builds a stack from the skills SKF generated. The
  `candidates` subcommand picks them and gates them against the roster
  `enumerate` builds:

  candidate_source
      Where the candidates came from. "explicit": the --explicit names
      (trimmed, duplicates dropped). An --explicit entry that holds `/` or
      `\\` is a package path instead, absolute or relative to the current
      folder: it names the first folder of its path under <skills-root>
      (`<skills-root>/react/1.2.0/react` and `<skills-root>/react/active/react`
      both name `react`). "manifest": each key of
      `<skills-root>/.export-manifest.json` `exports`. "active-links": when
      there is no --explicit list and the manifest is absent, lists
      nothing or cannot be read, each top-level folder holding
      `active/<name>/SKILL.md` (`active` a link or a real folder; dot
      names never match, and `_batch` and `.skf-` names are skipped as the
      roster skips them).
  kept
      The roster entries (the shape of a skills[] entry) of the candidates
      whose skill_type is single, individual or null (an early Quick Skill
      package), sorted by name.
  excluded
      Every other candidate, once, as {skill_dir, reason, message}, sorted
      by skill_dir. `message` is the log line to show, starting
      `<skill_dir>: `. The reason is the first that applies:
        not-a-skill     in the roster with another skill_type (a stack)
        not-skf-output  listed in not_skf_output
        roster-warning  named by roster warnings (the message holds them)
        no-such-folder  an --explicit name with no folder at
                        <skills-root>/<name>
        no-skf-package  anything else (a folder holding no SKF package)
      and an --explicit package path that is not inside <skills-root> is
      excluded as given, with the reason `outside-skills-root`.
  stale_manifest_keys
      The manifest keys with no folder at <skills-root>/<key>, sorted: the
      manifest names a skill that is gone, which the caller halts on. A
      folder SKF cannot read is not called gone. Never in excluded.
  manifest_parse_error
      Why the manifest could not be read (unreadable, not JSON, its root or
      its `exports` not an object); the candidates then come from the
      active links. null otherwise, and whenever --explicit is given (the
      manifest is not read then).

  The result also carries the roster's `cycles`, `warnings` and
  `not_skf_output`, with kept[] in place of skills[]. A composes cycle is
  not an exclusion reason: cycles[] reports it as `enumerate` does.

Scope:

  refine-architecture decides which skills its architecture document
  covers after `enumerate` ran. The `scope` subcommand splits the pairs
  `--pairs` emitted, so no prompt sorts them by hand, and a pair is never
  dropped from both halves. It reads no skills root: --skills names the
  inventory (the `name` of each skills[] entry of an enumerate result) and
  --in-scope the skills in scope, both comma-separated, trimmed, with empty
  items dropped. Names compare exactly, as skills[] spells them.

  in_scope            the --in-scope names that are inventory skills, sorted
  out_of_scope        every other inventory skill, sorted
  unknown             the --in-scope names that are no inventory skill, each
                      once, in the order given
  in_scope_pairs      the pairs, as `--pairs` emits them over --skills,
                      whose library_a and library_b are both in in_scope
  out_of_scope_pairs  every other pair: the two lists hold each pair once
  pair_count, in_scope_pair_count, out_of_scope_pair_count
                      the sizes of the three pair lists (all, in, out)

Exit codes:
  0  enumeration succeeded (including zero skills found)
  1  user error: a bad skills-root path, an --expect-hashes FILE that
     cannot be read or holds neither accepted shape, an --explicit list
     that names no skill, or a scope --skills list that names no skill

CLI:
  uv run skf-enumerate-stack-skills.py enumerate <skills-root> [--pairs] [--reliability] [--expect-hashes FILE]
  uv run skf-enumerate-stack-skills.py candidates <skills-root> [--explicit a,b]
  uv run skf-enumerate-stack-skills.py scope --skills a,b,c --in-scope a,b
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
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

# The exports-source label (`confidence`). It says where the exports list
# came from, never what evidence the package rests on: that is evidence_tier.
_CONFIDENCE_BY_SOURCE = {
    SOURCE_METADATA: "T1",
    SOURCE_REFERENCES: "T2",
    SOURCE_SKILL_MD: "T2",
    SOURCE_UNKNOWN: "T1-low",
}

# The confidence_distribution bins of metadata.json, from the strongest tier
# to the weakest. dominant_tier reads them in this order and lets a later bin
# win a tie, so a tie resolves toward the weaker tier.
_DISTRIBUTION_BINS = (("t1", "T1"), ("t1_low", "T1-low"), ("t2", "T2"), ("t3", "T3"))

# The tier of a package that records no evidence (the conservative default).
_NO_EVIDENCE_TIER = "T1-low"

# confidence_tier holds a different scale per skill_type: a single skill
# records the forge tier it was compiled at, a stack the dominant confidence
# tier of its libraries (its forge tier is in forge_tier). skill_type
# individual (the earlier name for single) and a missing skill_type (an early
# Quick Skill package) read as single; any other skill_type takes either scale.
_FORGE_TIERS = ("Quick", "Forge", "Forge+", "Deep")
_STACK_TIERS = ("T1", "T1-low", "T2", "T3")
_SINGLE_SKILL_TYPES = (None, "single", "individual")

# A source_repo or source_root path or URL splits into segments on either
# separator.
_PATH_SEPARATOR_RE = re.compile(r"[/\\]")

# candidates: the export manifest in the skills root, where each candidate
# came from, and why a candidate was excluded.
EXPORT_MANIFEST = ".export-manifest.json"
CANDIDATES_EXPLICIT = "explicit"
CANDIDATES_MANIFEST = "manifest"
CANDIDATES_ACTIVE_LINKS = "active-links"
REASON_NOT_A_SKILL = "not-a-skill"
REASON_NOT_SKF_OUTPUT = "not-skf-output"
REASON_ROSTER_WARNING = "roster-warning"
REASON_NO_SUCH_FOLDER = "no-such-folder"
REASON_NO_SKF_PACKAGE = "no-skf-package"
REASON_OUTSIDE_SKILLS_ROOT = "outside-skills-root"

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


def _resolve_from_metadata(skill_dir: Path) -> tuple[list[str] | None, str | None, list[str], list[str], dict]:
    """Try to resolve exports from metadata.json.

    Returns (exports, metadata_hash, composes, warnings, metadata).
      exports        : list of names if metadata.json was readable AND
                       contained an `exports[]` array (may be empty);
                       None if metadata.json absent or malformed.
      metadata_hash  : sha256: digest of metadata.json content, or None
                       if file absent / unreadable.
      composes       : list of constituent skill names (for cycle
                       detection); empty list if absent.
      warnings       : per-skill warnings (malformed JSON, etc.)
      metadata       : the parsed metadata.json object, or {} when the
                       file is absent, unreadable or not a JSON object.
    """
    meta_path = skill_dir / "metadata.json"
    if not meta_path.is_file():
        return None, None, [], [], {}

    warnings: list[str] = []
    try:
        raw_bytes = meta_path.read_bytes()
    except OSError as exc:
        warnings.append(f"failed to read metadata.json: {exc}")
        return None, None, [], warnings, {}

    metadata_hash = _sha256_of_bytes(raw_bytes)

    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        warnings.append(f"metadata.json is not valid JSON: {exc}")
        # Hash is still useful — record it so callers can correlate
        # malformed files across runs.
        return None, metadata_hash, [], warnings, {}

    if not isinstance(data, dict):
        warnings.append("metadata.json root is not an object")
        return None, metadata_hash, [], warnings, {}

    composes_raw = data.get("composes")
    composes = [c for c in composes_raw if isinstance(c, str)] if isinstance(composes_raw, list) else []

    if "exports" not in data:
        # metadata.json exists and is valid JSON but lacks an exports
        # field — fall through to references/ cascade. Carry the hash
        # forward so callers see metadata existed.
        return None, metadata_hash, composes, warnings, data

    exports = _normalize_exports(data.get("exports"))
    return exports, metadata_hash, composes, warnings, data


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
# Evidence tier and metadata.json fields
# --------------------------------------------------------------------------


def _bin_count(value):
    """A confidence_distribution bin's count: a positive finite number, else 0."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    if isinstance(value, float) and not math.isfinite(value):
        return 0
    return value if value > 0 else 0


def dominant_tier(distribution) -> str:
    """The tier of the largest bin of a metadata.json confidence_distribution.

    The bins are read from the strongest tier to the weakest and a later bin
    wins a tie, so a tie resolves toward the weaker tier (T1-low over T1, T2
    over T1-low, T3 over T2) and the tier never overstates confidence. A bin
    counts only when it holds a positive number. T1-low when none does: the
    distribution is absent, not an object or all zero.
    """
    tier, best = _NO_EVIDENCE_TIER, 0
    if isinstance(distribution, dict):
        for key, bin_tier in _DISTRIBUTION_BINS:
            count = _bin_count(distribution.get(key))
            if count and count >= best:
                tier, best = bin_tier, count
    return tier


def _text(value) -> str | None:
    """A string with its surrounding whitespace removed, or None when empty or not a string."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _language(value) -> str | list[str] | None:
    """metadata.json `language`: a string, or the strings of a list (a stack may list several)."""
    if isinstance(value, list):
        names = [name for name in (_text(item) for item in value) if name]
        return names or None
    return _text(value)


def _confidence_tier(value, skill_type: str | None) -> str | None:
    """metadata.json `confidence_tier` when it belongs to its skill_type's scale."""
    if skill_type == "stack":
        allowed = _STACK_TIERS
    elif skill_type in _SINGLE_SKILL_TYPES:
        allowed = _FORGE_TIERS
    else:
        allowed = _FORGE_TIERS + _STACK_TIERS
    return value if isinstance(value, str) and value in allowed else None


def _whole_number(value) -> int | None:
    """A non-negative whole number (an integral float too), else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return value if isinstance(value, int) and value >= 0 else None


def _last_segment(value: str) -> str | None:
    """The lower-case last non-empty `/` or `\\` segment, or None when it names no folder."""
    segments = [segment for segment in _PATH_SEPARATOR_RE.split(value) if segment]
    if not segments or segments[-1] in (".", ".."):
        return None
    return segments[-1].lower()


def source_repo_basename(source_repo: str | None) -> str | None:
    """The repository name a source_repo URL, owner/repo pair or path ends in.

    The last segment, lower case, without a trailing `.git`. None when
    source_repo is absent, holds no separator (so it is no URL, pair or
    path), or leaves no name.
    """
    if source_repo is None or not _PATH_SEPARATOR_RE.search(source_repo):
        return None
    segment = _last_segment(source_repo)
    if segment is not None and segment.endswith(".git"):
        segment = segment[:-len(".git")]
    return segment if segment not in (None, "", ".", "..") else None


def source_root_basename(source_root: str | None) -> str | None:
    """The last folder name of a source_root path, lower case, or None."""
    return None if source_root is None else _last_segment(source_root)


def metadata_fields(metadata: dict) -> dict:
    """The metadata.json facts a skills[] entry carries besides its exports.

    Each is None when metadata.json lacks it or holds a value of another
    shape, so a caller never reopens metadata.json to read it.
    """
    skill_type = metadata.get("skill_type")
    if not isinstance(skill_type, str):
        skill_type = None
    stats = metadata.get("stats")
    source_repo = _text(metadata.get("source_repo"))
    source_root = _text(metadata.get("source_root"))
    return {
        "skill_type": skill_type,
        "language": _language(metadata.get("language")),
        "confidence_tier": _confidence_tier(metadata.get("confidence_tier"), skill_type),
        "exports_documented": _whole_number(
            stats.get("exports_documented") if isinstance(stats, dict) else None),
        "metadata_schema_version": _text(metadata.get("spec_version")),
        "source_repo": source_repo,
        "source_repo_basename": source_repo_basename(source_repo),
        "source_root": source_root,
        "source_root_basename": source_root_basename(source_root),
    }


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
    exports, metadata_hash, composes, meta_warnings, metadata = _resolve_from_metadata(skill_dir)
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
        "evidence_tier": dominant_tier(metadata.get("confidence_distribution")),
        "metadata_hash": metadata_hash,
    }
    entry.update(metadata_fields(metadata))
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


def compute_scope(names: list[str], in_scope: list[str]) -> dict:
    """Split an inventory's pairs by the skills in scope (`scope`).

    `names` are the inventory's skill names and `in_scope` the names of the
    skills in scope. The pairs are compute_pairs() over `names`, so they are
    the ones `--pairs` emitted, in the same order; a pair is in scope when
    both of its libraries are. See "Scope" in the module docstring for the
    keys.
    """
    known = set(names)
    unknown: list[str] = []
    for name in in_scope:
        if name not in known and name not in unknown:
            unknown.append(name)
    kept = {name for name in in_scope if name in known}
    pairs = compute_pairs([{"name": name} for name in known])
    inside = [p for p in pairs if p["library_a"] in kept and p["library_b"] in kept]
    outside = [p for p in pairs if not (p["library_a"] in kept and p["library_b"] in kept)]
    return {
        "in_scope": sorted(kept),
        "out_of_scope": sorted(known - kept),
        "unknown": unknown,
        "in_scope_pairs": inside,
        "out_of_scope_pairs": outside,
        "pair_count": len(pairs),
        "in_scope_pair_count": len(inside),
        "out_of_scope_pair_count": len(outside),
    }


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
# Derived output: metadata_hash changes (--expect-hashes)
# --------------------------------------------------------------------------


def load_expected_hashes(text: str) -> dict[str, str | None]:
    """The metadata_hash recorded for each skill name, from --expect-hashes JSON.

    Takes an enumerate result, whose skills[] entries give each `name` its
    `metadata_hash`, or an object mapping each skill name to its hash (a
    string, or null for none). Raises ValueError on anything else.
    """
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("the JSON root is not an object")
    if not isinstance(data.get("skills"), list):
        if not all(h is None or isinstance(h, str) for h in data.values()):
            raise ValueError(
                "expected an enumerate result (with skills[]) or an object "
                "mapping each skill name to its metadata_hash")
        return dict(data)
    expected: dict[str, str | None] = {}
    for entry in data["skills"]:
        name = entry.get("name") if isinstance(entry, dict) else None
        if not isinstance(name, str):
            raise ValueError("a skills[] entry has no string name")
        metadata_hash = entry.get("metadata_hash")
        if metadata_hash is not None and not isinstance(metadata_hash, str):
            raise ValueError(f"skills[] entry {name!r} has a metadata_hash that is not a string")
        if name in expected:
            raise ValueError(f"skills[] lists {name!r} twice")
        expected[name] = metadata_hash
    return expected


def compare_hashes(skills: list[dict], expected: dict[str, str | None]) -> dict:
    """Which skills changed against the metadata_hash recorded for them.

    changed_skills: enumerated now with another metadata_hash;
    missing_skills: recorded but not enumerated now; new_skills: enumerated
    now but not recorded. Each sorted by name; hashes compare as written.
    """
    current = {entry["name"]: entry["metadata_hash"] for entry in skills}
    return {
        "changed_skills": sorted(
            name for name, metadata_hash in expected.items()
            if name in current and current[name] != metadata_hash),
        "missing_skills": sorted(name for name in expected if name not in current),
        "new_skills": sorted(name for name in current if name not in expected),
    }


# --------------------------------------------------------------------------
# Candidates: pick the compose-mode candidates and gate them (candidates)
# --------------------------------------------------------------------------


def _is_folder_name(skills_root: Path, name: str) -> bool:
    """True when `name` can name one folder directly in `skills_root`."""
    folder = skills_root / name
    return (name not in ("", ".", "..") and "\x00" not in name
            and folder.parent == skills_root and folder.name == name)


def _has_folder(skills_root: Path, name: str) -> bool:
    """True when `skills_root/name` is a folder, or SKF cannot tell.

    A name that cannot be one folder in the skills root (empty, `.`, `..`, a
    path) never is. A folder SKF cannot stat counts as present, so a
    manifest key is never called stale because of a folder SKF only fails to
    read.
    """
    if not _is_folder_name(skills_root, name):
        return False
    try:
        return stat.S_ISDIR(os.stat(skills_root / name).st_mode)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError:
        return True


def _manifest_keys(skills_root: Path) -> tuple[list[str], str | None]:
    """The skill names the export manifest lists, and why it could not be read.

    ([], None) when the manifest is absent or lists nothing; ([], reason)
    when it cannot be read or is not the manifest's shape (an object whose
    `exports`, when present, is an object).
    """
    manifest = skills_root / EXPORT_MANIFEST
    try:
        raw = manifest.read_bytes()
    except FileNotFoundError:
        return [], None
    except OSError as exc:
        return [], f"{EXPORT_MANIFEST} cannot be read ({exc})"
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError) as exc:  # JSON, UTF-8 or nesting errors
        return [], f"{EXPORT_MANIFEST} is not valid JSON ({exc})"
    if not isinstance(data, dict):
        return [], f"{EXPORT_MANIFEST} root is not an object"
    exports = data.get("exports")
    if exports is None:
        return [], None
    if not isinstance(exports, dict):
        return [], f"{EXPORT_MANIFEST} exports is not an object"
    return list(exports), None


def _active_link_candidates(skills_root: Path) -> list[str]:
    """The top-level folders matching `<skills-root>/*/active/*/SKILL.md`.

    `active` may be a link or a real folder. Dot names never match, as in a
    glob, and SKF's own `_batch` and `.skf-` names are skipped as the roster
    skips them.
    """
    try:
        children = list(skills_root.iterdir())
    except OSError:
        return []
    found: list[str] = []
    for child in children:
        name = child.name
        if name.startswith(".") or name == "_batch" or ".skf-" in name:
            continue
        active = child / "active"
        try:
            packages = os.listdir(active)
        except OSError:  # no `active`, not a folder, or unreadable
            continue
        for package in packages:
            if package.startswith("."):
                continue
            try:
                if stat.S_ISREG(os.stat(active / package / "SKILL.md").st_mode):
                    found.append(name)
                    break
            except OSError:
                continue
    return found


def explicit_skill_dir(skills_root: Path, entry: str) -> str | None:
    """The skill folder an --explicit entry names; None for a path outside `skills_root`.

    An entry with no `/` or `\\` is the folder name itself. Any other entry is
    a package path, absolute or relative to the current folder, that names
    the first folder of its path under `skills_root`: compared as written
    first (so `active/<name>` counts as written), then with links resolved.
    """
    if "/" not in entry and "\\" not in entry:
        return entry
    path = Path(entry.replace("\\", "/"))
    for resolve in (False, True):
        try:
            if resolve:
                parts = path.resolve().relative_to(skills_root.resolve()).parts
            else:
                parts = Path(os.path.abspath(path)).relative_to(os.path.abspath(skills_root)).parts
        except (ValueError, OSError, RuntimeError):  # outside, or a path SKF cannot resolve
            continue
        if parts:
            return parts[0]
    return None


def _excluded(skill_dir: str, reason: str, message: str) -> dict:
    return {"skill_dir": skill_dir, "reason": reason, "message": message}


def compute_candidates(skills_root: Path, explicit: list[str] | None = None) -> dict:
    """Pick the compose-mode candidates and gate them against the roster.

    `explicit` names the candidates when given; else the export manifest
    keys; else, when the manifest is absent, lists nothing or cannot be
    read, the folders holding an `active` package. A candidate is kept when
    the roster has it with skill_type single, individual or null; every
    other one is excluded with the first reason that applies, except a
    manifest key with no folder, which is a stale manifest key.
    """
    roster = enumerate_stack_skills(skills_root)
    manifest_parse_error = None
    outside: list[str] = []
    if explicit is not None:
        source, names = CANDIDATES_EXPLICIT, []
        for entry in explicit:
            skill_dir = explicit_skill_dir(skills_root, entry)
            if skill_dir is None:
                outside.append(entry)
            else:
                names.append(skill_dir)
    else:
        names, manifest_parse_error = _manifest_keys(skills_root)
        source = CANDIDATES_MANIFEST
        if not names:
            source, names = CANDIDATES_ACTIVE_LINKS, _active_link_candidates(skills_root)
    # One order for every source and platform: a Path sorts without case on
    # Windows, a name always with it.
    names = sorted(set(names))

    by_name = {entry["name"]: entry for entry in roster["skills"]}
    not_skf_output = set(roster["not_skf_output"])
    kept: list[dict] = []
    excluded: list[dict] = []
    stale: list[str] = []
    for name in names:
        entry = by_name.get(name)
        if entry is not None:
            if entry["skill_type"] in _SINGLE_SKILL_TYPES:
                kept.append(entry)
            else:
                excluded.append(_excluded(
                    name, REASON_NOT_A_SKILL,
                    f"{name}: not a skill (skill_type {entry['skill_type']}), excluding"))
            continue
        if name in not_skf_output:
            excluded.append(_excluded(name, REASON_NOT_SKF_OUTPUT, f"{name}: not SKF output, excluding"))
            continue
        named = [w for w in roster["warnings"] if w.startswith(f"{name}: ")]
        if named:
            excluded.append(_excluded(name, REASON_ROSTER_WARNING, "; ".join(named)))
            continue
        if not _has_folder(skills_root, name):
            if source == CANDIDATES_MANIFEST:
                stale.append(name)
            else:
                excluded.append(_excluded(
                    name, REASON_NO_SUCH_FOLDER, f"{name}: no such skill folder, excluding"))
            continue
        excluded.append(_excluded(name, REASON_NO_SKF_PACKAGE, f"{name}: no SKF skill package, excluding"))
    for entry in sorted(set(outside)):
        excluded.append(_excluded(
            entry, REASON_OUTSIDE_SKILLS_ROOT, f"{entry}: not inside the skills folder, excluding"))
    excluded.sort(key=lambda x: x["skill_dir"])

    return {
        "candidate_source": source,
        "kept": kept,
        "excluded": excluded,
        "stale_manifest_keys": stale,
        "manifest_parse_error": manifest_parse_error,
        "cycles": roster["cycles"],
        "warnings": roster["warnings"],
        "not_skf_output": roster["not_skf_output"],
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _read_expected_hashes(source: str) -> dict[str, str | None]:
    """Load the --expect-hashes file (`-` reads stdin). Raises ValueError or OSError."""
    if source == "-":
        return load_expected_hashes(sys.stdin.read())
    return load_expected_hashes(Path(source).read_text(encoding="utf-8"))


def _cmd_enumerate(args: argparse.Namespace) -> int:
    skills_root = Path(args.skills_root)
    if not skills_root.is_dir():
        print(
            f"error: skills root not a directory: {skills_root}",
            file=sys.stderr,
        )
        return 1
    expected = None
    if args.expect_hashes is not None:
        try:
            expected = _read_expected_hashes(args.expect_hashes)
        except (OSError, ValueError, RecursionError) as exc:
            print(f"error: --expect-hashes {args.expect_hashes}: {exc}", file=sys.stderr)
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
    if expected is not None:
        result.update(compare_hashes(result["skills"], expected))
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _parse_explicit(value: str) -> list[str]:
    """The names of a comma-separated list (--explicit, --skills, --in-scope), trimmed, empty items dropped."""
    return [name for name in (part.strip() for part in value.split(",")) if name]


def _cmd_candidates(args: argparse.Namespace) -> int:
    skills_root = Path(args.skills_root)
    if not skills_root.is_dir():
        print(
            f"error: skills root not a directory: {skills_root}",
            file=sys.stderr,
        )
        return 1
    explicit = None
    if args.explicit is not None:
        explicit = _parse_explicit(args.explicit)
        if not explicit:
            print("error: --explicit names no skill", file=sys.stderr)
            return 1
    json.dump(compute_candidates(skills_root, explicit), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _cmd_scope(args: argparse.Namespace) -> int:
    names = _parse_explicit(args.skills)
    if not names:
        print("error: --skills names no skill", file=sys.stderr)
        return 1
    json.dump(compute_scope(names, _parse_explicit(args.in_scope)), sys.stdout, indent=2)
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
    p_enum.add_argument(
        "--expect-hashes",
        metavar="FILE",
        help=(
            "additionally compare each skill's metadata_hash with FILE "
            "(an earlier enumerate result, or an object mapping each skill "
            "name to its metadata_hash; `-` reads stdin) and emit "
            "`changed_skills`, `missing_skills` and `new_skills`"
        ),
    )
    p_enum.set_defaults(func=_cmd_enumerate)

    p_cand = sub.add_parser(
        "candidates",
        help="pick the compose-mode candidates and gate them against the roster",
    )
    p_cand.add_argument(
        "skills_root",
        help="directory holding skill folders; only packages SKF generated can be kept",
    )
    p_cand.add_argument(
        "--explicit",
        metavar="NAMES",
        help=(
            "comma-separated skill folder names or package paths to gate, "
            "instead of the export manifest keys or the folders holding an "
            "`active` package; a path names its first folder under skills-root"
        ),
    )
    p_cand.set_defaults(func=_cmd_candidates)

    p_scope = sub.add_parser(
        "scope",
        help="split the unique pairs of an inventory's skills by the skills in scope",
    )
    p_scope.add_argument(
        "--skills",
        required=True,
        metavar="NAMES",
        help=(
            "comma-separated names of the inventory's skills (the `name` of "
            "each skills[] entry of an enumerate result)"
        ),
    )
    p_scope.add_argument(
        "--in-scope",
        required=True,
        metavar="NAMES",
        help=(
            "comma-separated names of the skills in scope; a name that is no "
            "inventory skill is listed in `unknown`"
        ),
    )
    p_scope.set_defaults(func=_cmd_scope)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def _force_utf8(*streams) -> None:
    """Reconfigure stdout and stderr to UTF-8, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which cannot print every character
    of the --help text, so --help would stop with UnicodeEncodeError.
    """
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


if __name__ == "__main__":
    _force_utf8(sys.stdout, sys.stderr)
    raise SystemExit(main())
