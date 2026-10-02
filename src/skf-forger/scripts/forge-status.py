#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Where each skill stands in the lifecycle, and the next code for it (WS).

Ferris's WS action (SKILL.md, Inline Actions) runs this once instead of
globbing the briefs, reading each skill's test result and working out each
stage and next code in the prompt. Which stage a skill reached and which code
comes next has one correct answer per state on disk, so it runs here.

Sources, read again on every call:

  briefs      {forge_data_folder}/<name>/skill-brief.yaml
  skills      skf-skill-inventory.py, the first existing of
              {project-root}/_bmad/skf/shared/scripts/ (installed) and
              {project-root}/src/shared/scripts/ (dev), or the path
              --inventory names, run through its CLI: the skills SKF
              generated (`skf_skill`), each with its `active_version`, and
              the export manifest
  verdicts    `summary.result` of skf-test-skill-result-latest.json in
              {forge_data_folder}/<name>/<active_version>/ (in
              {forge_data_folder}/<name>/ for a skill in the flat layout)
  pipeline    the resume or repair offer a stopped chain left: the `resume`
              of pipeline-journal.py (beside this script), as On Activation
              reads it

Stage, the furthest each skill reached:

  briefed    a brief and no skill of that name
  compiled   a skill with no verdict for its active version
  tested     a verdict for its active version, which is not the exported one
  exported   its active version is the manifest's `active_version` for it

Next code, one per skill (null: up to date):

  briefed                                  CS <name>
  no verdict, INCONCLUSIVE, PASS_WITH_DRIFT  TS <name>
  FAIL                                     US <name> --from-test-report
  PASS, active version not exported        EX <name>
  PASS, active version exported            null

The skill a stopped chain's offer names (its `skill_name`) takes the offer's
`route` instead. An offer whose skill is not listed (a chain that stopped
before a workflow handed a skill name on names none) adds its route as the
last of the `recommended` actions. `pipeline` is the offer either way.

When the inventory cannot run, each brief is listed by name with no stage
and no next code, and a warning says why: the briefs alone cannot tell a
compiled skill from a briefed one. A skills folder that does not exist yet
holds no skill, with no warning.

CLI usage (from the skf-forger skill root):
  uv run scripts/forge-status.py --project-root <dir> \\
      --skills-output-folder <dir> --forge-data-folder <dir> \\
      --run-root <dir> --result-dir <dir> [--inventory <skf-skill-inventory.py>]

Output (stdout, one object):
  {
    "status": "ok",
    "skills": [{"name", "stage", "active_version", "verdict",
                "exported_version", "next"}, ...],     # sorted by name
    "pipeline": null | {"offer", "route", "skill_name", "journal"},
    "recommended": ["CS hono", "US cognee --from-test-report", ...],
    "warnings": []          # e.g. "inventory_unavailable: not found"
  }

Exit codes:
  0  printed the status
  2  usage error (argparse: usage on stderr, no JSON)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

# Shipped scripts are consumer files, not a place for interpreter caches.
sys.dont_write_bytecode = True

JOURNAL_SCRIPT = Path(__file__).resolve().parent / "pipeline-journal.py"
BRIEF = "skill-brief.yaml"
TEST_RESULT = "skf-test-skill-result-latest.json"
INVENTORY_TIMEOUT = 120
# Where the shared inventory script sits under the project root, in probe order.
INVENTORY_PROBES = ("_bmad/skf/shared/scripts/skf-skill-inventory.py", "src/shared/scripts/skf-skill-inventory.py")

# `summary.result` spellings, as the next-code table names them.
VERDICTS = frozenset({"PASS", "FAIL", "INCONCLUSIVE", "PASS_WITH_DRIFT"})
RETEST = frozenset({None, "INCONCLUSIVE", "PASS_WITH_DRIFT"})


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"{path.as_posix()}: {e}") from None


def brief_names(forge_data_folder: Path) -> list[str]:
    """The names with a skill-brief.yaml in their forge folder."""
    try:
        return sorted(p.parent.name for p in forge_data_folder.glob(f"*/{BRIEF}") if p.is_file())
    except OSError:
        return []


def find_inventory(project_root: Path) -> Path | None:
    """The first inventory script of INVENTORY_PROBES under the project root, or None."""
    return next((project_root / probe for probe in INVENTORY_PROBES if (project_root / probe).is_file()), None)


