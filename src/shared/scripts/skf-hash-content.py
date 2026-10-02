# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Hash Content — SHA-256 hashing helpers for skill workflows.

Two patterns recur across the update-skill workflow's stage prose:

  1. **Single-file hash** — detect-changes.md §1b, when a candidate file is
     promoted into `brief.scope.include`, the LLM is asked to "compute SHA-256
     content hash of candidate.path" and emit a record
     `{path, heuristic, size_bytes, line_count, content_hash}` for
     `promoted_docs_new[]`. Deterministic file-read + hashlib.sha256.

  2. **Bulk-compare against provenance** — detect-changes.md §Category D,
     where the LLM is asked to "for each file_entry: compute current SHA-256
     content hash, compare against stored hash" and classify entries as
     MODIFIED_FILE / DELETED_FILE / (UNCHANGED). Same hashing primitive,
     iterated, plus a stat-and-compare. NEW_FILE detection is intentionally
     out of scope here — that lives in `skf-detect-scripts-assets.py`.

  3. **[MANUAL]-section integrity** — the update-skill workflow's headline
     Workflow Rule is "[MANUAL] sections survive regeneration with zero
     content loss." init.md §5 captures a pre-write inventory of every
     `<!-- [MANUAL:name] --> … <!-- [/MANUAL:name] -->` block; merge.md §6b,
     write.md §1 (HALT gate) and write.md §7 verify the merged SKILL.md
     against it. Doing that by an LLM marker-count + eyeball can silently
     pass a block whose interior was truncated (marker count unchanged).
     The `manual-inventory` / `manual-verify` subcommands extract each block
     by marker regex, hash its byte-exact interior, and emit an exact
     {preserved, modified, missing, moved, ok} verdict.

