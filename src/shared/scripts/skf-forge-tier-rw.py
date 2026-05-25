# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""SKF Forge Tier RW — Read/write primitives for forger-sidecar YAML files.

Replaces the prose-driven YAML emission in `src/skf-setup/references/
write-config.md` §1-§3 (and the prose-driven cleanup logic in
step 3 §5/§5b) with one Python invocation. The script is the source
of truth for the on-disk forge-tier.yaml schema (matching the
canonical template at write-config.md:24-58) and guarantees
that registry arrays are PRESERVED across rewrites — losing
`qmd_collections` or `ccc_index_registry` would break every
downstream skill (skf-create-skill, skf-audit-skill, skf-update-skill,
skf-brief-skill) that reads them.

Subcommands:

  read          Read forge-tier.yaml and emit the parsed structure as JSON
                on stdout. Missing-file is not an error — emits null
                payload with status=ok so first-run callers can branch.

  write-tools   Write a fresh forge-tier.yaml from a JSON context payload
                on stdin. Preserves `qmd_collections`,
                `ccc_index_registry`, and the user-customizable
                `ccc_index.staleness_threshold_hours` from the existing
                file (if any) by reading it first, then merging.

  init-prefs    Create preferences.yaml with first-run defaults IF it
                does not exist. Idempotent — refuses to overwrite an
                existing file (preserves user customization).

  register-qmd-collection
                Append-or-replace a single entry in the `qmd_collections`
                array. Reads the entry as JSON on stdin (must include
                `name`; `name` is the upsert key — existing entry with
                the same `name` is replaced, otherwise appended). All
                other forge-tier state (tools / tier / ccc_index /
                ccc_index_registry / other qmd_collections entries) is
                preserved verbatim. Used by skf-brief-skill step 5 §5
                and skf-create-skill to register Deep-tier QMD
                collections without re-rendering the whole file in
                prose.

  register-ccc-index
                Append-or-replace a single entry in the
                `ccc_index_registry` array. Reads the entry as JSON on
                stdin (must include `source_repo` and `skill_name`;
                composite key `source_repo`+`skill_name` is the upsert
                key — existing entry with the same composite key is
                replaced, otherwise appended). All other forge-tier
                state is preserved verbatim. Used by skf-create-skill
                §6b to register CCC-indexed source paths without
                re-rendering the whole file in prose.

  clean-stale   Two cleanup operations gated by flags:
                  --qmd-live-names a,b,c — remove qmd_collections
                    entries whose `name` is not in the comma-separated
                    live-names list. Caller computes liveness via
                    `qmd collection list` (or skf-qmd-classify-
                    collections.py once that ships in PR B).
                  --prune-missing-ccc-paths — remove ccc_index_registry
                    entries whose `path` no longer exists on disk.
                Both flags can be passed in the same invocation.

Output schema (the read subcommand and the response from every write):

  {"status": "ok", "version": "v1", ...subcommand-specific fields...}

Errors emit `{"status": "error", "message": "..."}` to stderr and
exit non-zero (1 for user error, 2 for I/O failure).

Cross-platform: pure stdlib + PyYAML. Atomic writes via temp + rename
mirror skf-atomic-write.py's pattern. Concurrent access requires
external `flock` coordination — see step 7 of skf-create-skill for
the precedent.

CLI — invoke via `uv run` so the PEP 723 PyYAML dependency declared
above is auto-resolved on first call and cached. `docs/getting-started.md`
documents uv as the runtime prerequisite for exactly this. Bare
`python3` will fail with `ModuleNotFoundError: No module named 'yaml'`
on a fresh interpreter where pyyaml has not been pip-installed
system-wide:

  uv run skf-forge-tier-rw.py read --target /path/forge-tier.yaml
  echo '{...}' | uv run skf-forge-tier-rw.py write-tools --target /path/forge-tier.yaml
  uv run skf-forge-tier-rw.py init-prefs --target /path/preferences.yaml
  echo '{...}' | uv run skf-forge-tier-rw.py register-ccc-index --target /path/forge-tier.yaml
  uv run skf-forge-tier-rw.py clean-stale --target /path/forge-tier.yaml \\
      --qmd-live-names foo-brief,bar-extraction --prune-missing-ccc-paths
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


