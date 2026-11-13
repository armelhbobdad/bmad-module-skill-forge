#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Merge the API-surface summaries of skf-verify-stack (integrations.md §3).

Each skill §3 reads gets one summary: a subagent, or the parent in the
sequential fallback, reads the skill's SKILL.md and writes its compact JSON to
`<dir>/<skill>.json`, the file named for the skill as the inventory names it.
Reading a SKILL.md is judgment; checking each reply's keys, joining the
inventory and counting the read failures against the 20% budget that gates
exit 7 have one correct answer, so they are done here rather than in prose.

merge --dir DIR --inventory FILE --skills a,b,c [--subagent-skills a,b] -o FILE
  --skills names every skill §3 reads, comma-separated; --subagent-skills the
  ones a subagent read (leave it out in the sequential fallback). The names
  are the inventory's, so a skill whose SKILL.md could not be read at all,
  and which left no file, is reported instead of dropped.

Reply contract (one JSON object per file, read as UTF-8, a byte order mark
allowed):
  skill_name             required, a non-empty string
  exports                required, a list of strings
  capabilities           required, a list of strings
  protocols_inferred     a list of strings when present, [] when absent
  data_formats_inferred  a list of strings when present, [] when absent
  Any other key, `language` included, is dropped: the inventory's `language`
  is authoritative. A reply that breaks the contract, a file that is not
  JSON or not an object, and a skill with no file ("no reply") are rejected,
  each with the reason.

