# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Summarize Validation: the score and the issue counts of a skill's validation.

Quick Skill's write-and-validate step runs skill-check, the frontmatter
validator, the output validator and the security scan on the skill package
it wrote, and saves what each prints in its run folder. This helper reads
those files and prints the skill-check quality score, the issue counts the
result contract carries as `validation_issues` and the issues behind each
count, so the step holds no rule for picking a score out of skill-check's
JSON and no counting rule. Test Skill's combine-external-scores.py loads
read_json_object() and quality_score() from this file, so both workflows
read skill-check's score by one rule.

Inputs, each a file path. A file that is missing, or that does not start
(after a byte order mark and whitespace) with a JSON object, is a check that
did not run. Only the object at the start of a file is read, so the
`Wrote <path>` line skill-check prints after its JSON when a project config
sets a report path is ignored.

  --skill-check  skill-check's `check --format json` stdout
  --frontmatter  skf-validate-frontmatter.py's JSON (written when skill-check
                 did not validate)
  --output       skf-validate-output.py's JSON
  --security     skf-security-scan.py's JSON
  --skill-dir    the skill package skill-check checked (required)

Quality score, from the first rule that gives one:

  1. the first `scores[]` entry whose `relativePath` (either separator),
     joined to the current folder and resolved, is <skill-dir>/SKILL.md
     resolved, links followed in both;
  2. the first `scores[]` entry whose `skillId` is the id skill-check 1.2.0
     derives for <skill-dir>/SKILL.md from its absolute path, links
     unresolved (dist/core/artifact.js): `<category>/<slug>`, the segments
     before and after the last `skills` segment of the path when it has one
     on each side, else the names of the skill folder's parent folder and of
     the skill folder;
  3. a top-level `qualityScore`, which older skill-check builds print;
  4. else null.

A score counts only as a number from 0 to 100 that is not a bool: an entry
whose score is anything else gives none, and the next entry, then the next
rule, is read. skill-check writes `relativePath` relative to the folder it
ran in, so run this helper from that folder; the `skillId` rule covers a run
from another folder.

Output (stdout, one JSON object):

  status                ok
  quality_score         the score, or null
  quality_score_source  scores, qualityScore or null
  skill_check           validated (the file holds a JSON object), stopped
                        (the file exists without one: skill-check stopped
                        before it validated) or not-run (there is no file)
  validation_issues     {"skill_md", "context_snippet", "metadata",
                        "security"}, each the number of entries of:
      skill_md          skill-check's `diagnostics[]` when skill_check is
                        validated, else the frontmatter JSON's `issues[]`,
                        plus the output JSON's `validation.skill_md.body[]`
      context_snippet   the output JSON's `validation.context_snippet.issues[]`
      metadata          the output JSON's `validation.metadata.issues[]`
      security          the security JSON's `findings[]`
                        A list that is absent or is not a list (a check that
                        did not run, such as a `{"skipped": ...}` snippet
                        check) counts 0.
  issues                the same four keys, each the list of the entries it
                        counts, in order, as {"check", "severity", "message",
                        "line"}: `check` is skill-check's `ruleId`, the
                        validators' `field` or the scan's `risk`; the scan's
                        message is its `text` and its severity null; `line`
                        is skill-check's, else null.

Exit codes:
  0  a summary was printed, whatever the files hold
  2  usage error (argparse), such as no --skill-dir

CLI (stdlib only):
  uv run skf-summarize-validation.py --skill-dir <skill-package>
      [--skill-check <file>] [--frontmatter <file>] [--output <file>] [--security <file>]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HEADINGS = ("skill_md", "context_snippet", "metadata", "security")
_DECODER = json.JSONDecoder()