DEFAULT_STALENESS_HOURS = 24
PREFERENCES_TEMPLATE = """# Ferris Sidecar: User Preferences
# Created by setup workflow on first run
# Edit this file to customize Ferris behavior

# Override detected tier (set to Quick, Forge, Forge+, or Deep to force a tier)
tier_override: ~

# Passive context injection (set to false to skip snippet generation and CLAUDE.md updates during export)
passive_context: true

# Headless mode (set to true to skip confirmation gates in all workflows)
headless_mode: false

# Compact greeting (set to true to skip the full capabilities table on session start)
compact_greeting: false

# Reserved for future use — these fields are not yet consumed by any workflow step
# output_language: ~
# skill_format_version: ~
# citation_style: ~
# confidence_display: ~
"""


def _die(code: int, message: str) -> None:
    print(json.dumps({"status": "error", "message": message}), file=sys.stderr)
    sys.exit(code)


def _ok(payload: dict) -> None:
    payload.setdefault("status", "ok")
    payload.setdefault("version", "v1")
    print(json.dumps(payload, default=str))


def _read_yaml(path: Path) -> dict | None:
    """Return parsed YAML as dict, or None if file missing. Raises on parse error."""
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        _die(2, f"failed to parse {path}: {e}")
    if data is None:
        return {}
    if not isinstance(data, dict):
        _die(2, f"expected mapping at top of {path}, got {type(data).__name__}")
    return data


def _atomic_write(target: Path, content: str) -> None:
    """Crash-safe write via temp + fsync + rename. Mirrors skf-atomic-write.py."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".skf-tmp")
    # O_BINARY (Windows only; 0 elsewhere) suppresses the text-mode \n -> \r\n
    # translation that would otherwise corrupt verbatim writes on Windows.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(tmp, flags, 0o644)
        try:
            os.write(fd, content.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, target)
    except OSError as e:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        _die(2, f"atomic write failed for {target}: {e}")


def _yaml_block(value, indent: int = 0) -> str:
    """Dump a value as a YAML fragment, indented by `indent` spaces, no trailing newline."""
    text = yaml.safe_dump(value, default_flow_style=False, sort_keys=False, allow_unicode=True)
    text = text.rstrip("\n")
    if indent == 0:
        return text
    pad = " " * indent
    return "\n".join(pad + line if line else line for line in text.split("\n"))


def render_forge_tier_yaml(payload: dict) -> str:
    """Render the canonical forge-tier.yaml from a context payload.

    Preserves the human-readable section comments from the template at
    write-config.md:24-58. Sections are emitted in a fixed order
    so re-runs against unchanged inputs produce byte-identical output.
    """
    tools = payload["tools"]
    tier = payload["tier"]
    tier_detected_at = payload["tier_detected_at"]
    ccc_index = payload["ccc_index"]
    ccc_index_registry = payload.get("ccc_index_registry", [])
    qmd_collections = payload.get("qmd_collections", [])

    # Render `tools` block in the canonical key order (matches step 2 template).
    tools_ordered = {
        "ast_grep": tools["ast_grep"],
        "gh_cli": tools["gh_cli"],
        "qmd": tools["qmd"],
        "ccc": tools["ccc"],
        "ccc_daemon": tools.get("ccc_daemon"),
        "security_scan": tools.get("security_scan", False),
    }

    # ccc_index keys in canonical order.
    ccc_ordered = {
        "indexed_path": ccc_index.get("indexed_path"),
        "last_indexed": ccc_index.get("last_indexed"),
        "status": ccc_index.get("status"),
        "staleness_threshold_hours": ccc_index.get("staleness_threshold_hours", DEFAULT_STALENESS_HOURS),
        "file_count": ccc_index.get("file_count"),
        "exclude_patterns": ccc_index.get("exclude_patterns", []),
    }

    parts = [
        "# Ferris Sidecar: Forge Tier State",
        "# Written by setup workflow",
        "",
        "# Tool availability (detected during [SF] Setup Forge)",
        _yaml_block({"tools": tools_ordered}),
        "",
        "# Capability tier (derived from tool availability)",
        "# Quick = no tools | Forge = + ast-grep | Forge+ = + ast-grep + ccc | Deep = + ast-grep + gh + QMD",
        f"tier: {tier}",
        f"tier_detected_at: {_yaml_scalar(tier_detected_at)}",
        "",
        "# CCC semantic index state (managed by setup step 1b and extraction workflows)",
        _yaml_block({"ccc_index": ccc_ordered}),
        "",
        "# CCC index registry (tracks which source paths have been indexed for skill workflows)",
        "# PRESERVE existing entries on re-runs",
        _yaml_block({"ccc_index_registry": ccc_index_registry}),
        "",
        "# QMD collection registry (populated by create-skill, consumed by audit/update-skill)",
        "# PRESERVE existing entries on re-runs",
        _yaml_block({"qmd_collections": qmd_collections}),
        "",
    ]
    return "\n".join(parts)


def _yaml_scalar(value) -> str:
    """Render a scalar value using YAML's own quoting rules so timestamps, booleans, etc. round-trip."""
    return yaml.safe_dump(value, default_flow_style=False).rstrip("\n").rstrip("...").rstrip()


