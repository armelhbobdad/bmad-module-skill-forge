# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Campaign Render Batch: build the QS `--batch` input file for Tier B skills.

step-06 batches every Tier B skill through `skf-quick-skill --batch`. The batch
input file is a machine-consumed cross-tool contract: one target per line in the
exact single-target shape `skf-quick-skill` parses (parse_line in the shared
skf-quick-batch.py, documented in quick-skill's references/batch-mode.md).
Hand-building that file in prose is filter + join + reformat-structured-data,
the same mechanical, all-or-nothing work campaign-parse-manifest.py owns for the
inverse direction, where a silent format slip corrupts the whole run. This
script is the single source of truth for
the generation side, and for the way back: it is the only place step-06 selects
Tier B skills and the only place it joins QS results to them.

What it does (render mode):
  - Selects `skills[]` with `tier == "B"` and status `pending` or `active` (an
    `active` skill is one an interrupted batch left behind; completed, failed
    and skipped skills are left alone, so a resume is safe).
  - Leaves out each selected skill the directive's `## Skip List` names (read
    through campaign-quality-gate.py) and reports it in `skipped_by_directive`.
  - Looks up each skill's `repo_url` from the brief's `targets[]` (matched by
    name); repo URLs live only in the brief, never in the state schema.
  - Emits one line per skill in the CONSUMER's single-target shape:
      {repo_url}                        (pin is null: latest)
      {repo_url}@{pin}                  (a version pin: a digit, or `v` and a
                                         digit, first; skf-resolve-package.py's
                                         _VERSION_RE)
      {repo_url}/tree/{pin}             (any other pin, a branch such as
                                         `main`: quick-skill's parse-target
                                         reads it as the ref to build)
    with optional ` language=<lang>` / ` scope=<path>` modifiers appended when the
    brief target carries a `language_hint`/`language` or `scope_hint`/`scope` hint.
    QS reads a modifier as one word: a hint that is empty or holds whitespace
    would make it read the whole line as one target, so it is left out and
    reported in `dropped_hints`, and the first word of every line is the
    target QS records for it.
  - No skill-name field, no bare pin token: that would not parse as a target.
  - With --map, writes the line-to-skill map: line n of the batch file is QS's
    batch number n, so two skills whose lines read the same stay apart.

Record mode (--record): joins the QS batch summary (`summary_path` of the
`batch_summary` event) to the map by batch number. Each mapped skill gets
`completed` (QS status success, `skill_path` from `skill_package`, its
`quality_score`) or `failed` (with QS's `error_code`, or `no-batch-result`
when the summary holds no result for its line). A result whose target is not
the mapped line's target means the summary belongs to another batch file, and
nothing is joined.

CLI:
  uv run campaign-render-batch.py --state-file <p> --brief-file <p> \
      [-o <batchFile>] [--map <mapFile>] [--directive-file <p>]
  uv run campaign-render-batch.py --record <summary_path> --map <mapFile>

Output:
  render: batch text (one target per line) to {batchFile} via -o, else to
    stdout; the map JSON {"batch_file", "lines": [{"batch", "skill",
    "target", "line"}], "skipped_by_directive": [{"name", "reason"}]} to
    --map; a JSON summary {written, count, skipped_non_tierB,
    skipped_non_pending, skills, skipped_by_directive, dropped_hints:
    [{"skill", "hint", "value"}]} to stderr.
  record: {"results": [{"skill", "batch", "status", "quality_score",
    "skill_path", "exit_code", "error_code"}], "counts": {"completed",
    "failed"}} on stdout.

Exit codes:
  0  batch file written (0+ targets), or results joined
  2  state file missing / unreadable / bad YAML, a directive that cannot be
     read, a missing or unreadable map or summary, or a summary that does not
     match the map (SUMMARY_MISMATCH)
  8  brief missing / unreadable (missing-brief HALT), or a selected Tier B skill
     has no matching brief target with a repo_url (unmatched-target)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

GATE_SCRIPT = Path(__file__).resolve().with_name("campaign-quality-gate.py")
RESOLVE_PACKAGE_SCRIPT = Path(__file__).resolve().parent.parent.parent / "shared" / "scripts" / "skf-resolve-package.py"
SELECTED_STATUSES = ("pending", "active")


