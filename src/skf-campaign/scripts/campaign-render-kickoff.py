# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Campaign Render Kickoff: render the per-skill kickoff message, every slot.

step-05 emits a kickoff message per Tier-A skill. Each placeholder is data the
campaign already holds, so this script fills all of them and step-05 presents
the output as it is. Re-typing them for each of 15+ skills cost output tokens
and risked paraphrasing or cutting the operator's directive.

  - From state and brief: campaign name, stage, quality gate, skill identity,
    repo, pin, commit and the dependency-status table.
  - {{workarounds_list}}: one bullet per workaround the pre-apply helper
    applied, read from its log (--workarounds-file, the preapply-log.json
    skf-preapply.py writes): the file it changed, the fingerprint and its
    fix, and the severity. Without the file, the skill's workarounds_applied
    from state.
  - {{brief_summary}}: the skill's target entry in the campaign brief, every
    field it carries (a language or scope hint included).
  - {{directive_content}}: the directive file byte for byte, whatever its
    encoding, or "No directive configured" when --directive-file is absent or
    names no file.
  - {{persistent_facts}}: one bullet per persistent fact, or "None". An entry
    `file:<path-or-glob>` adds the content of each file it names, with
    `{project-root}` replaced by --project-root; any other entry is a fact
    sentence.

CLI:
  uv run campaign-render-kickoff.py --state-file <p> --brief-file <p> \
      --skill <name> --template <p> [--workarounds-file <preapply-log.json>] \
      [--facts-json '<json-list>' | --facts-json -] [--project-root <p>] \
      [--directive-file <p>]

  `--facts-json -` reads the facts from stdin: a JSON list, or the object the
  customization resolver prints for `--key workflow.persistent_facts`.

Output: the rendered kickoff markdown on stdout, as UTF-8 bytes. The template
is filled in one pass, so a `{{...}}` inside the directive or a fact is kept
as written.