def _merge_preserved_fields(payload: dict, existing: dict | None) -> dict:
    """Inject preserved fields from the existing file into the new payload.

    Three preservation rules (per step 2 §1 "Note on re-runs"):
    - `qmd_collections` array — preserved entirely from existing.
    - `ccc_index_registry` array — preserved entirely from existing.
    - `ccc_index.staleness_threshold_hours` scalar — preserved if user set
      a non-default value; else uses payload value or DEFAULT.
    Note: `ccc_index.exclude_patterns` is NOT preserved (rewritten fresh
    by step 1b on every run, per the explicit step 2 contract).
    """
    if existing is None:
        return payload

    payload.setdefault("qmd_collections", existing.get("qmd_collections", []))
    payload.setdefault("ccc_index_registry", existing.get("ccc_index_registry", []))

    payload.setdefault("ccc_index", {})
    existing_ccc = existing.get("ccc_index", {}) or {}
    if "staleness_threshold_hours" not in payload["ccc_index"]:
        payload["ccc_index"]["staleness_threshold_hours"] = existing_ccc.get(
            "staleness_threshold_hours", DEFAULT_STALENESS_HOURS
        )
    return payload


# ─── Subcommands ─────────────────────────────────────────────────────────────


def cmd_read(target: Path) -> None:
    data = _read_yaml(target)
    if data is None:
        _ok({"exists": False, "data": None})
        return
    _ok({"exists": True, "data": data})


def cmd_write_tools(target: Path) -> None:
    raw = sys.stdin.read()
    if not raw.strip():
        _die(1, "write-tools: empty stdin (expected JSON payload)")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        _die(1, f"write-tools: invalid JSON on stdin: {e}")

    required = {"tools", "tier", "ccc_index"}
    missing = required - set(payload.keys())
    if missing:
        _die(1, f"write-tools: payload missing required keys: {sorted(missing)}")

    payload.setdefault("tier_detected_at", datetime.now(timezone.utc).isoformat())

    existing = _read_yaml(target)
    payload = _merge_preserved_fields(payload, existing)

    rendered = render_forge_tier_yaml(payload)
    _atomic_write(target, rendered)
    _ok({
        "wrote": str(target),
        "preserved_arrays": {
            "qmd_collections": len(payload.get("qmd_collections", [])),
            "ccc_index_registry": len(payload.get("ccc_index_registry", [])),
        },
        "tier": payload["tier"],
    })


def cmd_init_prefs(target: Path) -> None:
    if target.exists():
        _ok({"exists": True, "wrote": False, "path": str(target)})
        return
    _atomic_write(target, PREFERENCES_TEMPLATE)
    _ok({"exists": True, "wrote": True, "path": str(target), "first_run": True})


