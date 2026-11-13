#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
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
  audits      `summary.severity` of audit-skill-result-latest.json, in the
              same folder as the verdict, with its `timestamp` and its
              `summary.upstream_moved` and `summary.upstream_ref`
  campaign    an unfinished campaign: _campaign-state.yaml in the campaign
              workspace (--campaign-workspace, default
              {forge_data_folder}/_campaign), tallied by skf-campaign's
              campaign-status.py, the first existing of
              {project-root}/_bmad/skf/skf-campaign/scripts/ (installed) and
              {project-root}/src/skf-campaign/scripts/ (dev), run through its
              CLI; the state itself is read for its members' names only
  pipeline    the resume or repair offer a stopped chain left: the `resume`
              of pipeline-journal.py (beside this script), as On Activation
              reads it

Stage, the furthest each skill reached:

  briefed    a brief and no skill of that name
  compiled   a skill with no verdict for its active version
  tested     a verdict for its active version, which is not the exported one
  exported   its active version is the manifest's `active_version` for it

Next code, one per skill (null: up to date), by the verdict:

  briefed                                    CS <name>
  no verdict, INCONCLUSIVE, PASS_WITH_DRIFT  TS <name>
  FAIL                                       US <name> --from-test-report
  PASS, active version not exported          EX <name>
  PASS, active version exported              null: no drift on record

