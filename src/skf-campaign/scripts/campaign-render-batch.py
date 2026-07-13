# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Campaign Render Batch — build the QS `--batch` input file for Tier B skills.

step-06 batches every Tier B skill through `skf-quick-skill --batch`. The batch
input file is a machine-consumed cross-tool contract: one target per line in the
exact single-target shape `skf-quick-skill` parses (see
src/skf-quick-skill/references/batch-mode.md). Hand-building that file in prose
is filter + join + reformat-structured-data — the same mechanical, all-or-nothing
work campaign-parse-manifest.py owns for the inverse direction, where a silent
format slip corrupts the whole run. This script is the single source of truth for
the generation side so the line format lives in one place, aligned with the
consumer's contract, instead of being re-derived in the step prose.

What it does:
  - Filters `skills[]` for `tier == "B" && status == "pending"` (skips Tier A and
    any already completed/failed/skipped — resume-safe).
  - Looks up each skill's `repo_url` from the brief's `targets[]` (matched by
    name); repo URLs live only in the brief, never in the state schema.
  - Emits one line per skill in the CONSUMER's single-target shape:
      {repo_url}                        (pin is null → latest)
      {repo_url}@{pin}                  (skills[].pin is non-null)
    with optional ` language=<lang>` / ` scope=<path>` modifiers appended when the
    brief target carries a `language_hint`/`language` or `scope_hint`/`scope` hint.
  - No skill-name field, no bare pin token — that would not parse as a target.

CLI:
  uv run campaign-render-batch.py --state-file <p> --brief-file <p> [-o <batchFile>]

Output:
  - Batch text (one target per line) to {batchFile} via -o, else to stdout.
  - JSON summary {written, count, skipped_non_tierB, skipped_non_pending} to stderr.

Exit codes:
  0  batch file written (0+ targets)
  2  state file missing / unreadable / bad YAML
  8  brief missing / unreadable (missing-brief HALT), or a pending Tier B skill
     has no matching brief target with a repo_url (unmatched-target)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml


def _err(message: str, code: str, exit_code: int, **extra: Any) -> int:
    payload: Dict[str, Any] = {"error": message, "code": code}
    payload.update(extra)
    json.dump(payload, sys.stderr)
    sys.stderr.write("\n")
    return exit_code


def _target_line(repo_url: str, pin: Any, target: Dict[str, Any]) -> str:
    """Render one batch line in the consumer's single-target shape."""
    line = repo_url
    if pin:
        line += f"@{pin}"
    lang = target.get("language_hint") or target.get("language")
    scope = target.get("scope_hint") or target.get("scope")
    if lang:
        line += f" language={lang}"
    if scope:
        line += f" scope={scope}"
    return line


def build_batch(state: Dict[str, Any], brief: Dict[str, Any]) -> Tuple[List[str], Dict[str, Any]]:
    """Filter Tier B pending skills and render batch lines.

    Returns (lines, summary). `summary["unmatched"]` lists any pending Tier B
    skill names with no brief target / repo_url; the caller HALTs (exit 8) when
    it is non-empty.
    """
    skills = state.get("skills") or []
    targets: Dict[str, Dict[str, Any]] = {
        t.get("name"): t
        for t in (brief.get("targets") or [])
        if isinstance(t, dict) and t.get("name")
    }

    lines: List[str] = []
    unmatched: List[str] = []
    skipped_non_tierb = 0
    skipped_non_pending = 0

    for skill in skills:
        if not isinstance(skill, dict):
            continue
        if skill.get("tier") != "B":
            skipped_non_tierb += 1
            continue
        if skill.get("status") != "pending":
            skipped_non_pending += 1
            continue

        name = skill.get("name")
        target = targets.get(name)
        repo_url = (target or {}).get("repo_url") or ""
        if not repo_url:
            unmatched.append(name)
            continue

        lines.append(_target_line(repo_url, skill.get("pin"), target))

    summary = {
        "count": len(lines),
        "skipped_non_tierB": skipped_non_tierb,
        "skipped_non_pending": skipped_non_pending,
        "unmatched": unmatched,
    }
    return lines, summary


def _load_yaml_mapping(path: str) -> Dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("top-level document is not a mapping")
    return data


def run(state_file: str, brief_file: str, output: str | None) -> int:
    # State problems are plain file/parse errors (exit 2).
    if not Path(state_file).is_file():
        return _err(f"State file not found: {state_file}", "STATE_NOT_FOUND", 2)
    try:
        state = _load_yaml_mapping(state_file)
    except (yaml.YAMLError, ValueError) as exc:
        return _err(f"Failed to parse state YAML: {exc}", "STATE_PARSE_ERROR", 2)

    # Brief problems preserve step-06 §4's missing-brief HALT (exit 8): repo_urls
    # live only in the brief, so a missing/unreadable/corrupt brief is fatal here.
    if not Path(brief_file).is_file():
        return _err(f"Brief file not found: {brief_file}", "missing-brief", 8)
    try:
        brief = _load_yaml_mapping(brief_file)
    except OSError as exc:
        return _err(f"Brief unreadable: {exc}", "missing-brief", 8)
    except (yaml.YAMLError, ValueError) as exc:
        return _err(f"Brief unparseable: {exc}", "missing-brief", 8)

    lines, summary = build_batch(state, brief)

    unmatched = summary.pop("unmatched")
    if unmatched:
        return _err(
            "No matching brief target (repo_url) for pending Tier B skill(s): "
            + ", ".join(str(n) for n in unmatched),
            "unmatched-target",
            8,
            skills=unmatched,
        )

    batch_text = "\n".join(lines)
    if batch_text:
        batch_text += "\n"

    if output:
        Path(output).write_text(batch_text, encoding="utf-8")
        summary["written"] = output
    else:
        sys.stdout.write(batch_text)
        summary["written"] = "<stdout>"

    ordered = {
        "written": summary["written"],
        "count": summary["count"],
        "skipped_non_tierB": summary["skipped_non_tierB"],
        "skipped_non_pending": summary["skipped_non_pending"],
    }
    json.dump(ordered, sys.stderr)
    sys.stderr.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="campaign-render-batch",
        description="Build the QS --batch input file for pending Tier B skills.",
    )
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--brief-file", required=True)
    parser.add_argument("-o", "--output", dest="output", help="batch file path (default: stdout)")
    args = parser.parse_args(argv)
    return run(args.state_file, args.brief_file, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
