# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""SKF Forge Tier RW — Read/write primitives for forger-sidecar YAML files.

Replaces the prose-driven YAML emission in `src/skf-setup/references/
write-config.md` §1 (and the prose-driven cleanup logic in
step 3 §4) with one Python invocation. The script is the source
of truth for the on-disk forge-tier.yaml schema (the canonical
template is render_forge_tier_yaml below) and guarantees
that registry arrays are PRESERVED across rewrites — losing
`qmd_collections` or `ccc_index_registry` would break every
downstream skill (skf-create-skill, skf-audit-skill, skf-update-skill,
skf-brief-skill) that reads them.

Subcommands:

  read          Read forge-tier.yaml and emit the parsed structure as JSON
                on stdout. Missing-file is not an error — emits null
                payload with status=ok so first-run callers can branch.

  write-tools   Write a fresh forge-tier.yaml from a JSON context payload
                on stdin, or, with --detect-from, from the outputs a
                setup run staged in its run folder (below). Preserves
                `qmd_collections`, `ccc_index_registry`, and the
                user-customizable `ccc_index.staleness_threshold_hours`
                from the existing file (if any) by reading it first, then
                merging, and `ccc_index.exclude_patterns` when the payload
                sends null (the SKF exclusion record kept across runs that
                did not reconcile it).

                --detect-from <detect-tools.json>
                    skf-detect-tools.py's output: `tools` (each tool's
                    `available`, ccc's `daemon`) and `tier.calculated`.
                --ccc-from <ccc-exclusions.json>
                    skf-merge-ccc-exclusions.py's --result-to file, run
                    with --build-index: its `index` object (status,
                    indexed_path, last_indexed, file_count) and its
                    `effective_patterns` become `ccc_index`. A file that
                    is not there means the run did not prepare ccc
                    (status "none"), unless detect-tools.json reports
                    ccc available: the helper then wrote no result, so
                    the preparation failed (status "failed"), as with a
                    file that holds an error, or no JSON object.
                    Either way the exclusion record is kept.
                With --detect-from the subcommand reads nothing on stdin,
                so no value passes through the caller's hands.

  register-qmd-collection
                Append-or-replace a single entry in the `qmd_collections`
                array. Reads the entry as JSON on stdin (must include
                `name`; `name` is the upsert key — existing entry with
                the same `name` is replaced, otherwise appended). All
                other forge-tier state (tools / tier / ccc_index /
                ccc_index_registry / other qmd_collections entries) is
                preserved verbatim. Used by skf-brief-skill step 5 §3b
                and skf-create-skill to register Deep-tier QMD
                collections without re-rendering the whole file in
                prose.

  remove-qmd-collection
                Remove every `qmd_collections` entry whose `name` is
                --name. All other forge-tier state is preserved verbatim.
                The rollback of register-qmd-collection, for a caller
                whose `qmd collection add` failed after it removed the
                old collection, so the registry matches QMD again. A
                name with no entry changes nothing (action "absent").

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
                  --qmd-live-from <qmd-classify.json>: remove
                    qmd_collections entries whose `name` is not in the
                    `live_names` list of skf-qmd-classify-collections.py's
                    staged output. A file that is not there, or holds no
                    `live_names` list (the classifier did not run, or
                    failed), skips QMD cleanup: an empty list would read
                    as "nothing is live" and empty the registry.
                  --qmd-live-names a,b,c: the same with the list given
                    inline (mutually exclusive with --qmd-live-from).
                  --prune-missing-ccc-paths — remove ccc_index_registry
                    entries whose `path` no longer exists on disk.
                Both kinds of cleanup can run in the same invocation.

Output schema (the read subcommand and the response from every write):

  {"status": "ok", "version": "v1", ...subcommand-specific fields...}

The subcommands that take the registry lock (below) also return
`lock_stale_replaced`: null, or the {"held_by", "held_since"} of the
stale lock they replaced.

Errors emit `{"status": "error", "message": "..."}` to stderr and
exit non-zero (1 for user error, 2 for I/O failure or a registry lock
that cannot be taken, 3 when another call held the registry lock for the
whole --lock-timeout; nothing was written).

Cross-platform: pure stdlib + PyYAML. Atomic writes via temp + rename
mirror skf-atomic-write.py's pattern.