Merged record (one per accepted reply, in --skills order):
  {"skill_name": "<the inventory name the file is named for>",
   "language": <the inventory's: a string, a list for a stack, or null>,
   "exports": [...], "protocols_inferred": [...],
   "data_formats_inferred": [...], "capabilities": [...],
   "inventory_exports": [<the inventory's exports>],
   "exports_documented": <the inventory's, a whole number or null>}

-o FILE (written atomically, UTF-8):
  {"summaries": [<merged records>], "unread": ["<each rejected skill>"]}

Output (stdout, one object):
  {"accepted": ["<skill>", ...],
   "rejected": [{"skill": "<skill>", "reason": "<why>"}, ...],
   "malformed_ratio": <rejected subagent skills / --subagent-skills, 0 without>,
   "over_budget": <true when more than 20% of --subagent-skills are rejected>}

  Only the skills a subagent read count toward the budget, so a fallback run
  (no --subagent-skills) never goes over it. The stage re-reads each rejected
  skill once and runs the same merge again before it reads `over_budget`.

Errors (stdout, one object): {"error": "<why>", "code": "<code>"}.

Exit codes:
  0  merged: -o written and the result printed (rejected skills included)
  1  the inventory cannot be read, is not JSON or holds no `skills` list, or
     -o cannot be written (code UNUSABLE_INPUT); nothing is written
  2  a bad call (code INVALID_INPUT): a --skills name the inventory does not
     list, or a --subagent-skills name --skills does not hold; nothing is
     written. argparse usage errors exit 2 too, with usage on stderr and no
     JSON

CLI usage:
  uv run skf-skill-summaries.py merge --dir run/summaries --inventory run/skill-inventory.json \\
      --skills zod,react-query --subagent-skills zod,react-query -o run/skill-summaries.json
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

REQUIRED_LISTS = ("exports", "capabilities")
OPTIONAL_LISTS = ("protocols_inferred", "data_formats_inferred")
# More than this share of the subagent reads still rejected halts the stage
# (exit 7). Compared in integers: 5 * rejected > total.
BUDGET_DENOMINATOR = 5
NO_REPLY = "no reply"


class BadCall(Exception):
    """A call the stage fixes and runs again (exit 2)."""


class Unusable(Exception):
    """An input the stage cannot recover from (exit 1)."""


def _names(value):
    """The names of a comma-separated list, trimmed, empty items and repeats dropped."""
    names = []
    for part in (value or "").split(","):
        name = part.strip()
        if name and name not in names:
            names.append(name)
    return names


def load_inventory(path):
    """The inventory's skill entries by name, or Unusable."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError) as exc:
        raise Unusable(f"cannot read the inventory {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise Unusable(f"the inventory {path} is not JSON: {exc.msg}") from exc
    skills = data.get("skills") if isinstance(data, dict) else None
    if not isinstance(skills, list):
        raise Unusable(f"the inventory {path} holds no `skills` list")
    return {
        entry["name"]: entry
        for entry in skills
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }


def _is_text_list(value):
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def check_reply(reply):
    """The reply's kept fields, or (None, the reason it is rejected)."""
    if not isinstance(reply, dict):
        return None, "the reply is not a JSON object"
    problems = []
    name = reply.get("skill_name")
    if "skill_name" not in reply:
        problems.append("missing key skill_name")
    elif not isinstance(name, str) or not name.strip():
        problems.append("skill_name must be a non-empty string")
    fields = {}
    for key in REQUIRED_LISTS:
        if key not in reply:
            problems.append(f"missing key {key}")
        elif not _is_text_list(reply[key]):
            problems.append(f"{key} must be a list of strings")
        else:
            fields[key] = reply[key]
    for key in OPTIONAL_LISTS:
        if key not in reply:
            fields[key] = []
        elif not _is_text_list(reply[key]):
            problems.append(f"{key} must be a list of strings")
        else:
            fields[key] = reply[key]
    if problems:
        return None, "; ".join(problems)
    return fields, None


def read_reply(path):
    """The parsed reply file, or (None, the reason it cannot be used)."""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return None, NO_REPLY
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"cannot read the reply: {exc}"
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, f"the reply is not JSON: {exc.msg}"


def _record(name, fields, entry):
    exports = entry.get("exports")
    return {
        "skill_name": name,
        "language": entry.get("language"),
        "exports": fields["exports"],
        "protocols_inferred": fields["protocols_inferred"],
        "data_formats_inferred": fields["data_formats_inferred"],
        "capabilities": fields["capabilities"],
        "inventory_exports": exports if isinstance(exports, list) else [],
        "exports_documented": entry.get("exports_documented"),
    }


def merge(directory, inventory, skills, subagent_skills=None):
    """Check each skill's reply and join the inventory.

    Returns (the stdout result, the -o document). Raises BadCall on a name
    the inventory or --skills does not hold.
    """
    subagent_skills = subagent_skills or []
    outside = [name for name in subagent_skills if name not in skills]
    if outside:
        raise BadCall(f"--subagent-skills names {', '.join(outside)}, which --skills does not")
    unknown = [name for name in skills if name not in inventory]
    if unknown:
        raise BadCall(f"--skills names {', '.join(unknown)}, which the inventory does not list")

    summaries, accepted, rejected = [], [], []
    for name in skills:
        reply, reason = read_reply(Path(directory) / f"{name}.json")
        fields = None
        if reason is None:
            fields, reason = check_reply(reply)
        if reason is not None:
            rejected.append({"skill": name, "reason": reason})
            continue
        accepted.append(name)
        summaries.append(_record(name, fields, inventory[name]))

    unread = [entry["skill"] for entry in rejected]
    failed = sum(1 for name in unread if name in subagent_skills)
    total = len(subagent_skills)
    result = {
        "accepted": accepted,
        "rejected": rejected,
        "malformed_ratio": round(failed / total, 4) if total else 0,
        "over_budget": BUDGET_DENOMINATOR * failed > total,
    }
    return result, {"summaries": summaries, "unread": unread}


def _write_atomic(target, content):
    """Write content beside target, then move it into place, so a reader never sees half a file."""
    target = Path(target)
    tmp = target.with_name(f".{target.name}.{secrets.token_hex(4)}.tmp")
    try:
        with open(tmp, "wb") as handle:
            handle.write(content.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


# --- CLI --------------------------------------------------------------------


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="skf-skill-summaries",
        description=(
            "Merge the API-surface summaries of skf-verify-stack (integrations.md "
            "§3): check each <dir>/<skill>.json reply, join the inventory's "
            "language, exports and exports_documented, write the merged records "
            "and the unread skills to -o, and print the accepted and rejected "
            "skills with the 20% budget over the skills a subagent read. Exit 0 "
            "when merged, 1 when the inventory or -o is unusable, 2 on a bad call."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    merge_parser = sub.add_parser(
        "merge",
        help="check the replies, join the inventory and count the budget",
        description="Check each reply, join the inventory and count the budget (see the main --help).",
    )
    merge_parser.add_argument("--dir", required=True, help="the folder of <skill>.json replies")
    merge_parser.add_argument(
        "--inventory", required=True, help="the skill inventory step 1 wrote ({inventoryFile})"
    )
    merge_parser.add_argument(
        "--skills", required=True, help="every skill the stage reads, comma-separated"
    )
    merge_parser.add_argument(
        "--subagent-skills",
        help="the skills a subagent read, comma-separated (leave out in the sequential fallback)",
    )
    merge_parser.add_argument("-o", "--output", required=True, help="the merged summaries file to write")
    return parser


def _error(message, code):
    print(json.dumps({"error": message, "code": code}, indent=2))


def main(argv=None):
    args = _build_parser().parse_args(argv)
    skills = _names(args.skills)
    subagent_skills = _names(args.subagent_skills) if args.subagent_skills is not None else None
    try:
        inventory = load_inventory(args.inventory)
        result, document = merge(args.dir, inventory, skills, subagent_skills)
        try:
            _write_atomic(args.output, json.dumps(document, indent=2, ensure_ascii=False) + "\n")
        except OSError as exc:
            raise Unusable(f"cannot write {args.output}: {exc}") from exc
    except BadCall as exc:
        _error(str(exc), "INVALID_INPUT")
        return 2
    except Unusable as exc:
        _error(str(exc), "UNUSABLE_INPUT")
        return 1
    print(json.dumps(result, indent=2))
    return 0


def _force_utf8(*streams) -> None:
    """Reconfigure the given streams to UTF-8, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which cannot print every character
    a --help text or a skill name may hold.
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