Drift on record: the audit record's severity is MINOR, SIGNIFICANT or
CRITICAL, and its `timestamp` (the emitter's ISO-8601 UTC stamp) is later
than the test record's, or no test record carries a readable `timestamp`.
It takes `US <name>`, or `US <name> --target-ref <upstream_ref>` when the
audit found upstream moved (`upstream_moved` true and `upstream_ref` a
non-empty string, stripped, as pipeline-gate.py's AS gate hands it on): Update
Skill reads the ref the skill was built from unless it is given one, so a
skill pinned to a tag would miss the drift found at the newer ref. The
entry's `drift` names the severity; `drift` is null for every other entry.
An older audit, a CLEAN one (upstream moved or not), or one that does not
parse (a warning) leaves the verdict's code.

Each of these, lowest first, replaces the code before it:

  1. the verdict's code (the table above)
  2. drift on record                    US <name> [--target-ref <upstream_ref>]
  3. a member of an unfinished campaign  CA
  4. the skill a stopped chain's offer names (its `skill_name`): the offer's
     `route`

A campaign is finished when its `current_stage` is CAMPAIGN_FINAL_STAGE
(campaign-state.py's FINAL_STAGE) and no skill is pending or active; only an
unfinished one is printed, as `campaign`. Its members are each state
`skills[]` entry's `name` and the last part of its `skill_path` (Export Skill
names a Tier B skill's folder after its library, not its campaign name). A
campaign workspace that skf-campaign's `campaign_workspace_path` moved is
read only when the caller passes --campaign-workspace.

`recommended` lists the skills' codes in name order, each value once, then
the route of an offer whose skill is not listed (a chain that stopped before
a workflow handed a skill name on names none), then `CA` while a campaign is
unfinished and no listed skill shows it (no listed skill is a member, or an
offer's route stands for each that is). `pipeline` is the offer either way.

When the inventory cannot run, each brief is listed by name with no stage
and no next code, and a warning says why: the briefs alone cannot tell a
compiled skill from a briefed one. A skills folder that does not exist yet
holds no skill, with no warning. No campaign state gives no campaign and no
warning; a state campaign-status.py cannot tally, or no campaign-status.py,
is a `campaign_unavailable` warning, which gives the `error` it printed on
stderr, else its last stderr line (a crash's traceback ends with the cause).

CLI usage (from the skf-forger skill root):
  uv run scripts/forge-status.py --project-root <dir> \\
      --skills-output-folder <dir> --forge-data-folder <dir> \\
      --run-root <dir> --result-dir <dir> [--inventory <skf-skill-inventory.py>] \\
      [--campaign-workspace <dir>]
  uv run scripts/forge-status.py --campaign-only --project-root <dir> \\
      --forge-data-folder <dir> [--campaign-workspace <dir>]

Output (stdout, one object):
  {
    "status": "ok",
    "skills": [{"name", "stage", "active_version", "verdict",
                "exported_version", "drift", "next"}, ...],  # sorted by name
    "pipeline": null | {"offer", "route", "skill_name", "journal"},
    "campaign": null | {"name", "current_stage", "completed", "total"},
    "recommended": ["CS hono", "US cognee --from-test-report", ...],
    "warnings": []          # e.g. "inventory_unavailable: not found"
  }

--campaign-only reads the campaign alone (no inventory, no offer), for the
greeting: {"status": "ok", "campaign": ..., "warnings": [...]}.

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
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

# Shipped scripts are consumer files, not a place for interpreter caches.
sys.dont_write_bytecode = True

JOURNAL_SCRIPT = Path(__file__).resolve().parent / "pipeline-journal.py"
BRIEF = "skill-brief.yaml"
TEST_RESULT = "skf-test-skill-result-latest.json"
AUDIT_RESULT = "audit-skill-result-latest.json"
INVENTORY_TIMEOUT = 120
# Where the shared inventory script sits under the project root, in probe order.
INVENTORY_PROBES = ("_bmad/skf/shared/scripts/skf-skill-inventory.py", "src/shared/scripts/skf-skill-inventory.py")
CAMPAIGN_WORKSPACE = "_campaign"  # under the forge data folder: skf-campaign's default workspace
CAMPAIGN_STATE = "_campaign-state.yaml"
CAMPAIGN_TIMEOUT = 60
# Where skf-campaign's status script sits under the project root, in probe order.
CAMPAIGN_STATUS_PROBES = ("_bmad/skf/skf-campaign/scripts/campaign-status.py",
                          "src/skf-campaign/scripts/campaign-status.py")
CAMPAIGN_FINAL_STAGE = 10  # campaign-state.py's FINAL_STAGE: the report stage

# `summary.result` spellings, as the next-code table names them.
VERDICTS = frozenset({"PASS", "FAIL", "INCONCLUSIVE", "PASS_WITH_DRIFT"})
RETEST = frozenset({None, "INCONCLUSIVE", "PASS_WITH_DRIFT"})
# `summary.severity` spellings of an audit that found drift (CLEAN found none).
DRIFT = frozenset({"MINOR", "SIGNIFICANT", "CRITICAL"})


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


def _record_folder(forge_data_folder: Path, name: str, active_version: str) -> Path:
    """The forge folder that holds the active version's test and audit records."""
    folder = forge_data_folder / name
    return folder if active_version == "flat" else folder / active_version


def read_verdict(forge_data_folder: Path, name: str, active_version: str) -> str | None:
    """The settled verdict for the active version, upper case, or None; ValueError on an unreadable file."""
    record = _read_json(_record_folder(forge_data_folder, name, active_version) / TEST_RESULT)
    summary = record.get("summary") if isinstance(record, dict) else None
    result = summary.get("result") if isinstance(summary, dict) else None
    if not isinstance(result, str):
        return None
    verdict = result.strip().upper().replace("-", "_")
    return verdict if verdict in VERDICTS else None


def _timestamp(record) -> datetime | None:
    """A record's `timestamp` as a UTC time, or None when it carries no readable one."""
    value = record.get("timestamp") if isinstance(record, dict) else None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        when = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when.astimezone(timezone.utc)


def _upstream_ref(summary: dict) -> str | None:
    """The ref the audit found upstream moved to, stripped, as pipeline-gate.py's AS gate hands it on, or None."""
    ref = summary.get("upstream_ref")
    return ref.strip() if summary.get("upstream_moved") is True and isinstance(ref, str) and ref.strip() else None


def read_drift(forge_data_folder: Path, name: str, active_version: str) -> tuple[str | None, str | None]:
    """The drift on record for the active version: (severity upper case, the ref upstream moved to or None), or
    (None, None); ValueError on an unreadable audit file.

    The latest audit's severity counts when it found drift and is dated after
    the test record, or when no test record carries a readable `timestamp`.
    """
    folder = _record_folder(forge_data_folder, name, active_version)
    audit = _read_json(folder / AUDIT_RESULT)
    summary = audit.get("summary") if isinstance(audit, dict) else None
    severity = summary.get("severity") if isinstance(summary, dict) else None
    severity = severity.strip().upper() if isinstance(severity, str) else None
    if severity not in DRIFT:
        return None, None  # no audit, or a CLEAN one, upstream moved or not
    try:
        tested = _timestamp(_read_json(folder / TEST_RESULT))
    except ValueError:
        tested = None  # read_verdict names the unreadable test record
    if tested is not None:
        audited = _timestamp(audit)
        if audited is None or audited <= tested:
            return None, None
    return severity, _upstream_ref(summary)


def exported_version(manifest, name: str) -> str | None:
    exports = manifest.get("exports") if isinstance(manifest, dict) else None
    entry = exports.get(name) if isinstance(exports, dict) else None
    version = entry.get("active_version") if isinstance(entry, dict) else None
    return version if isinstance(version, str) and version else None


def skill_status(name: str, active_version: str | None, verdict: str | None, exported: str | None,
                 drift: str | None = None, target_ref: str | None = None) -> dict:
    """One skill's stage and next code, by the tables in the module docstring."""
    if drift is not None:
        nxt = f"US {name} --target-ref {target_ref}" if target_ref else f"US {name}"
    elif verdict == "FAIL":
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
            "exported_version": exported, "drift": drift, "next": nxt}


def _brief_status(name: str) -> dict:
    return {"name": name, "stage": "briefed", "active_version": None, "verdict": None,
            "exported_version": None, "drift": None, "next": f"CS {name}"}


def _unknown_status(name: str) -> dict:
    return {"name": name, "stage": None, "active_version": None, "verdict": None,
            "exported_version": None, "drift": None, "next": None}


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


# --------------------------------------------------------------------------
# An unfinished campaign
# --------------------------------------------------------------------------


def find_campaign_status(project_root: Path | None) -> Path | None:
    """The first campaign-status.py of CAMPAIGN_STATUS_PROBES under the project root, or None."""
    if project_root is None:
        return None
    return next((project_root / p for p in CAMPAIGN_STATUS_PROBES if (project_root / p).is_file()), None)


def run_campaign_status(script: Path | None, state: Path) -> dict:
    """campaign-status.py's tally of the state, through its CLI; ValueError when it cannot give one."""
    if script is None:
        raise ValueError("campaign-status.py not found")
    try:
        done = subprocess.run([sys.executable, str(script), "--state-file", str(state)],
                              capture_output=True, text=True, encoding="utf-8", timeout=CAMPAIGN_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ValueError(f"{script.name} did not run: {e}") from None
    try:
        tally = json.loads(done.stdout) if done.returncode == 0 else None
    except json.JSONDecodeError:
        tally = None
    if isinstance(tally, dict):
        return tally
    # Its own error is one JSON line; a crash prints a traceback, whose last line names the cause.
    lines = [line.strip() for line in done.stderr.splitlines() if line.strip()]
    try:
        error = json.loads(lines[-1]).get("error") if lines else None
    except (json.JSONDecodeError, AttributeError):
        error = None
    if not isinstance(error, str) or not error:
        error = lines[-1] if lines else f"{script.name} printed no JSON (exit {done.returncode})"
    raise ValueError(error)


def campaign_members(state: Path) -> set[str]:
    """The names a campaign's skills go by: each `skills[]` entry's `name` and its `skill_path`'s last part."""
    try:
        import yaml  # only the campaign source reads YAML: every other function runs without pyyaml
    except ImportError:
        raise ValueError("pyyaml is not installed") from None
    try:
        data = yaml.safe_load(state.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
        raise ValueError(f"{state.as_posix()}: {e}") from None
    skills = data.get("skills") if isinstance(data, dict) else None
    members: set[str] = set()
    for skill in skills if isinstance(skills, list) else []:
        if not isinstance(skill, dict):
            continue
        name, path = skill.get("name"), skill.get("skill_path")
        if isinstance(name, str) and name.strip():
            members.add(name.strip())
        if isinstance(path, str) and path.strip():
            last = PurePosixPath(path.strip().replace("\\", "/")).name
            if last:
                members.add(last)
    return members


def _finished(tally: dict) -> bool:
    return tally.get("current_stage") == CAMPAIGN_FINAL_STAGE and not tally.get("pending") and not tally.get("active")


def read_campaign(project_root: Path | None, workspace: Path, warnings: list) -> tuple[dict | None, set[str]]:
    """The unfinished campaign in the workspace, as `campaign` prints it, and its members; (None, set()) else."""
    state = workspace / CAMPAIGN_STATE
    if not state.is_file():
        return None, set()
    try:
        tally = run_campaign_status(find_campaign_status(project_root), state)
        if _finished(tally):
            return None, set()
        members = campaign_members(state)
    except ValueError as e:
        warnings.append(f"campaign_unavailable: {e}")
        return None, set()
    campaign = {"name": tally.get("campaign_name"), "current_stage": tally.get("current_stage"),
                "completed": tally.get("completed"), "total": tally.get("total")}
    return campaign, members


def campaign_only(project_root: Path, forge_data_folder: Path, campaign_workspace: Path | None = None) -> dict:
    """The greeting's campaign check: the unfinished campaign alone, with no inventory and no offer."""
    warnings: list = []
    campaign, _ = read_campaign(project_root, campaign_workspace or forge_data_folder / CAMPAIGN_WORKSPACE, warnings)
    return {"status": "ok", "campaign": campaign, "warnings": warnings}


# --------------------------------------------------------------------------
# The status
# --------------------------------------------------------------------------


def forge_status(skills_output_folder: Path, forge_data_folder: Path, inventory: Path | None, run_root: Path,
                 result_dir: Path, *, project_root: Path | None = None,
                 campaign_workspace: Path | None = None) -> dict:
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
            verdict = drift = target_ref = None
            if isinstance(active, str) and active:
                try:
                    verdict = read_verdict(forge_data_folder, name, active)
                except ValueError as e:
                    warnings.append(f"test_result_unreadable: {e}")
                try:
                    drift, target_ref = read_drift(forge_data_folder, name, active)
                except ValueError as e:
                    warnings.append(f"audit_result_unreadable: {e}")
            entries[name] = skill_status(name, active, verdict, exported_version(scan.get("manifest"), name), drift,
                                         target_ref)
        for name in briefs:
            entries.setdefault(name, _brief_status(name))
    workspace = campaign_workspace or forge_data_folder / CAMPAIGN_WORKSPACE
    campaign, members = read_campaign(project_root, workspace, warnings)
    for name in members & entries.keys():
        entries[name]["next"] = "CA"
    offer = pipeline_offer(run_root, result_dir, forge_data_folder, skills_output_folder, warnings)
    named = offer is not None and offer.get("skill_name") in entries
    if named:
        entries[offer["skill_name"]]["next"] = offer["route"]
    skills = [entries[name] for name in sorted(entries)]
    recommended: list = []
    for value in [s["next"] for s in skills]:
        if value and value not in recommended:
            recommended.append(value)
    if offer is not None and not named and offer.get("route") and offer["route"] not in recommended:
        recommended.append(offer["route"])
    if campaign is not None and "CA" not in recommended:
        recommended.append("CA")  # no listed skill is a member, or an offer's route stands for each that is
    return {"status": "ok", "skills": skills, "pipeline": offer, "campaign": campaign, "recommended": recommended,
            "warnings": warnings}


# Required unless --campaign-only, which reads the campaign alone.
STATUS_ONLY_FLAGS = ("--skills-output-folder", "--run-root", "--result-dir")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forge-status",
        description=(
            "Ferris's WS status: each skill's lifecycle stage (briefed, compiled, tested or exported) "
            "and the next code to run for it, from the briefs, the skill inventory, the test verdicts, "
            "the latest audits, the export manifest, an unfinished campaign and a stopped pipeline's offer."
        ),
    )
    parser.add_argument("--skills-output-folder", help="The skills output folder (required without --campaign-only).")
    parser.add_argument("--forge-data-folder", required=True, help="The forge data folder (briefs, test results).")
    parser.add_argument("--project-root", required=True,
                        help="The project root, under which the shared skf-skill-inventory.py and skf-campaign's "
                             "campaign-status.py are found.")
    parser.add_argument("--inventory",
                        help="The path of skf-skill-inventory.py, in place of the one found under the project root.")
    parser.add_argument("--run-root",
                        help="The folder that holds the pipeline runs' folders (required without --campaign-only).")
    parser.add_argument("--result-dir",
                        help="The folder of the pipeline result files, the sidecar (required without "
                             "--campaign-only).")
    parser.add_argument("--campaign-workspace",
                        help=f"The campaign workspace that holds {CAMPAIGN_STATE} (default: "
                             f"<forge-data-folder>/{CAMPAIGN_WORKSPACE}).")
    parser.add_argument("--campaign-only", action="store_true",
                        help="Print the unfinished campaign alone, with no inventory and no pipeline offer.")
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
    parser = _build_parser()
    args = parser.parse_args(argv)
    workspace = Path(args.campaign_workspace) if args.campaign_workspace else None
    if args.campaign_only:
        result = campaign_only(Path(args.project_root), Path(args.forge_data_folder), workspace)
    else:
        missing = [flag for flag in STATUS_ONLY_FLAGS if getattr(args, flag[2:].replace("-", "_")) is None]
        if missing:
            parser.error(f"the following arguments are required: {', '.join(missing)}")
        inventory = Path(args.inventory) if args.inventory else find_inventory(Path(args.project_root))
        result = forge_status(Path(args.skills_output_folder), Path(args.forge_data_folder), inventory,
                              Path(args.run_root), Path(args.result_dir), project_root=Path(args.project_root),
                              campaign_workspace=workspace)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    _force_utf8(sys.stdout, sys.stderr)
    sys.exit(main())