Subcommands:
  hash <path> [--include-path]
      Emit JSON {"content_hash": "sha256:...", "size_bytes": N, "line_count": L}
      for a single file. With --include-path, the record also includes
      "path": <as given>, so batch callers can collect records by streaming
      multiple invocations.

  compare <source-root> --provenance-map <path>
      Read `file_entries[]` from a provenance-map JSON and classify each row
      against the current source tree. Emits
        {
          "comparisons": [
            {"source_file": "...", "classification": "UNCHANGED|MODIFIED_FILE|DELETED_FILE",
             "stored_hash": "sha256:...", "current_hash": "sha256:..."|null,
             "current_size_bytes": N|null}, ...
          ],
          "stats": {"total": N, "unchanged": U, "modified": M, "deleted": D}
        }
      The provenance file must contain `file_entries` as a top-level array
      OR be the array itself (handles both schemas).

  manual-inventory <skill-md>
      Extract every `<!-- [MANUAL:name] --> … <!-- [/MANUAL:name] -->` block
      and emit
        {
          "blocks": [
            {"name": "...", "content_hash": "sha256:...",
             "byte_offset": N, "parent_heading": "..."|null}, ...
          ],
          "count": N
        }
      `content_hash` is the SHA-256 of the block's byte-exact interior (the
      bytes between the open marker's `-->` and the close marker's `<!--`,
      including surrounding newlines — zero normalization). `byte_offset` is
      the byte position of the opening marker; `parent_heading` is the text
      of the nearest preceding Markdown heading (or null). Blocks are sorted
      by `byte_offset`. Persist this JSON as the captured pre-write inventory.

  manual-verify --inventory <inventory.json> <skill-md>
      Re-extract the blocks from the (post-merge) on-disk file and classify
      each inventory block by name + hash + parent heading:
        - name present, hash matches, same parent heading  → preserved
        - name present, hash matches, parent heading changed → moved
        - name present, hash differs                        → modified
        - name absent                                       → missing
      Emits {"preserved":[names], "modified":[names], "missing":[names],
      "moved":[names], "ok": bool} where `ok = (modified empty AND missing
      empty)`. A `moved` block does NOT fail the verdict — a byte-identical
      block relocated with its logical parent section is a clean outcome.
      The inventory may be the object emitted by `manual-inventory` OR a bare
      `blocks[]` array (handles both shapes).

  manual-inventory-amend --inventory <inventory.json> --plan <plan.json>
                         --output <amended-inventory.json>
      Apply the user's [MANUAL] conflict decisions to a captured inventory,
      so the post-merge check verifies what the user approved instead of
      the pre-merge blocks. The plan is
        {"decisions": [
          {"name": "...", "action": "keep" | "remove" | "edit",
           "content_file": "<path>" | "content": "<text>"}, ...]}
      `remove` (an [R]emove or an orphan the user removed) drops every
      block of that name; `edit` (an [E]dit) rehashes the one block of that
      name from the approved interior: the bytes of `content_file` (a path
      relative to the plan's folder, or absolute), or `content` encoded as
      UTF-8, exactly the bytes the merged file holds between the markers,
      newlines included. `keep` and a block the plan does not name stay as
      captured. Writes the amended inventory ({blocks[], count}, the shape
      `manual-inventory` emits) to --output through a temporary file and a
      rename, then prints
        {"output": "...", "count": N, "removed": [names],
         "edited": [names], "kept": [names]}
      A plan with no decisions copies the inventory. A plan that names a
      block the inventory does not hold, decides one name twice, edits a
      name that several blocks share, or gives an edit no content (or both
      forms) is refused with exit 1 and nothing written.

  compare-constituent-hashes <provenance-map.json> [--skills-root <root>]
      Constituent-drift detection for compose-mode stack skills. Replaces the
      per-constituent read + SHA-256 + compare loop at
      `src/skf-audit-skill/references/constituent-freshness.md` (step 1c,
      Constituent Freshness). Reads the `constituents[]` array from a
      compose-mode provenance map (each entry carrying `skill_name`,
      `skill_path`, and the compile-time `metadata_hash`), reads each
      constituent's live `{skill_path}/active/{skill_name}/metadata.json`,
      recomputes its SHA-256 with the same `sha256:` prefix convention the
      writer used (`skf-enumerate-stack-skills._sha256_of_bytes`), and
      buckets each constituent:
        {
          "drifted":  [{"skill_name","skill_path","stored_hash","current_hash"}],
          "fresh":    [{"skill_name"}],
          "missing":  [{"skill_name","skill_path","stored_hash","reason"}],
          "skipped_null_hash": [{"skill_name"}],
          "stats": {"total":N,"drifted":N,"fresh":N,"missing":N,
                    "skipped_null_hash":N}
        }
      `drifted` is the audit's HIGH-severity constituent-drift signal (the
      live metadata.json differs from the compile-time snapshot). `missing`
      carries a `reason` (`"metadata-not-found"` when the file is absent on
      disk, `"incomplete-record"` when the provenance entry lacks
      skill_name/skill_path). `skipped_null_hash` holds constituents whose
      stored `metadata_hash` was null (recorded from a references/ cascade —
      no baseline to compare against, so never reported as drift). Relative
      `skill_path` values resolve against `--skills-root` (default: current
      directory); absolute `skill_path` values are used as-is. A provenance
      map with no `constituents` field (a single skill) yields all-empty
      buckets. Stored hashes are prefix-normalized before comparison so a
      bare-hex writer form still matches. Buckets are sorted by skill_name.

Hash format: `sha256:` prefix on a hex digest. Matches the convention used
by skf-detect-scripts-assets.py and the existing prose ("SHA-256 content
hash" — agnostic about prefix, but the prefix is the SKF convention to make
hashes self-describing for future algorithm migrations).

CLI examples:
  uv run skf-hash-content.py hash docs/AGENTS.md
  uv run skf-hash-content.py hash docs/AGENTS.md --include-path
  uv run skf-hash-content.py compare /path/to/source \\
      --provenance-map /path/to/provenance-map.json
  uv run skf-hash-content.py manual-inventory SKILL.md
  uv run skf-hash-content.py manual-verify --inventory inventory.json SKILL.md
  uv run skf-hash-content.py manual-inventory-amend --inventory inventory.json \\
      --plan manual-plan.json --output amended-inventory.json

