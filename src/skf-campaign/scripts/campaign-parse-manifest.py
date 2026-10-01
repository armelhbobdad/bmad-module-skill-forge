# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Campaign Parse Manifest: validate every campaign target before the first compile.

step-01 (Setup) takes a campaign's targets from a `--manifest` file, from a
`--brief` campaign-brief.yaml, or from the operator's answer (a pasted list or
repository URLs, rewritten as manifest lines and piped in). Every one of those
sources goes through this script, so a malformed target, a repository URL no
later stage can read, a name no sub-skill accepts, or two targets with one
name stop the campaign at Setup, never part-way through a run. step-01 section
1 documents the manifest format (one `name,repo_url,tier,pin[;dep1,dep2]`
target per line) and this parser is its single source of truth.

Manifest format (one target per line):

    name,repo_url,tier,pin[;dep1,dep2,...]

- `name` may be empty: it is then taken from the repository's name
- `pin` may be empty (latest): `name,repo_url,tier,`  or  `name,repo_url,tier`
- a trailing `;`-segment lists depends_on names (comma-separated)
- blank lines and lines starting with `#` are skipped
- `tier` must be `A` or `B`

Brief format: a campaign-brief.yaml (templates/campaign-brief-template.yaml).
Each `targets[]` entry is checked the same way; `tier` defaults to `A`, `pin`
to null and `depends_on` to [], and every other field a target carries (a
language or scope hint) is kept. `pin` must be a string or null (quote a pin
such as 1.10, which YAML reads as a number), and `quality_gate.soft_target`
and `quality_gate.soft_fallback` must be numbers when the brief gives them.

Every source, each rule taken from the script of the stage that reads it:
- `repo_url` must name a GitHub repository: a URL, an SSH URL or `owner/repo`.
  targets[] carries it as `https://github.com/<owner>/<repo>`, the one shape
  the pin stage (skf-validate-pins.py) and every later stage read; another
  host, or a path inside a repository, is an error
- `name` must be a skill name: lower-case letters, digits and hyphens,
  starting and ending with a letter or digit, at most 64 characters
  (brief-skill's KEBAB_RE, skf-validate-frontmatter.py's length)
- a Tier A `pin` must be an X.Y.Z version (brief-skill's `target_version`
  rule): the pin reaches the Tier A build only as that input
- names are unique (a duplicate is an error, never a silent overwrite)
- `dangling_depends_on` lists each depends_on name that is no target, and
  `tier_inversions` each Tier A target that depends on a Tier B target (the
  strategy stage rejects both, through dependency_problems, which
  campaign-deps.py imports); neither is an error here, so Setup can ask
  about them before it writes state

`--stack-name <state-file>` instead prints the capstone's `stack_name`: the
state's campaign name by the rule that names a target from its repository,
cut so create-stack-skill's `-stack` suffix still fits in 64 characters, or
null when nothing is left of it.

CLI:
  uv run campaign-parse-manifest.py <path/to/manifest.txt>
  cat manifest.txt | uv run campaign-parse-manifest.py -
  uv run campaign-parse-manifest.py --brief <path/to/campaign-brief.yaml>
  uv run campaign-parse-manifest.py --stack-name <path/to/_campaign-state.yaml>

Output (JSON on stdout):
  {"targets": [{"name","repo_url","tier","pin","depends_on", ...}],
   "errors": [{"line" | "target" | "field", "message"}],
   "filled_names": [{"name","repo_url"}],
   "dangling_depends_on": [{"skill","depends_on"}],
   "tier_inversions": [{"skill","depends_on"}]}
  --brief adds "brief": {"campaign_name","quality_gate","architecture_doc_path",
  "notes"} with only the keys the brief gives.
  --stack-name prints {"stack_name": "<name>" | null}.

Exit codes:
  0  parsed cleanly (no errors), or the stack name printed
  1  one or more malformed lines or targets (errors[] populated; targets[]
     omits them)
  2  file error (not found / unreadable / a brief or state that is not a
     YAML mapping)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

