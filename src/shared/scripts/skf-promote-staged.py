# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Promote Staged: move a compiled skill from its staging folder into place, byte for byte.

skf-create-skill step 5 writes every artifact of a skill into its staging
folder, `_bmad-output/.skf-stage/{skill-name}/`, and steps 5a to 6 edit
them there (doc sources, auto-shard, doc-rot, skill-check --fix, the
description guard, the provenance fixes). Step 7 publishes that folder.
Writing each file again from the copies the model holds in context can
drop an edit a later step made on disk, or a file such as a
references/full-*.md that auto-shard created, so this helper copies the
staged bytes instead and reports what it wrote.

Subcommand:

  promote --stage <dir> --package <skill_package> --forge-version <dir>
          [--inventory <extraction inventory JSON> --source-root <dir>]

What goes where:

  <package>/        SKILL.md, context-snippet.md and metadata.json, every
                    file under the staged references/, and scripts/<name>
                    and assets/<name> for each scripts_inventory[] and
                    assets_inventory[] entry of --inventory, copied from
                    <source-root>/<source_file>
  <forge-version>/  provenance-map.json, evidence-report.md and
                    extraction-rules.yaml

The package is built in `<package>.skf-tmp/` with skf-atomic-write.py
stage-dir and swapped into place with its commit-dir, so a reader sees the
earlier package or the new one, never a mix, and a run that compiles a
version again leaves no file of the earlier package behind. Each workspace
file goes through skf-atomic-write.py write into --forge-version, which is
created when missing; nothing else in that folder (earlier result files,
test reports) is touched. Every promoted file is read back and its SHA-256
compared with the bytes it came from.

Any other file in the staging folder is not promoted and is listed in
`ignored`, as is a file under references/ that is hidden (a name starting
with `.`) or that ends in `.skf-tmp`, a write skf-atomic-write.py did not
finish. A script or asset whose bytes no longer match the content_hash
the inventory recorded is still copied, with a warning.

Output (stdout, exit 0):

  {
    "status": "ok",
    "package": "<package, / separators>",
    "forge_version": "<forge-version, / separators>",
    "files": [{"path": "...", "kind": "deliverable|reference|script|asset|workspace",
               "bytes": N, "sha256": "sha256:<hex>"}, ...],
    "counts": {"deliverables": 3, "references": N, "scripts": N, "assets": N,
               "workspace": 3},
    "ignored": ["<staged file not promoted>", ...],
    "warnings": ["..."]
  }

Exit codes:
  0  promoted and verified
  1  input error, nothing written: a staged file the package or the forge
     folder needs is missing, the inventory cannot be read, or a script or
     asset is missing, lies outside --source-root or shares its
     scripts/<name> or assets/<name> with another
  2  write failed (one line on stderr names it): a failed package swap
     leaves the earlier package in place, while a workspace file that fails
     after the swap leaves the new package and the workspace files written
     before it
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

ATOMIC_WRITE = Path(__file__).resolve().parent / "skf-atomic-write.py"
DELIVERABLES = ("SKILL.md", "context-snippet.md", "metadata.json")
WORKSPACE_FILES = ("provenance-map.json", "evidence-report.md", "extraction-rules.yaml")
REFERENCES = "references"
# skf-atomic-write.py's temporary name: a write it did not finish leaves <name>.skf-tmp.
TMP_SUFFIX = ".skf-tmp"
# The inventory lists and the package folder each one lands in.
BUNDLED = (("scripts_inventory", "scripts", "script"), ("assets_inventory", "assets", "asset"))
ATOMIC_TIMEOUT_SEC = 120


class InputError(Exception):
    """Exit 1: nothing was written."""


class WriteError(Exception):
    """Exit 2: a write failed."""


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _posix(path: Path) -> str:
    return path.as_posix()


def _atomic(args: list[str], data: bytes | None = None) -> None:
    """Run skf-atomic-write.py with `args`; a non-zero exit is a WriteError."""
    try:
        proc = subprocess.run([sys.executable, str(ATOMIC_WRITE), *args], input=data or b"",
                              capture_output=True, timeout=ATOMIC_TIMEOUT_SEC, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WriteError(f"skf-atomic-write.py {args[0]} did not run: {exc}") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise WriteError(f"skf-atomic-write.py {args[0]} failed: {detail[-1] if detail else proc.returncode}")


def _staged_references(stage: Path) -> list[Path]:
    """The staged reference files, less a hidden one and a write an interrupted run left half done."""
    folder = stage / REFERENCES
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.rglob("*") if p.is_file() and not p.name.endswith(TMP_SUFFIX)
                  and not any(part.startswith(".") for part in p.relative_to(folder).parts))


