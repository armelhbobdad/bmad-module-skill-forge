# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Campaign Quality Gate: the campaign's quality bar, applied by one script.

The campaign holds a quality gate (`campaign.quality_gate` in state: `hard`,
`soft_target`, `soft_fallback`), and the directive's `## Quality Overrides`
and `## Skip List` sections adjust it while the campaign runs. Which gate a
skill gets, whether a test result settles it, and which completed skills
clear the gate each have one right answer, so they are computed here and the
step files read the result.

Precedence, highest first: the directive's Quality Overrides (a line for one
skill beats a campaign-wide line), then the gate in state, which `check`
settled at step-01 from a campaign brief's `quality_gate` and the
customize.toml values.

Subcommands:

  check     Settle and validate the gate step-01 writes to state: each of
            `hard`, `soft_target` and `soft_fallback` from the brief's
            `quality_gate` (--brief-file) when it gives one, else from the
            customize.toml values passed in. `hard` must be
            `zero-critical-high` (test-skill's own hard gate, the only one
            there is); `soft_target` and `soft_fallback` are numbers from 0
            to 100, the fallback not above the target.
  resolve   One Tier A skill's run at step-05: whether the directive's Skip
            List names it, the threshold its test run gets (`threshold`, the
            effective `soft_target`) and, with --brief-file, the inputs
            brief-skill takes for it (`brief_skill`: `target_repo` from the
            brief, `target_version` the skill's pin, the brief target's
            language and scope hints), so no step reads them out of prose.
  record    Settle a Tier A skill from the SKF_TEST_RESULT_JSON line its
            test run printed (stdin, or the file --result names). Only the
            verdict PASS completes the skill; FAIL, INCONCLUSIVE,
            pass-with-drift, an error envelope and a missing or unreadable
            line fail it, with the reason. test-skill already applied the
            threshold, its caps and its 80% floor fallback, so no score is
            compared here.
  classify  Classify every completed skill against its effective gate for
            the step-10 export: `pass` (score at or above soft_target),
            `fallback` (at or above soft_fallback) or `fail` (below it, or
            no score at all). Only pass and fallback skills export. A Tier A
            score is test-skill's; a Tier B score is the skill-check score
            quick-skill records, not a test-skill score. Each row's
            `export_name` is the skill folder skf-export-skill resolves: the
            last part of the `skill_path` the build recorded
            (`{skills_output_folder}/{skill-name}/{version}/{skill-name}`),
            which quick-skill names after the library for a Tier B skill,
            else the campaign name.

Directive format (a section runs to the next heading of level 1 or 2; each
entry is one list item, backticks around a name are dropped):

  ## Quality Overrides
  - soft_target: 85                         campaign-wide
  - soft_fallback: 75                       campaign-wide
  - cognee: soft_target 80, soft_fallback 70  for one skill

  ## Skip List
  - cognee: upstream is mid-rewrite         a reason after a colon, a dash
  - legacy-lib                              or in parentheses is optional

A list item in these sections that does not read this way is returned in
`unparsed[]`, never dropped silently: a Quality Overrides item with any other
text, or that names a key twice, is unparsed and none of its numbers apply. A
directive path that names no file means no directive.

CLI:
  uv run campaign-quality-gate.py check --hard <value> --soft-target <N> --soft-fallback <N> [--brief-file <p>]
  uv run campaign-quality-gate.py resolve --state-file <p> --skill <name> [--directive-file <p>] [--brief-file <p>]
  uv run campaign-quality-gate.py record --skill <name> [--result <p>]   (stdin otherwise)
  uv run campaign-quality-gate.py classify --state-file <p> [--directive-file <p>]

