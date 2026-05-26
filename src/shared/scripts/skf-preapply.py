# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""SKF Pre-Apply — apply known workarounds before pipeline iteration.

Loads a shared seed registry of known workarounds and optionally a project-local
registry, then scans target directory files for fingerprint matches and applies
the corresponding fixes.

CLI:
  uv run python src/shared/scripts/skf-preapply.py \
      --target-dir <path> [--registry <path>] [--local-registry <path>] [--log-dir <path>]

Input:
  --target-dir       directory to scan for fingerprint matches (required)
  --registry         path to shared seed registry YAML (optional, defaults to
                     src/shared/_known-workarounds.yaml relative to script)
  --local-registry   path to project-local override registry YAML (optional)
  --log-dir          directory to write preapply-log.json (optional)

Output (JSON on stdout):
  {
    "applied": [{"fingerprint": "...", "fix": "...", "file": "...", "severity": "..."}],
    "skipped_count": 0,
    "registry_version": 1
  }

Exit codes:
  0  success (applied >= 0 fixes without errors)
  2  error (invalid args, missing registry, YAML parse error)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, NoReturn

import yaml


def _err(message: str, code: str) -> NoReturn:
    json.dump({"error": message, "code": code}, sys.stderr)
    sys.stderr.write("\n")
    sys.exit(2)


def _load_registry(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        _err(f"Registry not found: {path}", "REGISTRY_NOT_FOUND")
    try:
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        _err(f"YAML parse error in {path}: {exc}", "YAML_PARSE_ERROR")
    if not isinstance(data, dict) or "workarounds" not in data:
        _err(f"Invalid registry format in {path}", "INVALID_REGISTRY")
    return data


def _merge_registries(
    shared: Dict[str, Any], local: Dict[str, Any] | None
) -> tuple[List[Dict[str, Any]], int]:
    version = shared.get("version", 1)
    by_fp: Dict[str, Dict[str, Any]] = {}
    for entry in shared.get("workarounds", []):
        by_fp[entry["fingerprint"]] = entry
    if local is not None:
        for entry in local.get("workarounds", []):
            by_fp[entry["fingerprint"]] = entry
    return list(by_fp.values()), version


def _match_and_apply(
    workarounds: List[Dict[str, Any]], target_dir: Path
) -> tuple[List[Dict[str, Any]], int]:
    applied: List[Dict[str, Any]] = []
    skipped = 0

    md_files = sorted(target_dir.rglob("*.md"))

    for wa in workarounds:
        fp = wa["fingerprint"]
        fix = wa["fix"]
        use_regex = wa.get("regex", False)
        matched = False

        for md_file in md_files:
            content = md_file.read_text(encoding="utf-8")
            if use_regex:
                try:
                    pattern = re.compile(fp)
                except re.error as exc:
                    _err(
                        f"Invalid regex in workaround fingerprint: {exc}",
                        "INVALID_REGEX",
                    )
                if pattern.search(content):
                    new_content = pattern.sub(fix, content)
                    md_file.write_text(new_content, encoding="utf-8")
                    applied.append({
                        "fingerprint": fp,
                        "fix": fix,
                        "file": md_file.relative_to(target_dir).as_posix(),
                        "severity": wa.get("severity", "low"),
                    })
                    matched = True
            else:
                if fp in content:
                    new_content = content.replace(fp, fix)
                    md_file.write_text(new_content, encoding="utf-8")
                    applied.append({
                        "fingerprint": fp,
                        "fix": fix,
                        "file": md_file.relative_to(target_dir).as_posix(),
                        "severity": wa.get("severity", "low"),
                    })
                    matched = True

        if not matched:
            skipped += 1

    return applied, skipped


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Apply known workarounds before pipeline iteration."
    )
    parser.add_argument(
        "--target-dir", required=True, type=Path,
        help="Directory to scan for fingerprint matches",
    )
    default_registry = (
        Path(__file__).resolve().parent.parent / "_known-workarounds.yaml"
    )
    parser.add_argument(
        "--registry", type=Path, default=default_registry,
        help="Path to shared seed registry YAML",
    )
    parser.add_argument(
        "--local-registry", type=Path, default=None,
        help="Path to project-local override registry YAML",
    )
    parser.add_argument(
        "--log-dir", type=Path, default=None,
        help="Directory to write preapply-log.json",
    )

    args = parser.parse_args(argv)

    if not args.target_dir.is_dir():
        _err(
            f"Target directory not found: {args.target_dir}",
            "TARGET_NOT_FOUND",
        )

    shared = _load_registry(args.registry)

    local = None
    if args.local_registry is not None:
        local = _load_registry(args.local_registry)

    workarounds, version = _merge_registries(shared, local)
    applied, skipped = _match_and_apply(workarounds, args.target_dir)

    result = {
        "applied": applied,
        "skipped_count": skipped,
        "registry_version": version,
    }

    json.dump(result, sys.stdout)
    sys.stdout.write("\n")

    if args.log_dir is not None:
        args.log_dir.mkdir(parents=True, exist_ok=True)
        log_path = args.log_dir / "preapply-log.json"
        with open(
            log_path, "w", encoding="utf-8", newline="\n"
        ) as f:
            json.dump(result, f, indent=2)
            f.write("\n")


if __name__ == "__main__":
    main()