def read_json_object(path: str | os.PathLike | None) -> dict | None:
    """The JSON object a file starts with, after a byte order mark and whitespace, or None.

    None when there is no path, the file cannot be read, or it does not start
    with a JSON object. Text after the object is ignored.
    """
    if path is None:
        return None
    try:
        text = Path(path).read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    text = text.lstrip()
    if not text.startswith("{"):
        return None
    try:
        data, _ = _DECODER.raw_decode(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _score(value: object) -> int | float | None:
    """`value` when it is a number from 0 to 100 that is not a bool, else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if 0 <= value <= 100 else None


def _resolved(path: Path) -> str | None:
    """`path` resolved, links followed, in the case form the platform compares by; None on a link loop."""
    try:
        return os.path.normcase(str(path.resolve()))
    except (OSError, RuntimeError):
        return None


def skill_check_id(skill_md: str | os.PathLike) -> str:
    """The `skillId` skill-check 1.2.0 gives a SKILL.md (dist/core/artifact.js deriveCategoryAndSlug).

    Read from the absolute path with links unresolved, as Node's path.resolve gives it.
    """
    absolute = os.path.abspath(os.fspath(skill_md))
    parts = [part for part in absolute.split(os.sep) if part]
    index = len(parts) - 1 - parts[::-1].index("skills") if "skills" in parts else -1
    if index > 0 and index + 1 < len(parts):
        return f"{parts[index - 1]}/{parts[index + 1]}"
    folder = os.path.dirname(absolute)
    return f"{os.path.basename(os.path.dirname(folder))}/{os.path.basename(folder)}"


def quality_score(data: object, skill_dir: str | os.PathLike) -> tuple[int | float | None, str | None]:
    """(score, source) from skill-check's JSON for the skill at `skill_dir`, by the module docstring's rule.

    `source` is "scores", "qualityScore" or None.
    """
    if not isinstance(data, dict):
        return None, None
    skill_md = Path(skill_dir) / "SKILL.md"
    scores = data.get("scores")
    entries = [entry for entry in scores if isinstance(entry, dict)] if isinstance(scores, list) else []
    target = _resolved(skill_md)
    for entry in entries:
        rel = entry.get("relativePath")
        if (isinstance(rel, str) and rel and target is not None
                and _resolved(Path.cwd() / rel.replace("\\", "/")) == target):
            score = _score(entry.get("score"))
            if score is not None:
                return score, "scores"
    skill_id = skill_check_id(skill_md)
    for entry in entries:
        if entry.get("skillId") == skill_id:
            score = _score(entry.get("score"))
            if score is not None:
                return score, "scores"
    score = _score(data.get("qualityScore"))
    if score is not None:
        return score, "qualityScore"
    return None, None


def _list(data: object, *keys: str) -> list:
    """The list at `keys` under `data`, or [] when a key is absent or the value is not a list."""
    for key in keys:
        if not isinstance(data, dict):
            return []
        data = data.get(key)
    return data if isinstance(data, list) else []


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _line(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _issue(entry: object, check_key: str, message_key: str = "message", with_severity: bool = True,
           with_line: bool = False) -> dict:
    entry = entry if isinstance(entry, dict) else {}
    return {
        "check": _text(entry.get(check_key)),
        "severity": _text(entry.get("severity")) if with_severity else None,
        "message": _text(entry.get(message_key)),
        "line": _line(entry.get("line")) if with_line else None,
    }


def summarize(skill_check: str | None, frontmatter: str | None, output: str | None, security: str | None,
              skill_dir: str) -> dict:
    """The summary main prints, from the four saved outputs."""
    checked = read_json_object(skill_check)
    if checked is not None:
        state = "validated"
    elif skill_check is not None and os.path.lexists(skill_check):
        state = "stopped"
    else:
        state = "not-run"
    score, source = quality_score(checked, skill_dir)
    validated = read_json_object(output)
    if state == "validated":
        skill_md = [_issue(d, "ruleId", with_line=True) for d in _list(checked, "diagnostics")]
    else:
        skill_md = [_issue(i, "field") for i in _list(read_json_object(frontmatter), "issues")]
    skill_md += [_issue(i, "field") for i in _list(validated, "validation", "skill_md", "body")]
    issues = {
        "skill_md": skill_md,
        "context_snippet": [_issue(i, "field") for i in _list(validated, "validation", "context_snippet", "issues")],
        "metadata": [_issue(i, "field") for i in _list(validated, "validation", "metadata", "issues")],
        "security": [_issue(f, "risk", message_key="text", with_severity=False)
                     for f in _list(read_json_object(security), "findings")],
    }
    return {
        "status": "ok",
        "quality_score": score,
        "quality_score_source": source,
        "skill_check": state,
        "validation_issues": {heading: len(issues[heading]) for heading in HEADINGS},
        "issues": issues,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-summarize-validation",
        description="Print the skill-check quality score, the validation issue counts and the issues behind "
                    "them, from the saved outputs of Quick Skill's validators.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--skill-check", metavar="FILE", help="skill-check's `check --format json` stdout")
    parser.add_argument("--frontmatter", metavar="FILE", help="skf-validate-frontmatter.py's JSON")
    parser.add_argument("--output", metavar="FILE", help="skf-validate-output.py's JSON")
    parser.add_argument("--security", metavar="FILE", help="skf-security-scan.py's JSON")
    parser.add_argument("--skill-dir", metavar="DIR", required=True, help="the skill package skill-check checked")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    summary = summarize(args.skill_check, args.frontmatter, args.output, args.security, args.skill_dir)
    sys.stdout.write(json.dumps(summary, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