def _bundled_files(inventory: Path | None, source_root: Path | None) -> list[tuple[str, str, Path, str | None]]:
    """(kind, package-relative path, source file, recorded hash) per inventory script and asset."""
    if inventory is None:
        return []
    try:
        data = json.loads(inventory.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise InputError(f"cannot read the inventory {_posix(inventory)}: {exc}") from exc
    if not isinstance(data, dict):
        raise InputError(f"the inventory {_posix(inventory)} is not a JSON object")
    entries: list[tuple[str, str, Path, str | None]] = []
    seen: dict[str, str] = {}
    for key, folder, kind in BUNDLED:
        records = data.get(key) or []
        if not isinstance(records, list):
            raise InputError(f"the inventory's {key} is not a list")
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get("source_file"), str):
                raise InputError(f"a {key} entry has no source_file: {record!r}")
            if source_root is None:
                raise InputError(f"the inventory lists {key} entries: pass --source-root")
            rel = PurePosixPath(record["source_file"])
            if rel.is_absolute() or ".." in rel.parts or not rel.parts:
                raise InputError(f"{key} entry {record['source_file']!r} is not a path inside --source-root")
            name = record.get("name") or rel.name
            if not isinstance(name, str) or not name or "/" in name or "\\" in name:
                raise InputError(f"{key} entry {record['source_file']!r} has no usable name")
            target = f"{folder}/{name}"
            if target in seen:
                raise InputError(f"{seen[target]!r} and {record['source_file']!r} would both be {target}")
            seen[target] = record["source_file"]
            source = source_root.joinpath(*rel.parts)
            if not source.is_file():
                raise InputError(f"{key} entry {record['source_file']!r} is not a file under --source-root")
            recorded = record.get("content_hash")
            entries.append((kind, target, source, recorded if isinstance(recorded, str) else None))
    return entries


def promote(stage: Path, package: Path, forge_version: Path,
            inventory: Path | None = None, source_root: Path | None = None) -> dict:
    """Promote the staging folder (see the module docstring); raises InputError or WriteError."""
    if not stage.is_dir():
        raise InputError(f"no staging folder at {_posix(stage)}")
    missing = [name for name in (*DELIVERABLES, *WORKSPACE_FILES) if not (stage / name).is_file()]
    if missing:
        raise InputError(f"the staging folder {_posix(stage)} has no {', '.join(missing)}")
    references = _staged_references(stage)
    bundled = _bundled_files(inventory, source_root)

    plan: list[tuple[str, str, bytes]] = []  # (kind, package-relative path, bytes)
    for name in DELIVERABLES:
        plan.append(("deliverable", name, (stage / name).read_bytes()))
    for path in references:
        plan.append(("reference", path.relative_to(stage).as_posix(), path.read_bytes()))
    warnings: list[str] = []
    for kind, rel, source, recorded in bundled:
        data = source.read_bytes()
        if recorded is not None and recorded != _sha256(data):
            warnings.append(f"{rel}: {_posix(source)} changed since extraction recorded {recorded}")
        plan.append((kind, rel, data))
    workspace = [(name, (stage / name).read_bytes()) for name in WORKSPACE_FILES]

    promoted = {_posix(p.relative_to(stage)) for p in references} | set(DELIVERABLES) | set(WORKSPACE_FILES)
    ignored = sorted(p.relative_to(stage).as_posix() for p in stage.rglob("*")
                     if p.is_file() and p.relative_to(stage).as_posix() not in promoted)

    # The package: build it beside its target, then swap it in.
    _atomic(["stage-dir", "--target", str(package)])
    building = package.with_name(package.name + ".skf-tmp")
    try:
        for _, rel, data in plan:
            target = building.joinpath(*PurePosixPath(rel).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    except OSError as exc:
        shutil.rmtree(building, ignore_errors=True)
        raise WriteError(f"cannot build {_posix(building)}: {exc}") from exc
    _atomic(["commit-dir", "--target", str(package)])

    # The workspace files, one atomic write each.
    for name, data in workspace:
        _atomic(["write", "--target", str(forge_version / name)], data)

    files = []
    for kind, rel, data in plan:
        files.append(_verified(package.joinpath(*PurePosixPath(rel).parts), kind, data))
    for name, data in workspace:
        files.append(_verified(forge_version / name, "workspace", data))
    counts = {"deliverables": len(DELIVERABLES), "references": len(references),
              "scripts": sum(1 for kind, *_ in bundled if kind == "script"),
              "assets": sum(1 for kind, *_ in bundled if kind == "asset"),
              "workspace": len(WORKSPACE_FILES)}
    return {"status": "ok", "package": _posix(package), "forge_version": _posix(forge_version),
            "files": files, "counts": counts, "ignored": ignored, "warnings": warnings}


def _verified(path: Path, kind: str, data: bytes) -> dict:
    """The promoted file's record, after checking it holds the bytes it came from."""
    try:
        written = path.read_bytes()
    except OSError as exc:
        raise WriteError(f"cannot read back {_posix(path)}: {exc}") from exc
    if written != data:
        raise WriteError(f"{_posix(path)} does not hold the bytes it was promoted from")
    return {"path": _posix(path), "kind": kind, "bytes": len(written), "sha256": _sha256(written)}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-promote-staged.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("promote", help="copy a staged skill into its package and forge version folders")
    p.add_argument("--stage", required=True, type=Path, help="the staging folder, _bmad-output/.skf-stage/<skill>")
    p.add_argument("--package", required=True, type=Path, help="the skill package folder, {skill_package}")
    p.add_argument("--forge-version", required=True, type=Path, help="the forge version folder, {forge_version}")
    p.add_argument("--inventory", type=Path, default=None,
                   help="the extraction inventory JSON whose scripts_inventory and assets_inventory are bundled")
    p.add_argument("--source-root", type=Path, default=None,
                   help="the source tree the inventory's source_file paths are relative to")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = promote(args.stage, args.package, args.forge_version, args.inventory, args.source_root)
    except InputError as exc:
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        return 1
    except WriteError as exc:
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


def _force_utf8(*streams) -> None:
    """Reconfigure the JSON streams to UTF-8 (a Windows console uses cp1252)."""
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


if __name__ == "__main__":
    _force_utf8(sys.stdout, sys.stderr)
    sys.exit(main())