Output (one JSON object on stdout):
  check:    {"hard", "soft_target", "soft_fallback"}
  resolve:  {"skill", "skip", "skip_reason", "hard", "soft_target",
             "soft_fallback", "threshold", "overrides": [...],
             "unparsed": [...], "warnings": [...]}, and with --brief-file
             "brief_skill": {"target_repo", "skill_name", "target_version",
             "language_hint", "scope_hint"} (null when the skill has none)
  record:   {"skill", "status": "completed|failed", "verdict",
             "quality_score", "threshold", "threshold_fallback", "reason"}
  classify: {"gate": {...}, "skills": [{"name", "tier", "skill_path",
             "export_name", "quality_score", "soft_target", "soft_fallback",
             "verdict", "reason"}],
             "export": [...], "excluded": [{"name", "tier", "quality_score",
             "verdict", "reason"}], "counts": {"pass", "fallback", "fail"},
             "unparsed": [...], "warnings": [...]}

Exit codes:
  0  result printed (for record, read `status`)
  2  error, as {"error", "code"} on stderr: STATE_NOT_FOUND,
     STATE_PARSE_ERROR, SKILL_NOT_FOUND, DIRECTIVE_UNREADABLE,
     RESULT_NOT_FOUND, BRIEF_NOT_FOUND, BRIEF_UNREADABLE (missing, or not a
     YAML mapping), TARGET_NOT_FOUND (the brief has no target with a
     repo_url for the skill), or INVALID_GATE (with `errors[]`: an
     unsupported hard gate, a soft value outside 0 to 100, a fallback above
     the target, from the brief, in state or after the directive's overrides)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

HARD_GATES = ("zero-critical-high",)
SOFT_KEYS = ("soft_target", "soft_fallback")
GATE_KEYS = ("hard", *SOFT_KEYS)
# Each brief-skill hint and the brief target fields it is read from, in order.
HINT_FIELDS = {"language_hint": ("language_hint", "language"), "scope_hint": ("scope_hint", "scope")}

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*\S)\s*$")
PAIR_RE = re.compile(r"\b(soft_target|soft_fallback)\b\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*%?", re.I)
# The whole override text: one or more PAIR_RE pairs separated by commas, nothing else.
PAIRS_RE = re.compile(
    r"(?:soft_target|soft_fallback)\b\s*[:=]?\s*-?\d+(?:\.\d+)?\s*%?"
    r"(?:\s*,\s*(?:soft_target|soft_fallback)\b\s*[:=]?\s*-?\d+(?:\.\d+)?\s*%?)*",
    re.I,
)
SKILL_LINE_RE = re.compile(r"^([^\s:]+)\s*:\s*(.+)$")
SKIP_NAME_RE = re.compile(r"^([^\s:(]+)(.*)$")
TS_PREFIX = "SKF_TEST_RESULT_JSON:"
ANY_ENVELOPE_RE = re.compile(r"SKF_[A-Z_]+_RESULT_JSON:")


class GateError(Exception):
    """A failure the CLI reports as {"error", "code"} on stderr with exit 2."""

    def __init__(self, message: str, code: str, **extra: Any) -> None:
        super().__init__(message)
        self.code = code
        self.extra = extra


def _number(text: str) -> int | float:
    value = float(text)
    return int(value) if value.is_integer() else value