Exit codes:
  0  — operation succeeded (including: file in compare missing on disk, its
       classification is DELETED_FILE; and manual-verify completing with
       ok=false — an integrity failure is a *result*, read from the `ok`
       field, not an operation error)
  1  — user error (bad path, malformed JSON, missing required field)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


# --------------------------------------------------------------------------
# Hashing primitives
# --------------------------------------------------------------------------


def sha256_of_file(path: Path) -> str:
    """SHA-256 of file content, with sha256: prefix."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def count_lines(path: Path) -> int:
    """Count newlines in file content; 0 if unreadable."""
    n = 0
    try:
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                n += chunk.count(b"\n")
    except OSError:
        return 0
    return n


def hash_record(path: Path, *, include_path: bool = False) -> dict:
    """Build a single-file record: content_hash + size_bytes + line_count."""
    rec: dict = {
        "content_hash": sha256_of_file(path),
        "size_bytes": path.stat().st_size,
        "line_count": count_lines(path),
    }
    if include_path:
        rec = {"path": path.as_posix(), **rec}
    return rec


_HASH_PREFIX_RE = re.compile(r"^[a-z0-9]+:")


def normalize_hash(value: str | None) -> str | None:
    """Strip a leading algorithm-name prefix (`sha256:`, `sha1:`, …) from a
    stored hash so bare-hex and prefixed forms compare equal.

    Mirrors skf-compare-file-hashes.normalize_hash. Returns None for a
    non-string input; idempotent on bare hex.
    """
    if not isinstance(value, str):
        return None
    return _HASH_PREFIX_RE.sub("", value, count=1)


# --------------------------------------------------------------------------
# Provenance comparison
# --------------------------------------------------------------------------


UNCHANGED = "UNCHANGED"
MODIFIED_FILE = "MODIFIED_FILE"
DELETED_FILE = "DELETED_FILE"


def load_file_entries(provenance_path: Path) -> list[dict]:
    """Extract the file_entries list from a provenance file.

    Accepts two shapes:
      - top-level object with a `file_entries` key (canonical)
      - top-level array of entries (already-extracted)

    Returns a copy of the list. Raises ValueError on malformed JSON or
    missing key.
    """
    try:
        data = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"failed to read provenance file {provenance_path}: {exc}") from exc

    if isinstance(data, list):
        return list(data)
    if isinstance(data, dict):
        entries = data.get("file_entries")
        if entries is None:
            raise ValueError(
                f"provenance file {provenance_path} has no `file_entries` field"
            )
        if not isinstance(entries, list):
            raise ValueError(
                f"`file_entries` in {provenance_path} is not an array"
            )
        return list(entries)
    raise ValueError(
        f"provenance file {provenance_path} must be an object or array; "
        f"got {type(data).__name__}"
    )


def classify_entry(source_root: Path, entry: dict) -> dict:
    """Classify a single file_entry against the current source tree."""
    source_file = entry.get("source_file")
    stored_hash = entry.get("content_hash")
    if not isinstance(source_file, str):
        raise ValueError(f"file_entry missing required `source_file`: {entry!r}")

    current = (source_root / source_file).resolve()
    # guard against ../.. escapes — resolved path must stay inside source_root
    try:
        current.relative_to(source_root.resolve())
    except ValueError:
        return {
            "source_file": source_file,
            "classification": DELETED_FILE,
            "stored_hash": stored_hash,
            "current_hash": None,
            "current_size_bytes": None,
        }

    if not current.is_file():
        return {
            "source_file": source_file,
            "classification": DELETED_FILE,
            "stored_hash": stored_hash,
            "current_hash": None,
            "current_size_bytes": None,
        }

    current_hash = sha256_of_file(current)
    if current_hash == stored_hash:
        classification = UNCHANGED
    else:
        classification = MODIFIED_FILE
    return {
        "source_file": source_file,
        "classification": classification,
        "stored_hash": stored_hash,
        "current_hash": current_hash,
        "current_size_bytes": current.stat().st_size,
    }


def compare(source_root: Path, provenance_path: Path) -> dict:
    entries = load_file_entries(provenance_path)
    comparisons = [classify_entry(source_root, entry) for entry in entries]
    counts = {UNCHANGED: 0, MODIFIED_FILE: 0, DELETED_FILE: 0}
    for c in comparisons:
        counts[c["classification"]] += 1
    return {
        "comparisons": comparisons,
        "stats": {
            "total": len(comparisons),
            "unchanged": counts[UNCHANGED],
            "modified": counts[MODIFIED_FILE],
            "deleted": counts[DELETED_FILE],
        },
    }


# --------------------------------------------------------------------------
# [MANUAL]-section integrity
# --------------------------------------------------------------------------


# Open marker:  <!-- [MANUAL:name] -->      (whitespace-tolerant)
# Close marker: <!-- [/MANUAL:name] -->     (note the leading slash)
# The open pattern cannot match a close marker: after `<!--` it requires
# `[MANUAL` with no slash, whereas a close has `[/MANUAL`.
_OPEN_RE = re.compile(rb"<!--\s*\[MANUAL:([^\]]+)\]\s*-->")
_CLOSE_RE = re.compile(rb"<!--\s*\[/MANUAL:([^\]]+)\]\s*-->")
_HEADING_RE = re.compile(rb"^(#{1,6})[ \t]+(.*)$")


def sha256_of_bytes(data: bytes) -> str:
    """SHA-256 of an in-memory byte string, with sha256: prefix."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _parent_heading(data: bytes, offset: int) -> str | None:
    """Text of the nearest Markdown heading preceding `offset` (or None).

    Returns the heading text with leading `#` markers and surrounding
    whitespace stripped — e.g. b"## Usage Patterns\\n" -> "Usage Patterns".
    """
    heading: str | None = None
    for line in data[:offset].split(b"\n"):
        m = _HEADING_RE.match(line)
        if m:
            heading = m.group(2).strip().decode("utf-8", errors="replace")
    return heading