def _version_re() -> Any:
    """skf-resolve-package.py's _VERSION_RE: the pins parse-target reads after `@`."""
    spec = importlib.util.spec_from_file_location("skf_resolve_package", RESOLVE_PACKAGE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._VERSION_RE


VERSION_RE = _version_re()


def _err(message: str, code: str, exit_code: int, **extra: Any) -> int:
    payload: Dict[str, Any] = {"error": message, "code": code}
    payload.update(extra)
    json.dump(payload, sys.stderr)
    sys.stderr.write("\n")
    return exit_code


def _target_line(repo_url: str, pin: Any, target: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    """Render one batch line in the consumer's single-target shape.

    Returns (line, dropped): each hint QS could not read as one modifier word
    (empty, or holding whitespace) is left off the line and returned instead.
    """
    line = repo_url
    if pin and VERSION_RE.match(str(pin)):
        line += f"@{pin}"
    elif pin:
        # parse-target reads `@main` as no target at all; /tree/<branch> is a ref.
        line += f"/tree/{pin}"
    dropped: List[Dict[str, Any]] = []
    for modifier, fields in (("language", ("language_hint", "language")), ("scope", ("scope_hint", "scope"))):
        field = next((f for f in fields if target.get(f) not in (None, "")), None)
        if field is None:
            continue
        value = str(target[field]).strip()
        if not value or any(c.isspace() for c in value):
            dropped.append({"hint": field, "value": target[field]})
            continue
        line += f" {modifier}={value}"
    return line, dropped


def _skip_list(directive_file: Optional[str]) -> Dict[str, Optional[str]]:
    """The directive's Skip List, parsed by campaign-quality-gate.py (one parser)."""
    if not directive_file:
        return {}
    spec = importlib.util.spec_from_file_location("campaign_quality_gate", GATE_SCRIPT)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    try:
        return gate.read_directive(directive_file)["skip"]
    except gate.GateError as exc:
        raise OSError(str(exc)) from exc


def build_batch(
    state: Dict[str, Any],
    brief: Dict[str, Any],
    skip: Optional[Dict[str, Optional[str]]] = None,
) -> Tuple[List[str], Dict[str, Any]]:
    """Select Tier B pending and interrupted skills and render batch lines.

    Returns (lines, summary). `summary["skills"]` names the skill of each line,
    in order; `summary["skipped_by_directive"]` lists the selected skills the
    Skip List names; `summary["unmatched"]` lists any selected Tier B skill
    with no brief target / repo_url; the caller HALTs (exit 8) when it is
    non-empty.
    """
    skip = skip or {}
    skills = state.get("skills") or []
    targets: Dict[str, Dict[str, Any]] = {
        t.get("name"): t
        for t in (brief.get("targets") or [])
        if isinstance(t, dict) and t.get("name")
    }

    lines: List[str] = []
    names: List[str] = []
    unmatched: List[str] = []
    skipped_by_directive: List[Dict[str, Any]] = []
    dropped_hints: List[Dict[str, Any]] = []
    skipped_non_tierb = 0
    skipped_non_pending = 0

    for skill in skills:
        if not isinstance(skill, dict):
            continue
        if skill.get("tier") != "B":
            skipped_non_tierb += 1
            continue
        if skill.get("status") not in SELECTED_STATUSES:
            skipped_non_pending += 1
            continue

        name = skill.get("name")
        if name in skip:
            skipped_by_directive.append({"name": name, "reason": skip[name]})
            continue
        target = targets.get(name)
        repo_url = (target or {}).get("repo_url") or ""
        if not repo_url:
            unmatched.append(name)
            continue

        line, dropped = _target_line(repo_url, skill.get("pin"), target)
        lines.append(line)
        names.append(name)
        dropped_hints.extend({"skill": name, **d} for d in dropped)

    summary = {
        "count": len(lines),
        "skipped_non_tierB": skipped_non_tierb,
        "skipped_non_pending": skipped_non_pending,
        "skills": names,
        "skipped_by_directive": skipped_by_directive,
        "dropped_hints": dropped_hints,
        "unmatched": unmatched,
    }
    return lines, summary


def build_map(lines: List[str], summary: Dict[str, Any], batch_file: str) -> Dict[str, Any]:
    """The line-to-skill map: QS numbers the batch file's targets from 1, in line order.

    A line's target is its first word, the target QS records for it, because
    every word after it is a modifier QS reads as one (see _target_line).
    """
    return {
        "batch_file": batch_file,
        "lines": [
            {"batch": n, "skill": name, "target": line.split()[0], "line": line}
            for n, (line, name) in enumerate(zip(lines, summary["skills"]), start=1)
        ],
        "skipped_by_directive": summary["skipped_by_directive"],
    }


def join_results(batch_map: Dict[str, Any], batch_summary: Dict[str, Any]) -> Dict[str, Any]:
    """Join a QS batch summary's results[] to the mapped skills by batch number.

    Raises ValueError when a result's target is not its mapped line's target.
    """
    by_batch = {
        r.get("batch"): r
        for r in (batch_summary.get("results") or [])
        if isinstance(r, dict)
    }
    results: List[Dict[str, Any]] = []
    for entry in batch_map.get("lines") or []:
        result = by_batch.get(entry["batch"])
        if result is not None and result.get("target") != entry["target"]:
            raise ValueError(
                f"batch {entry['batch']} is `{result.get('target')}` in the summary but "
                f"`{entry['target']}` in the map: the summary belongs to another batch file"
            )
        row: Dict[str, Any] = {
            "skill": entry["skill"],
            "batch": entry["batch"],
            "status": "failed",
            "quality_score": None,
            "skill_path": None,
            "exit_code": None,
            "error_code": "no-batch-result",
        }
        if result is not None:
            ok = result.get("status") == "success"
            row.update(
                status="completed" if ok else "failed",
                quality_score=result.get("quality_score") if ok else None,
                skill_path=result.get("skill_package") if ok else None,
                exit_code=result.get("exit_code"),
                error_code=None if ok else result.get("error_code"),
            )
        results.append(row)
    counts = {key: sum(1 for r in results if r["status"] == key) for key in ("completed", "failed")}
    return {"results": results, "counts": counts}


def _load_yaml_mapping(path: str) -> Dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("top-level document is not a mapping")
    return data


def run(
    state_file: str,
    brief_file: str,
    output: str | None,
    map_file: str | None = None,
    directive_file: str | None = None,
) -> int:
    # State problems are plain file/parse errors (exit 2).
    if not Path(state_file).is_file():
        return _err(f"State file not found: {state_file}", "STATE_NOT_FOUND", 2)
    try:
        state = _load_yaml_mapping(state_file)
    except (yaml.YAMLError, ValueError) as exc:
        return _err(f"Failed to parse state YAML: {exc}", "STATE_PARSE_ERROR", 2)

    # Brief problems preserve step-06's missing-brief HALT (exit 8): repo_urls
    # live only in the brief, so a missing/unreadable/corrupt brief is fatal here.
    if not Path(brief_file).is_file():
        return _err(f"Brief file not found: {brief_file}", "missing-brief", 8)
    try:
        brief = _load_yaml_mapping(brief_file)
    except OSError as exc:
        return _err(f"Brief unreadable: {exc}", "missing-brief", 8)
    except (yaml.YAMLError, ValueError) as exc:
        return _err(f"Brief unparseable: {exc}", "missing-brief", 8)

    try:
        skip = _skip_list(directive_file)
    except OSError as exc:
        return _err(str(exc), "DIRECTIVE_UNREADABLE", 2)

    lines, summary = build_batch(state, brief, skip)

    unmatched = summary.pop("unmatched")
    if unmatched:
        return _err(
            "No matching brief target (repo_url) for selected Tier B skill(s): "
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
        "skills": summary["skills"],
        "skipped_by_directive": summary["skipped_by_directive"],
        "dropped_hints": summary["dropped_hints"],
    }
    if map_file:
        Path(map_file).write_text(
            json.dumps(build_map(lines, summary, summary["written"]), indent=2) + "\n",
            encoding="utf-8",
        )
        ordered["map"] = map_file
    json.dump(ordered, sys.stderr)
    sys.stderr.write("\n")
    return 0


def _load_json(path: str, label: str) -> Tuple[Optional[Dict[str, Any]], int]:
    if not Path(path).is_file():
        return None, _err(f"{label.capitalize()} file not found: {path}", f"{label.upper()}_NOT_FOUND", 2)
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, _err(f"{label.capitalize()} unreadable: {exc}", f"{label.upper()}_PARSE_ERROR", 2)
    if not isinstance(data, dict):
        return None, _err(f"{label.capitalize()} is not a JSON object: {path}", f"{label.upper()}_PARSE_ERROR", 2)
    return data, 0


def record(summary_file: str, map_file: str) -> int:
    batch_map, rc = _load_json(map_file, "map")
    if batch_map is None:
        return rc
    batch_summary, rc = _load_json(summary_file, "summary")
    if batch_summary is None:
        return rc
    try:
        joined = join_results(batch_map, batch_summary)
    except ValueError as exc:
        return _err(str(exc), "SUMMARY_MISMATCH", 2)
    json.dump(joined, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="campaign-render-batch",
        description="Build the QS --batch input file for Tier B skills, or join a QS "
        "batch summary back to them with --record.",
    )
    parser.add_argument("--state-file")
    parser.add_argument("--brief-file")
    parser.add_argument("-o", "--output", dest="output", help="batch file path (default: stdout)")
    parser.add_argument("--map", dest="map_file", help="line-to-skill map path (written, or read by --record)")
    parser.add_argument("--directive-file", help="campaign directive whose Skip List is applied")
    parser.add_argument("--record", dest="summary_file", help="QS batch summary to join to --map")
    args = parser.parse_args(argv)
    if args.summary_file:
        if not args.map_file:
            parser.error("--record needs --map")
        return record(args.summary_file, args.map_file)
    if not args.state_file or not args.brief_file:
        parser.error("--state-file and --brief-file are required to build the batch file")
    return run(args.state_file, args.brief_file, args.output, args.map_file, args.directive_file)


if __name__ == "__main__":
    raise SystemExit(main())