def _plain(value: Any) -> Any:
    """A whole float as an int, so a threshold of 90.0 prints as 90."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


# --------------------------------------------------------------------------
# Directive
# --------------------------------------------------------------------------


def _sections(text: str) -> dict[str, list[tuple[int, str]]]:
    """The list items of each level-2 section, keyed by lower-case title."""
    sections: dict[str, list[tuple[int, str]]] = {}
    current: list[tuple[int, str]] | None = None
    for lineno, line in enumerate(text.splitlines(), start=1):
        heading = HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            if level <= 2:
                title = " ".join(heading.group(2).split()).lower()
                current = sections.setdefault(title, []) if level == 2 else None
            continue
        if current is not None:
            item = ITEM_RE.match(line)
            if item:
                current.append((lineno, item.group(1).replace("`", "").strip()))
    return sections


def parse_directive(text: str) -> dict[str, Any]:
    """Read the Skip List and Quality Overrides sections of a directive."""
    sections = _sections(text)
    skip: dict[str, str | None] = {}
    campaign: dict[str, int | float] = {}
    skills: dict[str, dict[str, int | float]] = {}
    unparsed: list[dict[str, Any]] = []

    for lineno, entry in sections.get("skip list", []):
        match = SKIP_NAME_RE.match(entry)
        if not match:
            unparsed.append({"section": "Skip List", "line": lineno, "text": entry})
            continue
        rest = match.group(2).strip()
        if rest.startswith("(") and rest.endswith(")"):
            rest = rest[1:-1]
        skip[match.group(1)] = re.sub(r"^\W+", "", rest).strip() or None

    for lineno, entry in sections.get("quality overrides", []):
        first = entry.split(None, 1)[0].rstrip(":=").lower()
        per_skill = SKILL_LINE_RE.match(entry)
        if first in SOFT_KEYS:
            name, text = None, entry
        elif per_skill:
            name, text = per_skill.group(1), per_skill.group(2)
        else:
            name, text = None, ""
        # Only the documented grammar applies: other text or a repeated key
        # leaves the whole item unparsed, so no stray number becomes the gate.
        pairs = PAIR_RE.findall(text) if PAIRS_RE.fullmatch(text) else []
        if len({key.lower() for key, _ in pairs}) < len(pairs):
            pairs = []
        if not pairs:
            unparsed.append({"section": "Quality Overrides", "line": lineno, "text": entry})
            continue
        target = campaign if name is None else skills.setdefault(name, {})
        for key, value in pairs:
            target[key.lower()] = _number(value)

    return {"skip": skip, "campaign": campaign, "skills": skills, "unparsed": unparsed}


def read_directive(path: str | None) -> dict[str, Any]:
    """The parsed directive, or an empty one when no path is given or no file is there."""
    if not path or not Path(path).is_file():
        return parse_directive("")
    try:
        text = Path(path).read_bytes().decode("utf-8", errors="replace").lstrip("\ufeff")
    except OSError as exc:
        raise GateError(f"Directive unreadable: {exc}", "DIRECTIVE_UNREADABLE") from exc
    return parse_directive(text)


def _unknown_name_warnings(directive: dict[str, Any], names: set[str]) -> list[str]:
    warnings = []
    for name in directive["skip"]:
        if name not in names:
            warnings.append(f"Skip List names `{name}`, which is no skill in this campaign")
    for name in directive["skills"]:
        if name not in names:
            warnings.append(f"Quality Overrides names `{name}`, which is no skill in this campaign")
    return warnings


# --------------------------------------------------------------------------
# Gate
# --------------------------------------------------------------------------


def gate_errors(gate: dict[str, Any]) -> list[str]:
    """Why a gate cannot be applied, or [] when it can."""
    errors = []
    hard = gate.get("hard")
    if hard not in HARD_GATES:
        errors.append(
            f"hard gate `{hard}` is not supported: the only hard gate is `zero-critical-high`, "
            "the Critical and High gap check test-skill runs on every skill"
        )
    in_range = []
    for key in SOFT_KEYS:
        value = gate.get(key)
        if _is_number(value) and 0 <= value <= 100:
            in_range.append(key)
        else:
            errors.append(f"`{key}` must be a number from 0 to 100, got {value!r}")
    if len(in_range) == 2 and gate["soft_fallback"] > gate["soft_target"]:
        errors.append(
            f"`soft_fallback` {_plain(gate['soft_fallback'])} is above "
            f"`soft_target` {_plain(gate['soft_target'])}"
        )
    return errors


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def effective_gate(
    base: dict[str, Any], directive: dict[str, Any], skill: str | None = None
) -> tuple[dict[str, Any], list[str]]:
    """The gate after the directive's overrides, and one line per override applied."""
    gate = {"hard": base.get("hard"), **{key: base.get(key) for key in SOFT_KEYS}}
    applied = []
    for key, value in directive["campaign"].items():
        gate[key] = value
        applied.append(f"directive Quality Overrides: {key} {value}")
    if skill is not None:
        for key, value in directive["skills"].get(skill, {}).items():
            gate[key] = value
            applied.append(f"directive Quality Overrides for {skill}: {key} {value}")
    return gate, applied