def cmd_register_qmd_collection(target: Path) -> None:
    # Note: render_forge_tier_yaml() emits exactly the six known top-level
    # sections (tools, tier, tier_detected_at, ccc_index, ccc_index_registry,
    # qmd_collections). If a future schema revision adds a new top-level key,
    # this subcommand will silently drop it — same limitation that already
    # affects cmd_write_tools and cmd_clean_stale. Update render_forge_tier_yaml()
    # AND those three subcommands together when the schema grows.
    raw = sys.stdin.read()
    if not raw.strip():
        _die(1, "register-qmd-collection: empty stdin (expected JSON entry)")
    try:
        entry = json.loads(raw)
    except json.JSONDecodeError as e:
        _die(1, f"register-qmd-collection: invalid JSON on stdin: {e}")

    if not isinstance(entry, dict):
        _die(1, "register-qmd-collection: entry must be a JSON object")
    name = entry.get("name")
    if not name or not isinstance(name, str):
        _die(1, "register-qmd-collection: entry must include a non-empty 'name' string")

    data = _read_yaml(target)
    if data is None:
        _die(1, f"register-qmd-collection: target does not exist: {target}. "
                f"Run setup workflow first to create forge-tier.yaml.")

    collections = list(data.get("qmd_collections") or [])
    replaced = False
    for i, existing in enumerate(collections):
        if isinstance(existing, dict) and existing.get("name") == name:
            collections[i] = entry
            replaced = True
            break
    if not replaced:
        collections.append(entry)

    payload = {
        "tools": data.get("tools", {}),
        "tier": data.get("tier", "Quick"),
        "tier_detected_at": data.get("tier_detected_at",
                                     datetime.now(timezone.utc).isoformat()),
        "ccc_index": data.get("ccc_index", {}),
        "ccc_index_registry": data.get("ccc_index_registry", []),
        "qmd_collections": collections,
    }
    rendered = render_forge_tier_yaml(payload)
    _atomic_write(target, rendered)
    _ok({
        "name": name,
        "action": "replaced" if replaced else "appended",
        "qmd_collections_count": len(collections),
        "wrote": str(target),
    })


def cmd_register_ccc_index(target: Path) -> None:
    raw = sys.stdin.read()
    if not raw.strip():
        _die(1, "register-ccc-index: empty stdin (expected JSON entry)")
    try:
        entry = json.loads(raw)
    except json.JSONDecodeError as e:
        _die(1, f"register-ccc-index: invalid JSON on stdin: {e}")

    if not isinstance(entry, dict):
        _die(1, "register-ccc-index: entry must be a JSON object")
    source_repo = entry.get("source_repo")
    skill_name = entry.get("skill_name")
    if not source_repo or not isinstance(source_repo, str):
        _die(1, "register-ccc-index: entry must include a non-empty 'source_repo' string")
    if not skill_name or not isinstance(skill_name, str):
        _die(1, "register-ccc-index: entry must include a non-empty 'skill_name' string")

    data = _read_yaml(target)
    if data is None:
        _die(1, f"register-ccc-index: target does not exist: {target}. "
                f"Run setup workflow first to create forge-tier.yaml.")

    registry = list(data.get("ccc_index_registry") or [])
    replaced = False
    for i, existing in enumerate(registry):
        if (isinstance(existing, dict)
                and existing.get("source_repo") == source_repo
                and existing.get("skill_name") == skill_name):
            registry[i] = entry
            replaced = True
            break
    if not replaced:
        registry.append(entry)

    payload = {
        "tools": data.get("tools", {}),
        "tier": data.get("tier", "Quick"),
        "tier_detected_at": data.get("tier_detected_at",
                                     datetime.now(timezone.utc).isoformat()),
        "ccc_index": data.get("ccc_index", {}),
        "ccc_index_registry": registry,
        "qmd_collections": data.get("qmd_collections", []),
    }
    rendered = render_forge_tier_yaml(payload)
    _atomic_write(target, rendered)
    _ok({
        "source_repo": source_repo,
        "skill_name": skill_name,
        "action": "replaced" if replaced else "appended",
        "ccc_index_registry_count": len(registry),
        "wrote": str(target),
    })