def find_manual_blocks(data: bytes) -> list[dict]:
    """Extract every well-formed [MANUAL] block from `data`.

    A block is an opening `<!-- [MANUAL:name] -->` paired with the *earliest*
    following `<!-- [/MANUAL:name] -->` of the same (whitespace-stripped)
    name. `content_hash` covers the byte-exact interior — the bytes between
    the open marker's `-->` and the close marker's `<!--`, with zero
    normalization, so any interior edit (including an equal-marker-count
    truncation) changes the hash.

    An opening marker with no matching close is malformed and skipped.
    Result is sorted by `byte_offset` for deterministic ordering.
    """
    closes = [
        (m.start(), m.group(1).decode("utf-8", errors="replace").strip())
        for m in _CLOSE_RE.finditer(data)
    ]
    blocks: list[dict] = []
    for om in _OPEN_RE.finditer(data):
        name = om.group(1).decode("utf-8", errors="replace").strip()
        open_end = om.end()
        close_start = None
        for c_start, c_name in closes:
            if c_start >= open_end and c_name == name:
                if close_start is None or c_start < close_start:
                    close_start = c_start
        if close_start is None:
            continue  # unclosed opening marker — malformed, skip
        content = data[open_end:close_start]
        blocks.append({
            "name": name,
            "content_hash": sha256_of_bytes(content),
            "byte_offset": om.start(),
            "parent_heading": _parent_heading(data, om.start()),
        })
    blocks.sort(key=lambda b: b["byte_offset"])
    return blocks