def _checked(gate: dict[str, Any], applied: list[str]) -> dict[str, Any]:
    errors = gate_errors(gate)
    if errors:
        where = f" (after {'; '.join(applied)})" if applied else ""
        raise GateError(f"The quality gate{where} cannot be applied: " + "; ".join(errors),
                        "INVALID_GATE", errors=errors)
    return {key: _plain(value) for key, value in gate.items()}


def _load_brief(path: str) -> dict[str, Any]:
    if not Path(path).is_file():
        raise GateError(f"Brief not found: {path}", "BRIEF_NOT_FOUND")
    try:
        brief = yaml.safe_load(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise GateError(f"Brief unreadable: {exc}", "BRIEF_UNREADABLE") from exc
    if not isinstance(brief, dict):
        raise GateError(f"Brief is not a YAML mapping: {path}", "BRIEF_UNREADABLE")
    return brief


def _load_state(path: str) -> dict[str, Any]:
    if not Path(path).is_file():
        raise GateError(f"State file not found: {path}", "STATE_NOT_FOUND")
    try:
        state = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise GateError(f"Failed to parse state file: {exc}", "STATE_PARSE_ERROR") from exc
    if not isinstance(state, dict) or not isinstance(state.get("skills"), list):
        raise GateError("State file is not a campaign state (no skills[] list)", "STATE_PARSE_ERROR")
    campaign = state.get("campaign")
    if not isinstance(campaign, dict) or not isinstance(campaign.get("quality_gate"), dict):
        raise GateError("State file has no campaign.quality_gate", "INVALID_GATE",
                        errors=["campaign.quality_gate is missing"])
    return state


# --------------------------------------------------------------------------
# Subcommands
# --------------------------------------------------------------------------


def check(hard: str, soft_target: str, soft_fallback: str, brief: dict[str, Any] | None = None) -> dict[str, Any]:
    gate: dict[str, Any] = {"hard": hard}
    for key, raw in (("soft_target", soft_target), ("soft_fallback", soft_fallback)):
        try:
            gate[key] = _number(raw)
        except ValueError:
            gate[key] = raw
    applied = []
    brief_gate = (brief or {}).get("quality_gate")
    if brief_gate is not None and not isinstance(brief_gate, dict):
        raise GateError("The brief's quality_gate is not a mapping", "INVALID_GATE",
                        errors=["the brief's quality_gate must be a mapping"])
    for key in GATE_KEYS:
        if (brief_gate or {}).get(key) is not None:
            gate[key] = brief_gate[key]
            applied.append(f"campaign brief: {key} {brief_gate[key]}")
    return _checked(gate, applied)


def _hint(target: dict[str, Any], fields: tuple[str, ...]) -> str | None:
    for field in fields:
        value = target.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def brief_skill_inputs(state: dict[str, Any], brief: dict[str, Any], skill: str) -> dict[str, Any]:
    """The inputs brief-skill takes for one skill: its repository and hints from the
    brief, its pin from state (the step-01 parser accepts only an X.Y.Z Tier A pin)."""
    target = next(
        (t for t in brief.get("targets") or [] if isinstance(t, dict) and t.get("name") == skill), None
    )
    repo_url = (target or {}).get("repo_url")
    if not isinstance(repo_url, str) or not repo_url.strip():
        raise GateError(f"The campaign brief has no target with a repo_url for skill '{skill}'",
                        "TARGET_NOT_FOUND")
    entry = next(s for s in state["skills"] if isinstance(s, dict) and s.get("name") == skill)
    pin = entry.get("pin")
    return {
        "target_repo": repo_url.strip(),
        "skill_name": skill,
        "target_version": str(pin) if pin not in (None, "") else None,
        **{hint: _hint(target, fields) for hint, fields in HINT_FIELDS.items()},
    }


def resolve(
    state: dict[str, Any], directive: dict[str, Any], skill: str, brief: dict[str, Any] | None = None
) -> dict[str, Any]:
    names = {s.get("name") for s in state["skills"] if isinstance(s, dict)}
    if skill not in names:
        raise GateError(f"Skill '{skill}' not found in state", "SKILL_NOT_FOUND")
    gate, applied = effective_gate(state["campaign"]["quality_gate"], directive, skill)
    gate = _checked(gate, applied)
    skipped = skill in directive["skip"]
    extra = {} if brief is None else {"brief_skill": brief_skill_inputs(state, brief, skill)}
    return {
        "skill": skill,
        "skip": skipped,
        "skip_reason": directive["skip"][skill] if skipped else None,
        **gate,
        "threshold": gate["soft_target"],
        "overrides": applied,
        "unparsed": directive["unparsed"],
        "warnings": _unknown_name_warnings(directive, names),
        **extra,
    }


def _envelope(text: str) -> tuple[dict[str, Any] | None, str | None]:
    """The last test-skill envelope in `text`, or None and why there is none."""
    text = text.lstrip("\ufeff")
    lines = [line for line in text.splitlines() if TS_PREFIX in line]
    if lines:
        payload = lines[-1].split(TS_PREFIX, 1)[1].strip()
    elif not text.strip():
        return None, "no-result"
    elif ANY_ENVELOPE_RE.search(text):
        return None, "not-a-test-result"
    else:
        payload = text.strip()
    try:
        envelope = json.loads(payload)
    except json.JSONDecodeError:
        return None, "result-unreadable"
    if not isinstance(envelope, dict):
        return None, "result-unreadable"
    return envelope, None


def record(skill: str, text: str) -> dict[str, Any]:
    envelope, problem = _envelope(text)
    out: dict[str, Any] = {
        "skill": skill,
        "status": "failed",
        "verdict": None,
        "quality_score": None,
        "threshold": None,
        "threshold_fallback": False,
        "reason": problem,
    }
    if envelope is None:
        return out

    verdict = envelope.get("verdict")
    if isinstance(verdict, str):
        verdict = {"PASS_WITH_DRIFT": "pass-with-drift"}.get(verdict.upper(), verdict)
        if verdict.upper() in ("PASS", "FAIL", "INCONCLUSIVE"):
            verdict = verdict.upper()
    score = envelope.get("score")
    out.update(
        verdict=verdict,
        quality_score=_plain(score) if _is_number(score) else None,
        threshold=_plain(envelope["threshold"]) if _is_number(envelope.get("threshold")) else None,
        threshold_fallback=envelope.get("threshold_fallback") is True,
    )

    named = envelope.get("skill_name")
    if isinstance(named, str) and named and named != skill:
        out["reason"] = f"result-for-another-skill: {named}"
    elif envelope.get("status") == "error":
        out["reason"] = envelope.get("halt_reason") or verdict or "error"
    elif verdict == "PASS":
        route = envelope.get("next_workflow")
        if route in (None, "export-skill"):
            out.update(status="completed", reason=None)
        else:
            out["reason"] = f"PASS routed to {route}"
    elif verdict in ("FAIL", "INCONCLUSIVE", "pass-with-drift"):
        out["reason"] = verdict
    else:
        out["reason"] = f"unknown-verdict: {verdict}"
    return out


def export_name(skill: dict[str, Any]) -> Any:
    """The skill folder skf-export-skill resolves for a completed skill: the
    last part of the package path its build recorded, else its campaign name."""
    path = skill.get("skill_path")
    if isinstance(path, str) and path.strip():
        return PurePosixPath(path.strip().replace("\\", "/")).name or skill.get("name")
    return skill.get("name")


def classify(state: dict[str, Any], directive: dict[str, Any]) -> dict[str, Any]:
    base = state["campaign"]["quality_gate"]
    names = {s.get("name") for s in state["skills"] if isinstance(s, dict)}
    rows: list[dict[str, Any]] = []
    for skill in state["skills"]:
        if not isinstance(skill, dict) or skill.get("status") != "completed":
            continue
        name = skill.get("name")
        gate = _checked(*effective_gate(base, directive, name))
        score = skill.get("quality_score")
        if not _is_number(score):
            verdict, reason = "fail", "no quality score to check against the gate"
        elif score >= gate["soft_target"]:
            verdict, reason = "pass", None
        elif score >= gate["soft_fallback"]:
            verdict, reason = "fallback", f"below soft_target {gate['soft_target']}"
        else:
            verdict, reason = "fail", f"below soft_fallback {gate['soft_fallback']}"
        rows.append({
            "name": name,
            "tier": skill.get("tier"),
            "skill_path": skill.get("skill_path"),
            "export_name": export_name(skill),
            "quality_score": _plain(score) if _is_number(score) else None,
            "soft_target": gate["soft_target"],
            "soft_fallback": gate["soft_fallback"],
            "verdict": verdict,
            "reason": reason,
        })
    return {
        "gate": _checked(*effective_gate(base, directive)),
        "skills": rows,
        "export": [r["name"] for r in rows if r["verdict"] in ("pass", "fallback")],
        "excluded": [
            {key: r[key] for key in ("name", "tier", "quality_score", "verdict", "reason")}
            for r in rows if r["verdict"] == "fail"
        ],
        "counts": {v: sum(1 for r in rows if r["verdict"] == v) for v in ("pass", "fallback", "fail")},
        "unparsed": directive["unparsed"],
        "warnings": _unknown_name_warnings(directive, names),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _emit(payload: dict[str, Any], stream: Any) -> None:
    stream.write(json.dumps(payload, separators=(",", ":")) + "\n")


def _read_result(path: str | None) -> str:
    if path is None:
        return sys.stdin.buffer.read().decode("utf-8", errors="replace")
    if not Path(path).is_file():
        raise GateError(f"Result file not found: {path}", "RESULT_NOT_FOUND")
    return Path(path).read_bytes().decode("utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="campaign-quality-gate",
        description="Apply the campaign quality gate: check it, resolve it per skill, "
        "settle a test result, classify completed skills for export.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="validate a quality gate before it is written to state")
    p_check.add_argument("--hard", required=True)
    p_check.add_argument("--soft-target", required=True)
    p_check.add_argument("--soft-fallback", required=True)
    p_check.add_argument("--brief-file", help="campaign brief whose quality_gate wins field by field")

    p_resolve = sub.add_parser("resolve", help="one skill's gate and Skip List entry")
    p_resolve.add_argument("--state-file", required=True)
    p_resolve.add_argument("--skill", required=True)
    p_resolve.add_argument("--directive-file")
    p_resolve.add_argument("--brief-file", help="campaign brief: adds the brief-skill inputs (brief_skill)")

    p_record = sub.add_parser("record", help="settle a skill from its SKF_TEST_RESULT_JSON line")
    p_record.add_argument("--skill", required=True)
    p_record.add_argument("--result", help="file holding the envelope line (default: stdin)")

    p_classify = sub.add_parser("classify", help="classify completed skills for export")
    p_classify.add_argument("--state-file", required=True)
    p_classify.add_argument("--directive-file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "check":
            brief = _load_brief(args.brief_file) if args.brief_file else None
            result = check(args.hard, args.soft_target, args.soft_fallback, brief)
        elif args.command == "resolve":
            state = _load_state(args.state_file)
            brief = _load_brief(args.brief_file) if args.brief_file else None
            result = resolve(state, read_directive(args.directive_file), args.skill, brief)
        elif args.command == "record":
            result = record(args.skill, _read_result(args.result))
        else:
            result = classify(_load_state(args.state_file), read_directive(args.directive_file))
    except GateError as exc:
        _emit({"error": str(exc), "code": exc.code, **exc.extra}, sys.stderr)
        return 2
    _emit(result, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