def cmd_clean_stale(target: Path, qmd_live_names: list[str] | None,
                    prune_missing_ccc_paths: bool) -> None:
    data = _read_yaml(target)
    if data is None:
        _die(1, f"clean-stale: target does not exist: {target}")

    qmd_removed: list[str] = []
    ccc_removed: list[str] = []

    if qmd_live_names is not None:
        live_set = set(qmd_live_names)
        kept = []
        for entry in data.get("qmd_collections", []) or []:
            if not isinstance(entry, dict):
                kept.append(entry)
                continue
            name = entry.get("name")
            if name in live_set:
                kept.append(entry)
            else:
                qmd_removed.append(str(name))
        data["qmd_collections"] = kept

    if prune_missing_ccc_paths:
        kept = []
        for entry in data.get("ccc_index_registry", []) or []:
            if not isinstance(entry, dict):
                kept.append(entry)
                continue
            entry_path = entry.get("path")
            if entry_path and Path(entry_path).exists():
                kept.append(entry)
            else:
                ccc_removed.append(str(entry_path))
        data["ccc_index_registry"] = kept

    if not qmd_removed and not ccc_removed:
        _ok({"qmd_removed": [], "ccc_removed": [], "wrote": False})
        return

    # Round-trip through render to preserve the canonical format.
    # Existing data already contains the full state; render needs the same shape.
    payload = {
        "tools": data.get("tools", {}),
        "tier": data.get("tier", "Quick"),
        "tier_detected_at": data.get("tier_detected_at",
                                     datetime.now(timezone.utc).isoformat()),
        "ccc_index": data.get("ccc_index", {}),
        "ccc_index_registry": data.get("ccc_index_registry", []),
        "qmd_collections": data.get("qmd_collections", []),
    }
    rendered = render_forge_tier_yaml(payload)
    _atomic_write(target, rendered)
    _ok({
        "qmd_removed": qmd_removed,
        "ccc_removed": ccc_removed,
        "wrote": True,
    })


# ─── CLI ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read/write primitives for forger-sidecar YAML files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_read = sub.add_parser("read", help="Read a forge-tier.yaml and emit JSON")
    p_read.add_argument("--target", type=Path, required=True)

    p_write = sub.add_parser("write-tools",
                             help="Write a fresh forge-tier.yaml from a JSON payload on stdin")
    p_write.add_argument("--target", type=Path, required=True)

    p_init = sub.add_parser("init-prefs",
                            help="Create preferences.yaml with first-run defaults if missing")
    p_init.add_argument("--target", type=Path, required=True)

    p_clean = sub.add_parser("clean-stale",
                             help="Remove stale qmd_collections / ccc_index_registry entries")
    p_clean.add_argument("--target", type=Path, required=True)
    p_clean.add_argument("--qmd-live-names", default=None,
                         help="Comma-separated list of currently-live QMD collection names. "
                              "Entries in qmd_collections whose name is NOT in this list are removed. "
                              "Omit the flag entirely to skip QMD cleanup.")
    p_clean.add_argument("--prune-missing-ccc-paths", action="store_true",
                         help="Remove ccc_index_registry entries whose path no longer exists.")

    p_register = sub.add_parser("register-qmd-collection",
                                help="Append-or-replace a single qmd_collections entry by name")
    p_register.add_argument("--target", type=Path, required=True)

    p_ccc = sub.add_parser("register-ccc-index",
                           help="Append-or-replace a single ccc_index_registry entry by source_repo+skill_name")
    p_ccc.add_argument("--target", type=Path, required=True)

    args = parser.parse_args()

    if args.cmd == "read":
        cmd_read(args.target)
    elif args.cmd == "write-tools":
        cmd_write_tools(args.target)
    elif args.cmd == "init-prefs":
        cmd_init_prefs(args.target)
    elif args.cmd == "clean-stale":
        live = None
        if args.qmd_live_names is not None:
            live = [n.strip() for n in args.qmd_live_names.split(",") if n.strip()]
        cmd_clean_stale(args.target, live, args.prune_missing_ccc_paths)
    elif args.cmd == "register-qmd-collection":
        cmd_register_qmd_collection(args.target)
    elif args.cmd == "register-ccc-index":
        cmd_register_ccc_index(args.target)


if __name__ == "__main__":
    main()