def classify_manual_blocks(inv_blocks: list[dict], cur_blocks: list[dict]) -> dict:
    """Classify each inventory block against the current on-disk blocks.

    Buckets are mutually exclusive per inventory block:
      - missing:   name not present in the current file
      - modified:  name present but no current block's hash matches
      - preserved: a current block matches name + hash + parent_heading
      - moved:     a current block matches name + hash but parent_heading
                   changed (relocated with its logical section — clean)

    `ok = (modified empty AND missing empty)`; `moved` does not fail it.
    """
    from collections import defaultdict

    cur_by_name: dict[str, list[dict]] = defaultdict(list)
    for b in cur_blocks:
        cur_by_name[b["name"]].append(b)

    preserved: list[str] = []
    modified: list[str] = []
    missing: list[str] = []
    moved: list[str] = []

    for inv in inv_blocks:
        name = inv.get("name")
        candidates = cur_by_name.get(name, [])
        if not candidates:
            missing.append(name)
            continue
        hash_matches = [c for c in candidates if c["content_hash"] == inv.get("content_hash")]
        if not hash_matches:
            modified.append(name)
            continue
        if any(c.get("parent_heading") == inv.get("parent_heading") for c in hash_matches):
            preserved.append(name)
        else:
            moved.append(name)

    return {
        "preserved": preserved,
        "modified": modified,
        "missing": missing,
        "moved": moved,
        "ok": not modified and not missing,
    }


def manual_inventory(path: Path) -> dict:
    """Build the [MANUAL] inventory for a file: {blocks[], count}."""
    data = path.read_bytes()
    blocks = find_manual_blocks(data)
    return {"blocks": blocks, "count": len(blocks)}