Registry lock: every subcommand that rewrites forge-tier.yaml
(write-tools, register-qmd-collection, remove-qmd-collection,
register-ccc-index, clean-stale) holds `forge-tier.yaml.lock` beside it
for its one read-modify-write and releases it before it exits, through
skf-run-lock.py loaded from this script's folder. Concurrent runs never
lose each other's entries, and no caller takes a lock of its own: the
lock lives inside one call, never across calls. A call waits up to
--lock-timeout seconds (30 by default) while another call holds the lock.
A lock older than 15 seconds was left by a call that was killed, and is
replaced. An empty lock file holds nothing (the helper never writes one;
an `flock` on the same path leaves one) and is replaced at once.

CLI — invoke via `uv run` so the PEP 723 PyYAML dependency declared
above is auto-resolved on first call and cached. `docs/getting-started.md`
documents uv as the runtime prerequisite for exactly this. Bare
`python3` will fail with `ModuleNotFoundError: No module named 'yaml'`
on a fresh interpreter where pyyaml has not been pip-installed
system-wide:

  uv run skf-forge-tier-rw.py read --target /path/forge-tier.yaml
  echo '{...}' | uv run skf-forge-tier-rw.py write-tools --target /path/forge-tier.yaml
  uv run skf-forge-tier-rw.py write-tools --target /path/forge-tier.yaml \\
      --detect-from /run/detect-tools.json --ccc-from /run/ccc-exclusions.json
  uv run skf-forge-tier-rw.py register-qmd-collection --target /path/forge-tier.yaml < entry.json
  uv run skf-forge-tier-rw.py remove-qmd-collection --target /path/forge-tier.yaml \\
      --name foo-extraction
  echo '{...}' | uv run skf-forge-tier-rw.py register-ccc-index --target /path/forge-tier.yaml
  uv run skf-forge-tier-rw.py clean-stale --target /path/forge-tier.yaml \\
      --qmd-live-from /run/qmd-classify.json --prune-missing-ccc-paths
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


DEFAULT_STALENESS_HOURS = 24
RUN_LOCK_HELPER = Path(__file__).resolve().parent / "skf-run-lock.py"
REGISTRY_LOCK_WAIT_SEC = 30.0
# A call holds the registry lock for milliseconds; one this old was killed.
REGISTRY_LOCK_STALE_SEC = 15.0
EXIT_LOCK_BUSY = 3
# The tool keys write-tools records, in forge-tier.yaml order.
TOOL_KEYS = ("ast_grep", "gh_cli", "qmd", "ccc")


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


def _load_run_lock():
    """Load skf-run-lock.py, which installs into the same folder as this script."""
    try:
        spec = importlib.util.spec_from_file_location("skf_run_lock", RUN_LOCK_HELPER)
        if spec is None or spec.loader is None:
            raise ImportError("no import spec")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except (OSError, ImportError) as e:
        _die(2, f"cannot load the run-lock helper {RUN_LOCK_HELPER}: {e}")
    return module


@contextlib.contextmanager
def _registry_lock(target: Path, command: str, timeout: float):
    """Hold `<target>.lock` through one read-modify-write of forge-tier.yaml.

    Yields the stale lock this call replaced ({"held_by", "held_since"}) or
    None. Exits 3 when another call holds the lock for `timeout` seconds, 2
    when the lock cannot be taken (a folder in its place, an I/O error).
    """
    run_lock = _load_run_lock()
    lock = target.with_name(target.name + ".lock")
    owner = f"forge-tier-rw:{command}:{run_lock.new_run_id()}"
    try:
        # The empty file an `flock` on this path leaves (create-skill prose
        # before 3.0.0) holds nothing, so it must not make the call wait.
        held = run_lock.acquire_within(lock, owner, REGISTRY_LOCK_STALE_SEC, timeout,
                                       empty_is_stale=True)
    except run_lock.LockBusy as busy:
        info = busy.result
        _die(EXIT_LOCK_BUSY,
             f"{command}: {lock} is held by {info['held_by'] or 'an unnamed owner'} since "
             f"{info['held_since']}: another run is writing {target.name}. Nothing was "
             f"written; run the command again.")
    except (OSError, ValueError) as e:
        _die(2, f"{command}: cannot take {lock}: {e}")
    try:
        yield held["stale_replaced"]
    finally:
        try:
            run_lock.release(lock, owner)
        except (OSError, ValueError):
            pass  # a lock this call could not delete goes stale on its own


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

    This is the file's one template, human-readable section comments
    included. Sections are emitted in a fixed order
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
        "exclude_patterns": ccc_index.get("exclude_patterns") or [],
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

    Four preservation rules (write-tools in the module docstring):
    - `qmd_collections` array — preserved entirely from existing.
    - `ccc_index_registry` array — preserved entirely from existing.
    - `ccc_index.staleness_threshold_hours` scalar — preserved if user set
      a non-default value; else uses payload value or DEFAULT.
    - `ccc_index.exclude_patterns` array — replaced when the payload
      carries a list; kept from the existing file when the payload sends
      null or omits it (an existing value that is not a list becomes []).
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
    if payload["ccc_index"].get("exclude_patterns") is None:
        prior = existing_ccc.get("exclude_patterns")
        payload["ccc_index"]["exclude_patterns"] = prior if isinstance(prior, list) else []
    return payload