BRIEF_KEYS = ("campaign_name", "quality_gate", "architecture_doc_path", "notes")
TARGET_KEYS = ("name", "repo_url", "tier", "pin", "depends_on")
SHARED_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "shared" / "scripts"
STACK_SUFFIX = "-stack"
# An owner or repository segment of a GitHub URL.
SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _shared(file_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(file_name[:-3].replace("-", "_"), SHARED_SCRIPTS / file_name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The rules the later stages apply, read from their own scripts so Setup
# cannot accept a target they refuse.
_PINS = _shared("skf-validate-pins.py")
_BRIEF_INPUTS = _shared("skf-validate-brief-inputs.py")
GITHUB_URL_RE = _PINS._GITHUB_URL_RE
KEBAB_RE = _BRIEF_INPUTS.KEBAB_RE
VERSION_RE = _BRIEF_INPUTS.SEMVER_RE
MAX_NAME = _shared("skf-validate-frontmatter.py").MAX_SKILL_NAME_LENGTH


def canonical_repo_url(repo_url: str) -> Tuple[Optional[str], Optional[str]]:
    """(`https://github.com/<owner>/<repo>`, None) for a GitHub repository, else (None, why not).

    Reads a GitHub URL (http or https, `www.` and `.git` allowed), an SSH URL
    (`git@github.com:o/r` or `ssh://git@github.com/o/r`) and `owner/repo`.
    """
    url = repo_url.strip()
    ssh = re.match(r"^(?:ssh://)?git@([^:/\s]+)[:/](.*)$", url)
    if ssh:
        host, path = ssh.group(1), ssh.group(2)
    else:
        rest = re.sub(r"^https?://", "", url, flags=re.I)
        if "://" in rest:
            return None, f"`repo_url` `{repo_url}` is no GitHub URL: use https://github.com/<owner>/<repo>"
        first, _, path = rest.partition("/")
        if rest != url or "." in first:
            host = first
        else:
            host, path = "github.com", rest
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    if host != "github.com":
        return None, (
            f"`repo_url` `{repo_url}` is not on GitHub: the pin and provenance stages "
            "read GitHub repositories only"
        )
    parts = [p for p in path.strip().strip("/").split("/") if p]
    if parts and parts[-1].lower().endswith(".git"):
        parts[-1] = parts[-1][:-4]
    if len(parts) < 2 or not all(SEGMENT_RE.match(p) and p.strip(".") for p in parts[:2]):
        return None, f"`repo_url` `{repo_url}` names no repository (use a GitHub URL or `owner/repo`)"
    canonical = f"https://github.com/{parts[0]}/{parts[1]}"
    if len(parts) > 2:
        return None, (
            f"`repo_url` `{repo_url}` names a path inside a repository: give the repository "
            f"itself, `{canonical}`"
        )
    if not GITHUB_URL_RE.match(canonical):
        return None, f"`repo_url` `{repo_url}` names no repository (use a GitHub URL or `owner/repo`)"
    return canonical, None


def name_from_repo(repo: str) -> str:
    """A skill name from a repository name: lower case, runs of other characters as `-`."""
    return re.sub(r"[^a-z0-9]+", "-", repo.lower()).strip("-")


def is_skill_name(name: str) -> bool:
    return bool(KEBAB_RE.match(name)) and len(name) <= MAX_NAME


def stack_name(campaign_name: Any) -> Optional[str]:
    """The capstone's stack_name: the campaign name as a skill name, short enough
    for create-stack-skill to append `-stack` within MAX_NAME; None when empty."""
    name = name_from_repo(campaign_name if isinstance(campaign_name, str) else "")
    room = MAX_NAME if name.endswith(STACK_SUFFIX) else MAX_NAME - len(STACK_SUFFIX)
    return name[:room].rstrip("-") or None


def dependency_problems(skills: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, str]]]:
    """Each depends_on name that is no skill, and each Tier A skill that depends on a Tier B skill.

    The one statement of both rules: campaign-deps.py imports it for the
    strategy stage, so Setup and Strategy report the same entries. Tier B
    skills are built in the batch stage, after the skill loop that builds
    Tier A skills, so a Tier A skill could never pass that dependency gate.
    """
    tiers = {s.get("name"): s.get("tier") for s in skills}
    dangling: List[Dict[str, str]] = []
    inversions: List[Dict[str, str]] = []
    for skill in skills:
        for dep in skill.get("depends_on") or []:
            if dep not in tiers:
                dangling.append({"skill": skill.get("name"), "depends_on": dep})
            elif skill.get("tier") == "A" and tiers[dep] == "B":
                inversions.append({"skill": skill.get("name"), "depends_on": dep})
    return {"dangling_depends_on": dangling, "tier_inversions": inversions}