def load_inventory_blocks(inventory_path: Path) -> list[dict]:
    """Read the blocks[] list from a manual-inventory JSON file.

    Accepts the object emitted by `manual_inventory` (has a `blocks` key)
    OR a bare list of block records. Raises ValueError on malformed input.
    """
    try:
        data = json.loads(inventory_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(
            f"failed to read inventory file {inventory_path}: {exc}"
        ) from exc
    if isinstance(data, list):
        return list(data)
    if isinstance(data, dict):
        blocks = data.get("blocks")
        if blocks is None:
            raise ValueError(
                f"inventory file {inventory_path} has no `blocks` field"
            )
        if not isinstance(blocks, list):
            raise ValueError(
                f"`blocks` in {inventory_path} is not an array"
            )
        return list(blocks)
    raise ValueError(
        f"inventory file {inventory_path} must be an object or array; "
        f"got {type(data).__name__}"
    )


def manual_verify(inventory_path: Path, skill_md_path: Path) -> dict:
    """Verify a post-merge file against a captured [MANUAL] inventory."""
    inv_blocks = load_inventory_blocks(inventory_path)
    cur_blocks = find_manual_blocks(skill_md_path.read_bytes())
    return classify_manual_blocks(inv_blocks, cur_blocks)


_PLAN_ACTIONS = ("keep", "remove", "edit")


def _load_plan(plan_path: Path) -> list[dict]:
    """The decisions[] of a manual plan. Raises ValueError on malformed input."""
    try:
        data = json.loads(plan_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"failed to read plan file {plan_path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("decisions"), list):
        raise ValueError(f"plan file {plan_path} must be an object with a `decisions` array")
    decisions = data["decisions"]
    for d in decisions:
        if not isinstance(d, dict) or not isinstance(d.get("name"), str) or not d["name"].strip():
            raise ValueError(f"every decision in {plan_path} needs a non-empty `name`: {d!r}")
        if d.get("action") not in _PLAN_ACTIONS:
            raise ValueError(f"decision for {d['name']!r}: `action` must be one of "
                             f"{', '.join(_PLAN_ACTIONS)}, got {d.get('action')!r}")
    return decisions


def _edited_interior(decision: dict, plan_dir: Path) -> bytes:
    """The approved interior bytes of an `edit` decision."""
    has_file, has_text = "content_file" in decision, "content" in decision
    if has_file == has_text:
        raise ValueError(f"edit of {decision['name']!r} needs exactly one of `content_file` and `content`")
    if has_text:
        if not isinstance(decision["content"], str):
            raise ValueError(f"edit of {decision['name']!r}: `content` must be a string")
        return decision["content"].encode("utf-8")
    raw = decision["content_file"]
    if not isinstance(raw, str) or not raw:
        raise ValueError(f"edit of {decision['name']!r}: `content_file` must be a path")
    path = Path(raw)
    if not path.is_absolute():
        path = plan_dir / path
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ValueError(f"edit of {decision['name']!r}: cannot read {path}: {exc}") from exc


def amend_inventory(inv_blocks: list[dict], decisions: list[dict], plan_dir: Path) -> tuple[list[dict], dict]:
    """The inventory blocks with the plan's decisions applied, and what changed.

    Pure apart from reading each edit's content file. Raises ValueError for
    a plan the inventory cannot take (see the module docstring).
    """
    names = [b.get("name") for b in inv_blocks]
    seen: set[str] = set()
    by_name: dict[str, dict] = {}
    for d in decisions:
        name = d["name"]
        if name in seen:
            raise ValueError(f"the plan decides {name!r} twice")
        seen.add(name)
        if name not in names:
            raise ValueError(f"the plan names {name!r}, which the inventory does not hold")
        if d["action"] == "edit" and names.count(name) > 1:
            raise ValueError(f"the plan edits {name!r}, which {names.count(name)} blocks share")
        by_name[name] = d
    out: list[dict] = []
    for block in inv_blocks:
        decision = by_name.get(block.get("name"))
        if decision is None or decision["action"] == "keep":
            out.append(dict(block))
        elif decision["action"] == "edit":
            out.append({**block, "content_hash": sha256_of_bytes(_edited_interior(decision, plan_dir))})
    changes = {action: [d["name"] for d in decisions if d["action"] == key]
               for action, key in (("removed", "remove"), ("edited", "edit"), ("kept", "keep"))}
    return out, changes


def _write_atomic(path: Path, text: str) -> None:
    """Write `text` to `path` through a temporary file and one rename."""
    tmp = path.with_name(f".{path.name}.skf-tmp")
    try:
        tmp.write_bytes(text.encode("utf-8"))
        tmp.replace(path)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def manual_inventory_amend(inventory_path: Path, plan_path: Path, output_path: Path) -> dict:
    """Write the amended inventory to `output_path` and return the summary."""
    inv_blocks = load_inventory_blocks(inventory_path)
    decisions = _load_plan(plan_path)
    blocks, changes = amend_inventory(inv_blocks, decisions, plan_path.parent)
    _write_atomic(output_path, json.dumps({"blocks": blocks, "count": len(blocks)}, indent=2) + "\n")
    return {"output": output_path.as_posix(), "count": len(blocks), **changes}


# --------------------------------------------------------------------------
# Constituent-hash comparison (compose-mode stack drift)
# --------------------------------------------------------------------------


def load_constituents(provenance_path: Path) -> list[dict]:
    """Extract the `constituents[]` list from a compose-mode provenance map.

    Accepts three shapes:
      - top-level object with a `constituents` key (canonical provenance map)
      - top-level object with NO `constituents` field → empty list (a single
        skill omits the array entirely per skill-sections.md — valid, no drift)
      - top-level array of constituent records (already extracted)

    Raises ValueError on read failure, malformed JSON, or a non-array
    `constituents` field.
    """
    try:
        text = provenance_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            f"failed to read provenance file {provenance_path}: {exc}"
        ) from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"malformed JSON in provenance file {provenance_path}: {exc}"
        ) from exc

    if isinstance(data, list):
        return list(data)
    if isinstance(data, dict):
        constituents = data.get("constituents")
        if constituents is None:
            return []  # single skill — no constituents to verify
        if not isinstance(constituents, list):
            raise ValueError(
                f"`constituents` in {provenance_path} is not an array"
            )
        return list(constituents)
    raise ValueError(
        f"provenance file {provenance_path} must be an object or array; "
        f"got {type(data).__name__}"
    )