def _payload_from(data: dict, **replace) -> dict:
    """The render payload of an existing forge-tier.yaml, with `replace` applied.

    render_forge_tier_yaml() emits exactly the six known top-level sections
    (tools, tier, tier_detected_at, ccc_index, ccc_index_registry,
    qmd_collections), so a rewrite from this payload drops any other
    top-level key, as cmd_write_tools does. Update render_forge_tier_yaml()
    and this function together when the schema grows.
    """
    payload = {
        "tools": data.get("tools", {}),
        "tier": data.get("tier", "Quick"),
        "tier_detected_at": data.get("tier_detected_at",
                                     datetime.now(timezone.utc).isoformat()),
        "ccc_index": data.get("ccc_index", {}),
        "ccc_index_registry": data.get("ccc_index_registry", []),
        "qmd_collections": data.get("qmd_collections", []),
    }
    payload.update(replace)
    return payload


# ─── Subcommands ─────────────────────────────────────────────────────────────


def cmd_read(target: Path) -> None:
    data = _read_yaml(target)
    if data is None:
        _ok({"exists": False, "data": None})
        return
    _ok({"exists": True, "data": data})


def _staged_object(path: Path):
    """The JSON object a staged helper output holds; None when it holds none (or cannot be read)."""
    try:
        # utf-8-sig: a shell that writes a byte-order mark still stages JSON.
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _staged_ccc_index(ccc_from: Path | None, ccc_available: bool = False) -> dict:
    """forge-tier.yaml's `ccc_index` from the merge helper's --result-to file.

    No file: the run did not prepare ccc (status "none"), or, when
    `ccc_available`, the helper ran and wrote nothing (a usage error, or a
    call its host stopped), so the preparation failed (status "failed"). A
    file holding an error, or no JSON object: the preparation failed too.
    Each keeps the exclusion record (exclude_patterns null). A result
    without an `index` object comes from a run without --build-index,
    which a setup run never makes: that is a usage error.
    """
    unset = {"indexed_path": None, "last_indexed": None, "file_count": None, "exclude_patterns": None}
    if ccc_from is None or not ccc_from.exists():
        if ccc_available:
            return {**unset, "status": "failed"}
        return {**unset, "status": "none"}
    result = _staged_object(ccc_from)
    if result is None or result.get("status") != "ok":
        return {**unset, "status": "failed"}
    index = result.get("index")
    if not isinstance(index, dict):
        _die(1, f"write-tools: {ccc_from} holds no `index` result (run the merge helper with --build-index)")
    patterns = result.get("effective_patterns")
    return {
        "indexed_path": index.get("indexed_path"),
        "last_indexed": index.get("last_indexed"),
        "status": index.get("status"),
        "file_count": index.get("file_count"),
        "exclude_patterns": patterns if isinstance(patterns, list) else None,
    }


def payload_from_staged(detect_from: Path, ccc_from: Path | None) -> dict:
    """The write-tools payload from a setup run's staged detector and ccc outputs."""
    detect = _staged_object(detect_from)
    if detect is None:
        _die(1, f"write-tools: {detect_from} holds no skf-detect-tools.py output")
    tools, tier = detect.get("tools"), detect.get("tier")
    if not isinstance(tools, dict) or not isinstance(tier, dict) or not tier.get("calculated"):
        _die(1, f"write-tools: {detect_from} has no `tools` and `tier.calculated`")

    def probe(key: str) -> dict:
        value = tools.get(key)
        return value if isinstance(value, dict) else {}

    return {
        "tools": {
            **{key: probe(key).get("available") is True for key in TOOL_KEYS},
            "ccc_daemon": probe("ccc").get("daemon"),
            "security_scan": probe("security_scan").get("available") is True,
        },
        "tier": tier["calculated"],
        "ccc_index": _staged_ccc_index(ccc_from, probe("ccc").get("available") is True),
    }