class _Collector:
    """Checks targets one at a time and keeps the results of the whole set."""

    def __init__(self) -> None:
        self.targets: List[Dict[str, Any]] = []
        self.errors: List[Dict[str, Any]] = []
        self.filled: List[Dict[str, str]] = []
        self.seen: set = set()

    def error(self, where: Dict[str, Any], message: str) -> None:
        self.errors.append({**where, "message": message})

    def add(self, where: Dict[str, int], target: Dict[str, Any]) -> None:
        name, repo_url, tier, pin = target["name"], target["repo_url"], target["tier"], target["pin"]
        if not repo_url:
            label = f"`{name}`" if name else "target"
            self.error(where, f"{label} has empty `repo_url`")
            return
        canonical, problem = canonical_repo_url(repo_url)
        if canonical is None:
            self.error(where, problem)
            return
        target["repo_url"] = canonical
        if not name:
            name = name_from_repo(canonical.rsplit("/", 1)[1])
            if not name:
                self.error(where, f"empty `name`, and none can be taken from `{repo_url}`")
                return
            target["name"] = name
            self.filled.append({"name": name, "repo_url": canonical})
        if not is_skill_name(name):
            self.error(where, (
                f"`{name}` is no skill name: use lower-case letters, digits and hyphens, starting "
                f"and ending with a letter or digit, at most {MAX_NAME} characters"
            ))
            return
        if tier not in ("A", "B"):
            self.error(where, f"`{name}` has invalid tier `{tier}` (must be A or B)")
            return
        if tier == "A" and pin is not None and not VERSION_RE.match(pin):
            self.error(where, (
                f"`{name}` is Tier A with pin `{pin}`, which is no X.Y.Z version: brief-skill builds "
                "a Tier A skill from a release version only (write it in full, such as `1.2.0` or "
                "`v1.2.0`, or leave the pin empty for the latest release)"
            ))
            return
        if name in self.seen:
            self.error(where, f"duplicate target name `{name}`")
            return
        self.seen.add(name)
        self.targets.append(target)

    def result(self) -> Dict[str, Any]:
        return {
            "targets": self.targets,
            "errors": self.errors,
            "filled_names": self.filled,
            **dependency_problems(self.targets),
        }


def parse_manifest_text(text: str) -> Dict[str, Any]:
    found = _Collector()

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        body, sep, deps_part = line.partition(";")
        fields = [f.strip() for f in body.split(",")]
        if len(fields) < 3:
            found.error({"line": lineno}, f"expected `name,repo_url,tier[,pin]`, got {len(fields)} field(s)")
            continue

        name, repo_url, tier = fields[0], fields[1], fields[2]
        pin = fields[3] if len(fields) >= 4 and fields[3] != "" else None
        depends_on = [d.strip() for d in deps_part.split(",") if d.strip()] if sep else []
        found.add(
            {"line": lineno},
            {"name": name, "repo_url": repo_url, "tier": tier, "pin": pin, "depends_on": depends_on},
        )

    return found.result()


def _brief_target(found: _Collector, index: int, entry: Any) -> None:
    where = {"target": index}
    if not isinstance(entry, dict):
        found.error(where, "a target must be a mapping with at least `repo_url`")
        return
    name = entry.get("name")
    repo_url = entry.get("repo_url")
    tier = entry.get("tier", "A")
    pin = entry.get("pin")
    depends_on = entry.get("depends_on")
    if name is not None and not isinstance(name, str):
        found.error(where, f"`name` must be a string, got {name!r}")
        return
    if repo_url is not None and not isinstance(repo_url, str):
        found.error(where, f"`repo_url` must be a string, got {repo_url!r}")
        return
    if pin is not None and not isinstance(pin, str):
        found.error(where, f"`pin` must be a string or null, got {pin!r} (quote a version pin)")
        return
    if depends_on is None:
        depends_on = []
    if not isinstance(depends_on, list) or not all(isinstance(d, str) and d.strip() for d in depends_on):
        found.error(where, "`depends_on` must be a list of target names")
        return
    target = {
        "name": (name or "").strip(),
        "repo_url": (repo_url or "").strip(),
        "tier": tier,
        "pin": (pin.strip() or None) if isinstance(pin, str) else None,
        "depends_on": [d.strip() for d in depends_on],
    }
    target.update({k: v for k, v in entry.items() if k not in TARGET_KEYS})
    found.add(where, target)