Exit codes:
  0  rendered
  2  error, as {"error", "code"} on stderr:
       STATE_NOT_FOUND, BRIEF_NOT_FOUND, TEMPLATE_NOT_FOUND
                             the input file is missing
       STATE_UNREADABLE, BRIEF_UNREADABLE, TEMPLATE_UNREADABLE
                             it cannot be read as UTF-8 text
       PARSE_ERROR          state or brief is not a YAML mapping
       SKILL_NOT_FOUND       the skill is not in state
       BAD_WORKAROUNDS       --workarounds-file cannot be read, or holds no
                             applied[] list of workarounds
       BAD_FACTS             --facts-json is not a list of strings (nor the
                             resolver's object), --project-root is not a
                             directory, or a `file:` entry keeps a placeholder
       FACTS_FILE_NOT_FOUND  a `file:` path with no glob character names no
                             file (a glob that matches nothing adds no fact)
       FACTS_UNREADABLE      a facts file cannot be read
       DIRECTIVE_UNREADABLE  the directive file cannot be read
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

NO_DIRECTIVE = "No directive configured"
NO_FACTS = "None"
FILE_PREFIX = "file:"
PROJECT_ROOT = "{project-root}"
# The key the customization resolver prints for --key workflow.persistent_facts
# (it prints {} when no layer sets it).
RESOLVER_KEY = "workflow.persistent_facts"
GLOB_CHARS = ("*", "?", "[")
# Target fields shown first, in this order; any other field of the entry
# follows in the entry's own order.
BRIEF_FIELDS = ("name", "repo_url", "tier", "pin", "depends_on")
SLOT_RE = re.compile(r"\{\{[a-z_]+\}\}")
# A placeholder left in a `file:` entry would match no file.
UNRESOLVED_RE = re.compile(r"\{[A-Za-z][\w-]*\}")


def _err(message: str, code: str) -> int:
    json.dump({"error": message, "code": code}, sys.stderr)
    sys.stderr.write("\n")
    return 2


def _quality_gate_summary(qg: Dict[str, Any]) -> str:
    return (
        f"Hard: {qg.get('hard', 'N/A')} | "
        f"Soft: {qg.get('soft_target', 'N/A')} (fallback: {qg.get('soft_fallback', 'N/A')})"
    )


def _dependency_status_table(skill: Dict[str, Any], skill_map: Dict[str, Dict[str, Any]]) -> str:
    deps = skill.get("depends_on", []) or []
    if not deps:
        return "No dependencies."
    rows = ["| Dependency | Status |", "|------------|--------|"]
    for dep in deps:
        status = skill_map.get(dep, {}).get("status", "unknown")
        rows.append(f"| {dep} | {status} |")
    return "\n".join(rows)


def _code(text: Any) -> str:
    """Inline code that survives a backtick inside the text."""
    text = str(text)
    return f"`` {text} ``" if "`" in text else f"`{text}`"


def _workaround(entry: Any) -> str:
    """One applied workaround: a pre-apply log entry, or a string from state."""
    if not isinstance(entry, dict):
        return str(entry)
    line = f"{_code(entry.get('fingerprint', ''))} replaced with {_code(entry.get('fix', ''))}"
    if entry.get("file"):
        line = f"{entry['file']}: {line}"
    if entry.get("severity"):
        line += f" ({entry['severity']} severity)"
    return line


def _workarounds_list(workarounds: List[Any]) -> str:
    if not workarounds:
        return "None"
    return "\n".join(f"- {_workaround(w)}" for w in workarounds)


def read_workarounds(path: str) -> List[Any]:
    """The applied[] list of a pre-apply log. Raises ValueError on any other file."""
    try:
        log = json.loads(Path(path).read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    applied = log.get("applied") if isinstance(log, dict) else None
    if not isinstance(applied, list):
        raise ValueError(f"{path} holds no applied[] list")
    return applied


def _field_value(key: str, value: Any) -> str:
    if value is None or value == "" or value == []:
        return "latest" if key == "pin" else "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _brief_summary(skill_name: str, target: Optional[Dict[str, Any]]) -> str:
    if not target:
        return f"The campaign brief has no target entry for `{skill_name}`."
    keys = [k for k in BRIEF_FIELDS if k in target] + [k for k in target if k not in BRIEF_FIELDS]
    return "\n".join(f"- `{key}`: {_field_value(key, target[key])}" for key in keys)


def _bullet(text: str) -> str:
    """One markdown bullet; a fact of several lines continues indented under it."""
    first, *rest = text.strip().splitlines()
    lines = [f"- {first}"] + [f"  {line}" if line.strip() else "" for line in rest]
    return "\n".join(lines)


def _facts_list(facts: List[str]) -> str:
    bullets = [_bullet(fact) for fact in facts if fact.strip()]
    return "\n".join(bullets) if bullets else NO_FACTS


def _fact_files(entry: str, pattern: str, root: str) -> List[Path]:
    """The files a `file:` entry names: the path itself, else every file its glob matches.

    `{project-root}` in the pattern becomes root, escaped where it joins a glob.
    A path with no glob character that names no file raises FileNotFoundError,
    so a mistyped path stops the kickoff instead of dropping its facts; a glob
    that matches nothing adds no file.
    """
    path = Path(pattern.replace(PROJECT_ROOT, root))
    if path.is_file():
        return [path]
    if not any(c in pattern for c in GLOB_CHARS):
        raise FileNotFoundError(f"`{entry}` names no file ({path.as_posix()})")
    matches = glob.glob(pattern.replace(PROJECT_ROOT, glob.escape(root)), recursive=True)
    return [Path(p) for p in sorted(matches) if Path(p).is_file()]


def load_facts(entries: List[str], project_root: Optional[str] = None) -> List[str]:
    """Turn persistent-facts entries into the facts the kickoff lists.

    A `file:` entry adds one fact per file it names, headed by the file's
    path. Raises ValueError on an entry that keeps a placeholder (as
    `{project-root}` does when project_root is None), FileNotFoundError on a
    path that names no file, OSError on a file that cannot be read.
    """
    facts: List[str] = []
    for entry in entries:
        if not entry.startswith(FILE_PREFIX):
            facts.append(entry)
            continue
        pattern = entry[len(FILE_PREFIX):].strip()
        left = pattern if project_root is None else pattern.replace(PROJECT_ROOT, "")
        placeholder = UNRESOLVED_RE.search(left)
        if placeholder:
            hint = "; pass --project-root" if placeholder.group(0) == PROJECT_ROOT else ""
            raise ValueError(f"`{entry}` holds the unresolved placeholder `{placeholder.group(0)}`{hint}")
        for path in _fact_files(entry, pattern, project_root or ""):
            text = path.read_bytes().decode("utf-8", errors="replace")
            facts.append(f"From `{path.as_posix()}`:\n\n{text}")
    return facts


def read_directive(path: Optional[str]) -> Optional[str]:
    """The directive file's text exactly as stored, or None when no file is there.

    A byte that is not UTF-8 is kept as a surrogate, which _write_stdout turns
    back into the same byte, so a directive in another encoding comes through
    unchanged.
    """
    if not path or not Path(path).is_file():
        return None
    return Path(path).read_bytes().decode("utf-8", errors="surrogateescape")


def render_kickoff(
    state: Dict[str, Any],
    brief: Dict[str, Any],
    skill_name: str,
    template: str,
    workarounds: Optional[List[Any]] = None,
    directive: Optional[str] = None,
    facts: Optional[List[str]] = None,
) -> str:
    campaign = state.get("campaign", {})
    skills = state.get("skills", [])
    skill_map = {s["name"]: s for s in skills}
    if skill_name not in skill_map:
        raise KeyError(f"Skill '{skill_name}' not found in state")
    skill = skill_map[skill_name]

    targets = {t.get("name"): t for t in (brief.get("targets") or []) if isinstance(t, dict)}
    target = targets.get(skill_name)
    repo_url = (target or {}).get("repo_url", "")

    wa = workarounds if workarounds is not None else (skill.get("workarounds_applied", []) or [])

    values = {
        "{{campaign_name}}": str(campaign.get("name", "")),
        "{{current_stage}}": str(campaign.get("current_stage", "")),
        "{{quality_gate_summary}}": _quality_gate_summary(campaign.get("quality_gate", {})),
        "{{skill_name}}": skill_name,
        "{{skill_tier}}": str(skill.get("tier", "")),
        "{{pin}}": skill.get("pin") or "latest",
        "{{commit_sha}}": skill.get("commit_sha") or "unknown",
        "{{repo_url}}": repo_url,
        "{{workarounds_list}}": _workarounds_list(wa),
        "{{dependency_status_table}}": _dependency_status_table(skill, skill_map),
        "{{brief_summary}}": _brief_summary(skill_name, target),
        "{{persistent_facts}}": _facts_list(facts or []),
        "{{directive_content}}": NO_DIRECTIVE if directive is None else directive,
    }
    # One pass: a filled-in value is never searched again.
    return SLOT_RE.sub(lambda m: values.get(m.group(0), m.group(0)), template)


def _facts_entries(raw: str) -> List[Any]:
    """The entries a --facts-json value holds: a JSON list, or the resolver's object."""
    if not raw.strip():
        raise ValueError("it is empty (with -, the command piped into stdin printed nothing)")
    value = json.loads(raw)
    if isinstance(value, dict) and set(value) <= {RESOLVER_KEY}:
        value = value.get(RESOLVER_KEY, [])
    if not isinstance(value, list):
        raise ValueError(f"not a list, nor an object holding `{RESOLVER_KEY}`")
    return value


def _read_stdin() -> str:
    """stdin as UTF-8, the encoding the resolver writes; a byte-order mark is dropped."""
    buffer = getattr(sys.stdin, "buffer", None)
    if buffer is None:
        return sys.stdin.read()
    return buffer.read().decode("utf-8-sig")


def _write_stdout(text: str) -> None:
    """Write UTF-8 bytes as they are, so no platform rewrites the directive's line endings.

    A surrogate read_directive kept for a byte that is not UTF-8 becomes that byte again.
    """
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        sys.stdout.write(text)
        return
    sys.stdout.flush()
    buffer.write(text.encode("utf-8", errors="surrogateescape"))
    buffer.flush()


def run(
    state_file: str,
    brief_file: str,
    skill: str,
    template_file: str,
    workarounds_file: Optional[str],
    facts_json: Optional[str] = None,
    directive_file: Optional[str] = None,
    project_root: Optional[str] = None,
) -> int:
    texts: Dict[str, str] = {}
    for label, p in (("State", state_file), ("Brief", brief_file), ("Template", template_file)):
        if not Path(p).is_file():
            return _err(f"{label} file not found: {p}", f"{label.upper()}_NOT_FOUND")
        try:
            texts[label] = Path(p).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return _err(f"{label} file unreadable: {p}: {exc}", f"{label.upper()}_UNREADABLE")

    try:
        state = yaml.safe_load(texts["State"])
        brief = yaml.safe_load(texts["Brief"])
    except yaml.YAMLError as exc:
        return _err(f"Failed to parse YAML: {exc}", "PARSE_ERROR")
    if not isinstance(state, dict) or not isinstance(brief, dict):
        return _err("State and brief must each be a YAML mapping", "PARSE_ERROR")

    workarounds: Optional[List[Any]] = None
    if workarounds_file:
        try:
            workarounds = read_workarounds(workarounds_file)
        except ValueError as exc:
            return _err(f"--workarounds-file: {exc}", "BAD_WORKAROUNDS")

    entries: List[Any] = []
    if facts_json:
        try:
            entries = _facts_entries(_read_stdin() if facts_json == "-" else facts_json)
        except ValueError as exc:
            return _err(f"--facts-json must be a JSON list of strings: {exc}", "BAD_FACTS")
        if not all(isinstance(e, str) for e in entries):
            return _err("--facts-json must be a JSON list of strings: an entry is not a string", "BAD_FACTS")
    if project_root is not None and (not project_root.strip() or not Path(project_root).is_dir()):
        return _err(f"--project-root is not a directory: '{project_root}'", "BAD_FACTS")
    try:
        facts = load_facts(entries, project_root)
    except ValueError as exc:
        return _err(f"--facts-json: {exc}", "BAD_FACTS")
    except FileNotFoundError as exc:
        return _err(f"Persistent facts file not found: {exc}", "FACTS_FILE_NOT_FOUND")
    except OSError as exc:
        return _err(f"Persistent facts file unreadable: {exc}", "FACTS_UNREADABLE")

    try:
        directive = read_directive(directive_file)
    except OSError as exc:
        return _err(f"Directive file unreadable: {directive_file}: {exc}", "DIRECTIVE_UNREADABLE")

    try:
        rendered = render_kickoff(state, brief, skill, texts["Template"], workarounds, directive, facts)
    except KeyError as exc:
        return _err(str(exc), "SKILL_NOT_FOUND")

    _write_stdout(rendered if rendered.endswith("\n") else rendered + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="campaign-render-kickoff",
        description="Render the campaign kickoff template for one skill, every placeholder filled.",
    )
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--brief-file", required=True)
    parser.add_argument("--skill", required=True, help="skill name (must exist in state)")
    parser.add_argument("--template", required=True, dest="template_file")
    parser.add_argument(
        "--workarounds-file",
        help="the pre-apply log (preapply-log.json) whose applied[] workarounds the kickoff lists",
    )
    parser.add_argument(
        "--facts-json",
        help="persistent facts as a JSON list of sentences and file:<path-or-glob> entries, or - to "
        "read them from stdin (a list, or the resolver's output for --key workflow.persistent_facts)",
    )
    parser.add_argument(
        "--project-root",
        help="project root that replaces {project-root} in file: entries",
    )
    parser.add_argument(
        "--directive-file",
        help="directive file to inline byte for byte (absent or missing: 'No directive configured')",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(
        args.state_file,
        args.brief_file,
        args.skill,
        args.template_file,
        args.workarounds_file,
        args.facts_json,
        args.directive_file,
        args.project_root,
    )


def _force_utf8(*streams) -> None:
    """Reconfigure stdout and stderr to UTF-8, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which cannot print every character
    a directive or a fact may hold.
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