def cmd_write_tools(target: Path, lock_timeout: float = REGISTRY_LOCK_WAIT_SEC,
                    detect_from: Path | None = None, ccc_from: Path | None = None) -> None:
    if detect_from is not None:
        payload = payload_from_staged(detect_from, ccc_from)
    else:
        if ccc_from is not None:
            _die(1, "write-tools: --ccc-from needs --detect-from")
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

    with _registry_lock(target, "write-tools", lock_timeout) as stale_replaced:
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
        "lock_stale_replaced": stale_replaced,
    })


def cmd_register_qmd_collection(target: Path,
                                lock_timeout: float = REGISTRY_LOCK_WAIT_SEC) -> None:
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

    missing = (f"register-qmd-collection: target does not exist: {target}. "
               f"Run setup workflow first to create forge-tier.yaml.")
    if not target.exists():
        _die(1, missing)
    with _registry_lock(target, "register-qmd-collection", lock_timeout) as stale_replaced:
        data = _read_yaml(target)
        if data is None:
            _die(1, missing)

        collections = list(data.get("qmd_collections") or [])
        replaced = False
        for i, existing in enumerate(collections):
            if isinstance(existing, dict) and existing.get("name") == name:
                collections[i] = entry
                replaced = True
                break
        if not replaced:
            collections.append(entry)

        rendered = render_forge_tier_yaml(_payload_from(data, qmd_collections=collections))
        _atomic_write(target, rendered)
    _ok({
        "name": name,
        "action": "replaced" if replaced else "appended",
        "qmd_collections_count": len(collections),
        "wrote": str(target),
        "lock_stale_replaced": stale_replaced,
    })


def cmd_remove_qmd_collection(target: Path, name: str,
                              lock_timeout: float = REGISTRY_LOCK_WAIT_SEC) -> None:
    if not name.strip():
        _die(1, "remove-qmd-collection: --name must be a non-empty collection name")

    missing = (f"remove-qmd-collection: target does not exist: {target}. "
               f"Run setup workflow first to create forge-tier.yaml.")
    if not target.exists():
        _die(1, missing)
    with _registry_lock(target, "remove-qmd-collection", lock_timeout) as stale_replaced:
        data = _read_yaml(target)
        if data is None:
            _die(1, missing)

        collections = list(data.get("qmd_collections") or [])
        kept = [e for e in collections if not (isinstance(e, dict) and e.get("name") == name)]
        removed = len(collections) - len(kept)
        if removed:
            rendered = render_forge_tier_yaml(_payload_from(data, qmd_collections=kept))
            _atomic_write(target, rendered)
    _ok({
        "name": name,
        "action": "removed" if removed else "absent",
        "removed_count": removed,
        "qmd_collections_count": len(kept),
        "wrote": str(target) if removed else None,
        "lock_stale_replaced": stale_replaced,
    })


def cmd_register_ccc_index(target: Path, lock_timeout: float = REGISTRY_LOCK_WAIT_SEC) -> None:
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

    missing = (f"register-ccc-index: target does not exist: {target}. "
               f"Run setup workflow first to create forge-tier.yaml.")
    if not target.exists():
        _die(1, missing)
    with _registry_lock(target, "register-ccc-index", lock_timeout) as stale_replaced:
        data = _read_yaml(target)
        if data is None:
            _die(1, missing)

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

        rendered = render_forge_tier_yaml(_payload_from(data, ccc_index_registry=registry))
        _atomic_write(target, rendered)
    _ok({
        "source_repo": source_repo,
        "skill_name": skill_name,
        "action": "replaced" if replaced else "appended",
        "ccc_index_registry_count": len(registry),
        "wrote": str(target),
        "lock_stale_replaced": stale_replaced,
    })


def live_names_from(path: Path) -> list[str] | None:
    """The `live_names` of a staged classifier output, or None to skip QMD cleanup.

    A file that is not there (the classifier did not run) or that holds no
    list of names (it failed) gives None, never [], which would remove
    every qmd_collections entry.
    """
    if not path.exists():
        return None
    names = (_staged_object(path) or {}).get("live_names")
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        return None
    return names