def parse_brief(brief: Dict[str, Any]) -> Dict[str, Any]:
    found = _Collector()
    targets = brief.get("targets")
    if targets is None:
        targets = []
    if not isinstance(targets, list):
        found.error({"field": "targets"}, "`targets` must be a list")
        targets = []
    for index, entry in enumerate(targets, start=1):
        _brief_target(found, index, entry)

    fields = {k: brief[k] for k in BRIEF_KEYS if k in brief}
    gate = fields.get("quality_gate")
    if gate is not None and not isinstance(gate, dict):
        found.error({"field": "quality_gate"}, "`quality_gate` must be a mapping")
        fields.pop("quality_gate")
    elif isinstance(gate, dict):
        for key in ("soft_target", "soft_fallback"):
            value = gate.get(key)
            if key in gate and (isinstance(value, bool) or not isinstance(value, (int, float))):
                found.error({"field": f"quality_gate.{key}"}, f"`quality_gate.{key}` must be a number, got {value!r}")
    result = found.result()
    result["brief"] = fields
    return result


def _read(path: str) -> tuple:
    p = Path(path)
    if not p.is_file():
        return None, ("MANIFEST_NOT_FOUND", f"Manifest not found: {path}")
    try:
        # utf-8-sig: a byte-order mark an editor wrote is no part of the first name.
        return p.read_text(encoding="utf-8-sig"), None
    except (OSError, UnicodeDecodeError) as exc:
        return None, ("MANIFEST_READ_ERROR", f"Manifest unreadable: {exc}")


def _fail(code: str, message: str) -> int:
    json.dump({"error": message, "code": code}, sys.stderr)
    sys.stderr.write("\n")
    return 2


def _emit(payload: Dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


def run(path: str, brief: bool = False) -> int:
    if path == "-":
        # Bytes as UTF-8, whatever the console's code page (cp1252 on Windows).
        text = sys.stdin.buffer.read().decode("utf-8", errors="replace").lstrip("﻿")
    else:
        text, problem = _read(path)
        if problem:
            code, message = problem
            if brief:
                code, message = code.replace("MANIFEST", "BRIEF"), message.replace("Manifest", "Brief")
            return _fail(code, message)

    if brief:
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            return _fail("BRIEF_PARSE_ERROR", f"Brief is not valid YAML: {exc}")
        if not isinstance(data, dict):
            return _fail("BRIEF_PARSE_ERROR", "Brief is not a YAML mapping")
        result = parse_brief(data)
    else:
        result = parse_manifest_text(text)
    _emit(result)
    return 1 if result["errors"] else 0


def run_stack_name(state_file: str) -> int:
    path = Path(state_file)
    if not path.is_file():
        return _fail("STATE_NOT_FOUND", f"State file not found: {state_file}")
    try:
        state = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        return _fail("STATE_PARSE_ERROR", f"Failed to parse state file: {exc}")
    if not isinstance(state, dict) or not isinstance(state.get("campaign"), dict):
        return _fail("STATE_PARSE_ERROR", "State file has no campaign mapping")
    _emit({"stack_name": stack_name(state["campaign"].get("name"))})
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="campaign-parse-manifest",
        description="Validate campaign targets from a --manifest list or a campaign-brief.yaml, "
        "or print the capstone's stack name from a campaign state.",
    )
    parser.add_argument("path", nargs="?", help="path to manifest text file, or `-` for stdin")
    parser.add_argument("--brief", help="path to a campaign-brief.yaml to validate instead")
    parser.add_argument("--stack-name", dest="stack_state", help="path to _campaign-state.yaml whose campaign name gives the stack name")
    args = parser.parse_args(argv)
    given = [value for value in (args.path, args.brief, args.stack_state) if value is not None]
    if len(given) != 1:
        parser.error("give one of: a manifest path (or `-` for stdin), --brief <file>, or --stack-name <state-file>")
    if args.stack_state is not None:
        return run_stack_name(args.stack_state)
    if args.brief is not None:
        return run(args.brief, brief=True)
    return run(args.path)


if __name__ == "__main__":
    raise SystemExit(main())