def _constituent_metadata_path(skills_root: Path, skill_path: str, skill_name: str) -> Path:
    """Resolve a constituent's live metadata.json path.

    Mirrors the by-hand fallback of constituent-freshness.md (audit-skill
    step 1c):
    `{skill_path}/active/{skill_name}/metadata.json`. A relative `skill_path`
    resolves against `skills_root`; an absolute one is used as-is.
    """
    base = Path(skill_path)
    if not base.is_absolute():
        base = skills_root / base
    return base / "active" / skill_name / "metadata.json"


def compare_constituents(provenance_path: Path, skills_root: Path) -> dict:
    """Classify each compose-mode constituent as drifted / fresh / missing.

    For each constituent, the live `metadata.json` is re-hashed with the same
    `sha256:`-prefixed convention the writer used and compared (prefix-
    normalized) against the compile-time `metadata_hash`.
    """
    constituents = load_constituents(provenance_path)

    drifted: list[dict] = []
    fresh: list[dict] = []
    missing: list[dict] = []
    skipped_null_hash: list[dict] = []

    for entry in constituents:
        if not isinstance(entry, dict):
            missing.append({
                "skill_name": None,
                "skill_path": None,
                "stored_hash": None,
                "reason": "incomplete-record",
            })
            continue
        skill_name = entry.get("skill_name")
        skill_path = entry.get("skill_path")
        stored_hash = entry.get("metadata_hash")

        if not isinstance(skill_name, str) or not skill_name or \
                not isinstance(skill_path, str) or not skill_path:
            missing.append({
                "skill_name": skill_name if isinstance(skill_name, str) else None,
                "skill_path": skill_path if isinstance(skill_path, str) else None,
                "stored_hash": stored_hash if isinstance(stored_hash, str) else None,
                "reason": "incomplete-record",
            })
            continue

        if not isinstance(stored_hash, str) or not stored_hash:
            # No compile-time baseline (recorded from a references/ cascade) —
            # cannot be drift; do not flag.
            skipped_null_hash.append({"skill_name": skill_name})
            continue

        meta_path = _constituent_metadata_path(skills_root, skill_path, skill_name)
        if not meta_path.is_file():
            missing.append({
                "skill_name": skill_name,
                "skill_path": skill_path,
                "stored_hash": stored_hash,
                "reason": "metadata-not-found",
            })
            continue

        current_hash = sha256_of_file(meta_path)
        if normalize_hash(stored_hash) == normalize_hash(current_hash):
            fresh.append({"skill_name": skill_name})
        else:
            drifted.append({
                "skill_name": skill_name,
                "skill_path": skill_path,
                "stored_hash": stored_hash,
                "current_hash": current_hash,
            })

    drifted.sort(key=lambda r: (r.get("skill_name") or ""))
    fresh.sort(key=lambda r: (r.get("skill_name") or ""))
    missing.sort(key=lambda r: (r.get("skill_name") or ""))
    skipped_null_hash.sort(key=lambda r: (r.get("skill_name") or ""))

    return {
        "drifted": drifted,
        "fresh": fresh,
        "missing": missing,
        "skipped_null_hash": skipped_null_hash,
        "stats": {
            "total": len(constituents),
            "drifted": len(drifted),
            "fresh": len(fresh),
            "missing": len(missing),
            "skipped_null_hash": len(skipped_null_hash),
        },
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_hash(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.is_file():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1
    rec = hash_record(path, include_path=args.include_path)
    json.dump(rec, sys.stdout)
    sys.stdout.write("\n")
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    source_root = Path(args.source_root)
    provenance = Path(args.provenance_map)
    if not source_root.is_dir():
        print(f"error: source root not a directory: {source_root}", file=sys.stderr)
        return 1
    if not provenance.is_file():
        print(f"error: provenance map not found: {provenance}", file=sys.stderr)
        return 1
    try:
        result = compare(source_root, provenance)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _cmd_manual_inventory(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.is_file():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1
    result = manual_inventory(path)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _cmd_manual_verify(args: argparse.Namespace) -> int:
    path = Path(args.path)
    inventory = Path(args.inventory)
    if not path.is_file():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1
    if not inventory.is_file():
        print(f"error: inventory not found: {inventory}", file=sys.stderr)
        return 1
    try:
        result = manual_verify(inventory, path)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _cmd_manual_inventory_amend(args: argparse.Namespace) -> int:
    inventory, plan, output = Path(args.inventory), Path(args.plan), Path(args.output)
    for label, path in (("inventory", inventory), ("plan", plan)):
        if not path.is_file():
            print(f"error: {label} not found: {path}", file=sys.stderr)
            return 1
    if not output.parent.is_dir():
        print(f"error: output folder not found: {output.parent}", file=sys.stderr)
        return 1
    try:
        result = manual_inventory_amend(inventory, plan, output)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: cannot write {output}: {exc}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _cmd_compare_constituents(args: argparse.Namespace) -> int:
    provenance = Path(args.provenance_map)
    skills_root = Path(args.skills_root)
    if not provenance.is_file():
        print(f"error: provenance map not found: {provenance}", file=sys.stderr)
        return 1
    if not skills_root.is_dir():
        print(f"error: skills root not a directory: {skills_root}", file=sys.stderr)
        return 1
    try:
        result = compare_constituents(provenance, skills_root)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-hash-content",
        description="SHA-256 hashing helpers: single-file record or bulk-compare against provenance.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_hash = sub.add_parser("hash", help="emit hash record for a single file")
    p_hash.add_argument("path", help="path to the file")
    p_hash.add_argument(
        "--include-path",
        action="store_true",
        help="include the path string in the emitted record",
    )
    p_hash.set_defaults(func=_cmd_hash)

    p_cmp = sub.add_parser(
        "compare",
        help="classify provenance file_entries[] against current source tree",
    )
    p_cmp.add_argument("source_root", help="path to the source tree root")
    p_cmp.add_argument(
        "--provenance-map",
        required=True,
        help="path to provenance-map.json (object with file_entries[] or bare array)",
    )
    p_cmp.set_defaults(func=_cmd_compare)

    p_inv = sub.add_parser(
        "manual-inventory",
        help="extract [MANUAL] blocks and emit {blocks[], count} JSON",
    )
    p_inv.add_argument("path", help="path to the SKILL.md (or reference file)")
    p_inv.set_defaults(func=_cmd_manual_inventory)

    p_ver = sub.add_parser(
        "manual-verify",
        help="verify a file against a captured [MANUAL] inventory",
    )
    p_ver.add_argument("path", help="path to the post-merge SKILL.md (or reference file)")
    p_ver.add_argument(
        "--inventory",
        required=True,
        help="path to the manual-inventory JSON captured before the write",
    )
    p_ver.set_defaults(func=_cmd_manual_verify)

    p_amend = sub.add_parser(
        "manual-inventory-amend",
        help="apply the user's [MANUAL] remove and edit decisions to a captured inventory",
    )
    p_amend.add_argument("--inventory", required=True, help="the manual-inventory JSON captured before the merge")
    p_amend.add_argument("--plan", required=True, help="the plan JSON holding the user's decisions")
    p_amend.add_argument("--output", required=True, help="where to write the amended inventory JSON")
    p_amend.set_defaults(func=_cmd_manual_inventory_amend)

    p_con = sub.add_parser(
        "compare-constituent-hashes",
        help="classify compose-mode stack constituents as drifted/fresh/missing",
    )
    p_con.add_argument(
        "provenance_map",
        help="path to the compose-mode provenance-map.json (object with constituents[] or bare array)",
    )
    p_con.add_argument(
        "--skills-root",
        default=".",
        help="base directory for resolving relative constituent skill_path values (default: current directory)",
    )
    p_con.set_defaults(func=_cmd_compare_constituents)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