def cmd_clean_stale(target: Path, qmd_live_names: list[str] | None,
                    prune_missing_ccc_paths: bool,
                    lock_timeout: float = REGISTRY_LOCK_WAIT_SEC) -> None:
    missing = f"clean-stale: target does not exist: {target}"
    if not target.exists():
        _die(1, missing)
    with _registry_lock(target, "clean-stale", lock_timeout) as stale_replaced:
        data = _read_yaml(target)
        if data is None:
            _die(1, missing)

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

        if qmd_removed or ccc_removed:
            # Round-trip through render to preserve the canonical format.
            rendered = render_forge_tier_yaml(_payload_from(data))
            _atomic_write(target, rendered)
    _ok({
        "qmd_removed": qmd_removed,
        "ccc_removed": ccc_removed,
        "wrote": bool(qmd_removed or ccc_removed),
        "lock_stale_replaced": stale_replaced,
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

    def add_lock_timeout(p: argparse.ArgumentParser) -> None:
        p.add_argument("--lock-timeout", type=float, default=REGISTRY_LOCK_WAIT_SEC,
                       help="seconds to wait while another call holds forge-tier.yaml.lock "
                            f"(default {REGISTRY_LOCK_WAIT_SEC:g})")

    p_write = sub.add_parser("write-tools",
                             help="Write a fresh forge-tier.yaml from a JSON payload on stdin, "
                                  "or from a setup run's staged outputs")
    p_write.add_argument("--target", type=Path, required=True)
    p_write.add_argument("--detect-from", type=Path, default=None,
                         help="skf-detect-tools.py's staged output; read instead of stdin.")
    p_write.add_argument("--ccc-from", type=Path, default=None,
                         help="skf-merge-ccc-exclusions.py's --result-to file (with --detect-from). "
                              "Not there: ccc was not prepared this run, or, when the detector "
                              "reports ccc available, the preparation failed.")
    add_lock_timeout(p_write)

    p_clean = sub.add_parser("clean-stale",
                             help="Remove stale qmd_collections / ccc_index_registry entries")
    p_clean.add_argument("--target", type=Path, required=True)
    live = p_clean.add_mutually_exclusive_group()
    live.add_argument("--qmd-live-from", type=Path, default=None,
                      help="skf-qmd-classify-collections.py's staged output. Entries in "
                           "qmd_collections whose name is NOT in its live_names are removed. A file "
                           "that is not there, or holds no live_names list, skips QMD cleanup.")
    live.add_argument("--qmd-live-names", default=None,
                      help="Comma-separated list of currently-live QMD collection names. "
                           "Entries in qmd_collections whose name is NOT in this list are removed. "
                           "Omit the flag entirely to skip QMD cleanup.")
    p_clean.add_argument("--prune-missing-ccc-paths", action="store_true",
                         help="Remove ccc_index_registry entries whose path no longer exists.")
    add_lock_timeout(p_clean)

    p_register = sub.add_parser("register-qmd-collection",
                                help="Append-or-replace a single qmd_collections entry by name")
    p_register.add_argument("--target", type=Path, required=True)
    add_lock_timeout(p_register)

    p_remove = sub.add_parser("remove-qmd-collection",
                              help="Remove the qmd_collections entries with this name (rollback)")
    p_remove.add_argument("--target", type=Path, required=True)
    p_remove.add_argument("--name", required=True, help="the collection name to remove")
    add_lock_timeout(p_remove)

    p_ccc = sub.add_parser("register-ccc-index",
                           help="Append-or-replace a single ccc_index_registry entry by source_repo+skill_name")
    p_ccc.add_argument("--target", type=Path, required=True)
    add_lock_timeout(p_ccc)

    args = parser.parse_args()

    lock_timeout = getattr(args, "lock_timeout", REGISTRY_LOCK_WAIT_SEC)
    if not math.isfinite(lock_timeout) or lock_timeout < 0:
        _die(1, f"{args.cmd}: --lock-timeout must be a number of seconds, 0 or more")

    if args.cmd == "read":
        cmd_read(args.target)
    elif args.cmd == "write-tools":
        cmd_write_tools(args.target, lock_timeout, args.detect_from, args.ccc_from)
    elif args.cmd == "clean-stale":
        live = None
        if args.qmd_live_from is not None:
            live = live_names_from(args.qmd_live_from)
        elif args.qmd_live_names is not None:
            live = [n.strip() for n in args.qmd_live_names.split(",") if n.strip()]
        cmd_clean_stale(args.target, live, args.prune_missing_ccc_paths, lock_timeout)
    elif args.cmd == "register-qmd-collection":
        cmd_register_qmd_collection(args.target, lock_timeout)
    elif args.cmd == "remove-qmd-collection":
        cmd_remove_qmd_collection(args.target, args.name, lock_timeout)
    elif args.cmd == "register-ccc-index":
        cmd_register_ccc_index(args.target, lock_timeout)


if __name__ == "__main__":
    main()