def run_inventory(inventory: Path | None, skills_output_folder: Path, forge_data_folder: Path) -> dict:
    """skf-skill-inventory.py's scan, through its CLI; ValueError when it cannot give one."""
    if inventory is None:
        raise ValueError("not found")
    if not inventory.is_file():
        raise ValueError(f"{inventory.as_posix()} not found")
    try:
        done = subprocess.run(
            [sys.executable, str(inventory), str(skills_output_folder), "--forge-data-folder",
             str(forge_data_folder)],
            capture_output=True, text=True, encoding="utf-8", timeout=INVENTORY_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ValueError(f"{inventory.name} did not run: {e}") from None
    try:
        result = json.loads(done.stdout)
    except json.JSONDecodeError:
        first = (done.stderr.strip().splitlines() or ["no JSON"])[0]
        raise ValueError(f"{inventory.name} printed no JSON: {first}") from None
    if not isinstance(result, dict):
        raise ValueError(f"{inventory.name} printed no JSON object")
    if result.get("code") == "DIR_NOT_FOUND":
        return {"skills": [], "manifest": None}  # no skill exists yet
    if result.get("status") != "ok":
        raise ValueError(f"{inventory.name}: {result.get('error') or result.get('code') or 'status not ok'}")
    return result


def read_verdict(forge_data_folder: Path, name: str, active_version: str) -> str | None:
    """The settled verdict for the active version, upper case, or None; ValueError on an unreadable file."""
    folder = forge_data_folder / name
    record = _read_json((folder if active_version == "flat" else folder / active_version) / TEST_RESULT)
    summary = record.get("summary") if isinstance(record, dict) else None
    result = summary.get("result") if isinstance(summary, dict) else None
    if not isinstance(result, str):
        return None
    verdict = result.strip().upper().replace("-", "_")
    return verdict if verdict in VERDICTS else None


def exported_version(manifest, name: str) -> str | None:
    exports = manifest.get("exports") if isinstance(manifest, dict) else None
    entry = exports.get(name) if isinstance(exports, dict) else None
    version = entry.get("active_version") if isinstance(entry, dict) else None
    return version if isinstance(version, str) and version else None


def skill_status(name: str, active_version: str | None, verdict: str | None, exported: str | None) -> dict:
    """One skill's stage and next code, by the tables in the module docstring."""
    if verdict == "FAIL":
        nxt = f"US {name} --from-test-report"
    elif verdict in RETEST:
        nxt = f"TS {name}"
    elif exported != active_version:
        nxt = f"EX {name}"
    else:
        nxt = None
    if exported is not None and exported == active_version:
        stage = "exported"
    else:
        stage = "compiled" if verdict is None else "tested"
    return {"name": name, "stage": stage, "active_version": active_version, "verdict": verdict,
            "exported_version": exported, "next": nxt}


def _brief_status(name: str) -> dict:
    return {"name": name, "stage": "briefed", "active_version": None, "verdict": None,
            "exported_version": None, "next": f"CS {name}"}


def _unknown_status(name: str) -> dict:
    return {"name": name, "stage": None, "active_version": None, "verdict": None,
            "exported_version": None, "next": None}


def _load_journal():
    spec = importlib.util.spec_from_file_location("skf_pipeline_journal", JOURNAL_SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError("no import spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pipeline_offer(run_root: Path, result_dir: Path, forge_data_folder: Path, skills_output_folder: Path,
                   warnings: list) -> dict | None:
    """The offer On Activation's `pipeline-journal.py resume` call makes, or None."""
    try:
        journal = _load_journal()
    except (ImportError, OSError, SyntaxError) as e:
        warnings.append(f"pipeline_offer_unavailable: pipeline-journal.py cannot be loaded: {e}")
        return None
    found = journal.cmd_resume(argparse.Namespace(
        run_root=str(run_root), result_dir=str(result_dir), forge_data_folder=str(forge_data_folder),
        skills_output_folder=str(skills_output_folder)))
    warnings.extend(found.get("warnings", []))
    if found.get("status") != "offer":
        return None
    return {key: found.get(key) for key in ("offer", "route", "skill_name", "journal")}


def forge_status(skills_output_folder: Path, forge_data_folder: Path, inventory: Path | None, run_root: Path,
                 result_dir: Path) -> dict:
    warnings: list = []
    briefs = brief_names(forge_data_folder)
    entries: dict[str, dict] = {}
    try:
        scan = run_inventory(inventory, skills_output_folder, forge_data_folder)
    except ValueError as e:
        warnings.append(f"inventory_unavailable: {e}")
        entries = {name: _unknown_status(name) for name in briefs}
    else:
        for skill in scan.get("skills") or []:
            if not (isinstance(skill, dict) and skill.get("skf_skill") and isinstance(skill.get("name"), str)):
                continue
            name, active = skill["name"], skill.get("active_version")
            verdict = None
            if isinstance(active, str) and active:
                try:
                    verdict = read_verdict(forge_data_folder, name, active)
                except ValueError as e:
                    warnings.append(f"test_result_unreadable: {e}")
            entries[name] = skill_status(name, active, verdict, exported_version(scan.get("manifest"), name))
        for name in briefs:
            entries.setdefault(name, _brief_status(name))
    offer = pipeline_offer(run_root, result_dir, forge_data_folder, skills_output_folder, warnings)
    named = offer is not None and offer.get("skill_name") in entries
    if named:
        entries[offer["skill_name"]]["next"] = offer["route"]
    skills = [entries[name] for name in sorted(entries)]
    recommended = [s["next"] for s in skills if s["next"]]
    if offer is not None and not named and offer.get("route"):
        recommended.append(offer["route"])
    return {"status": "ok", "skills": skills, "pipeline": offer, "recommended": recommended,
            "warnings": warnings}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forge-status",
        description=(
            "Ferris's WS status: each skill's lifecycle stage (briefed, compiled, tested or exported) "
            "and the next code to run for it, from the briefs, the skill inventory, the test verdicts, "
            "the export manifest and a stopped pipeline's offer."
        ),
    )
    parser.add_argument("--skills-output-folder", required=True, help="The skills output folder.")
    parser.add_argument("--forge-data-folder", required=True, help="The forge data folder (briefs, test results).")
    parser.add_argument("--project-root", required=True,
                        help="The project root, under which the shared skf-skill-inventory.py is found.")
    parser.add_argument("--inventory",
                        help="The path of skf-skill-inventory.py, in place of the one found under the project root.")
    parser.add_argument("--run-root", required=True, help="The folder that holds the pipeline runs' folders.")
    parser.add_argument("--result-dir", required=True, help="The folder of the pipeline result files (the sidecar).")
    return parser


def _force_utf8(*streams) -> None:
    """Reconfigure the output streams to UTF-8 (a Windows console uses cp1252)."""
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    inventory = Path(args.inventory) if args.inventory else find_inventory(Path(args.project_root))
    result = forge_status(Path(args.skills_output_folder), Path(args.forge_data_folder), inventory,
                          Path(args.run_root), Path(args.result_dir))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    _force_utf8(sys.stdout, sys.stderr)
    sys.exit(main())
