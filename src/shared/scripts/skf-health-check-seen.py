# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Health Check Seen: the fingerprints of a health-check finding, the
seen-issue cache that every SKF workflow on the machine shares, and the SKF
version a report names.

src/shared/health-check.md, the last step of every SKF workflow, files a
finding as a GitHub issue once per defect on a machine and reports a fixed
defect that comes back as a regression. This helper owns the deterministic
part of that: the workflow and step file in one form whatever the install,
the section slug from its heading and the defect key from a name, the two
hashes, the tolerant read of the cache, the bounded check of a recorded
issue's state, the verdict and the line a regression's issue opens with, the
locked merge-write of a record, and the installed SKF version. The step keeps
the judgment: whether a finding is real, its severity, which section and
which thing it names, the user's pick at a matching issue, and the rest of
the issue's wording.

CLI:

  uv run skf-health-check-seen.py fingerprint --severity <bug|friction|gap> \\
      --workflow <skf-name> --step-file <path> \\
      (--stdin | --section <slug> --defect-key <key>)
  uv run skf-health-check-seen.py lookup --fp <fp> --legacy-fp <fp> \\
      [--repo <[HOST/]OWNER/REPO>] [--cache <path>]
  uv run skf-health-check-seen.py record --fp <fp> \\
      --action <created|reacted|commented|resolved> --issue-url <url> \\
      --date <YYYY-MM-DD> [--regression] [--cache <path>]
  uv run skf-health-check-seen.py version

--cache is $HOME/.skf/health-check-seen.json (Path.home()) by default. The
step passes none, so every workflow reads and writes the same file.

Every file this helper reads besides the cache it finds from its own place:
the SKF module root is the folder two levels up (src/ in a checkout or a
plugin, _bmad/skf/ when installed), never {project-root}.

fingerprint
-----------
  fp         "fp-" and the first 7 hex characters of
             sha1("{severity}|{workflow}|{step_file}|{section}|{defect_key}"),
             taken over the UTF-8 bytes with no newline (the tuple)
  legacy_fp  the same hash without "|{defect_key}": the section fingerprint,
             which SKF versions without the defect key used as the
             fingerprint and which every defect of one severity in one
             section shares

The hashed fields take one form whatever the install, so a finding reported
from a checkout, a CLI install or a plugin gets one fingerprint:

  workflow   one of the 15 workflow folders whose references/health-check.md
             loads shared/health-check.md (WORKFLOWS: every skf-* folder but
             skf-forger), as written there: skf-test-skill, never test-skill
             or Test Skill
  step_file  src/<workflow>/references/<file>.md. --step-file may be the
             file's name, references/<file>.md, its src/ path, its installed
             _bmad/skf/ path or an absolute one: only its last component is
             kept, and it must be, letter case included, the name of a file
             in the module's <workflow>/references/ folder. It may not be
             health-check.md in any letter case (the relay that only loads
             this step), and when the folder above references/ in the path
             is another SKF skill's, the step file is that skill's: the
             workflow is the one whose references/ folder holds the step
             file, so a step file one workflow loads from another's
             references/ is that other workflow's.

The section comes from a --stdin section_heading or from --section, never
both, and the defect key from a --stdin defect_name or from --defect-key,
never both; each pair is checked on its own, so a --stdin object may hold
one key while the other value is a flag. --stdin reads one JSON object, as
UTF-8, holding only those keys, each a non-empty string.

  section_heading: a heading of the step file, outside its frontmatter and
    fenced code, as the file writes it or in any form that gives the same
    slug (another letter case, other punctuation). Its slug: drop the
    leading `#`s and a leading numbering token (`1.`, `5a.`, `5a-ii.`,
    `4-headless.`), lower-case, turn each run of characters that are not
    ASCII letters or digits into `-`, and trim hyphens. A heading whose slug
    is empty, or no heading of the step file gives, exits 2.
  defect_name: drop surrounding whitespace, backticks and quotes, keep its
    last path component (after `/` or `\\`), drop a trailing `:N`, `:N-M`
    or `:N:M` line suffix, a known file extension (KNOWN_EXTENSIONS) and
    then leading dashes and underscores; split at whitespace, `_`, `-`, `.`
    and each lower-case letter followed by an upper-case one; drop each
    character that is not an ASCII letter or digit; lower-case; keep the
    last four words, joined by `-`. `scripts/gate_eval.py:42` gives
    `gate-eval`, `composeStories` gives `compose-stories`.
  --section <slug>: kebab-case (^[a-z0-9]+(-[a-z0-9]+)*$), with no heading
    check. --defect-key <key>: one to four such words
    (^[a-z0-9]+(-[a-z0-9]+){0,3}$). These flags stay for tests and old
    calls.

Each value must keep its rule, else exit 2 naming it: the severity is bug,
friction or gap; the workflow, the step file, the JSON object and its keys,
the heading and the name (it yields a word) as above; the step file holds
no "|" and no line break.

  Output: {"fp": "fp-a54e7a6", "legacy_fp": "fp-eb2d6f2",
           "tuple": <fp's sha1 input>, "step_file": "src/skf-.../...md",
           "section_slug": ..., "defect_key": ...}

lookup
------
Reads the cache. A file that is missing, empty, unreadable, not UTF-8, not
JSON or not a JSON object is an empty cache, never an error. With --repo, a
record whose issue_url is not a string under https://github.com/OWNER/REPO/
(https://HOST/OWNER/REPO/ for a --repo that names a host), compared in any
letter case, counts as no record under either fingerprint, before gh runs:
another repository's issue, a URL that is not https:// or one that is not a
string alike. A record that is not an object, or whose issue_url is empty or
missing, names no repository and decides as without --repo. --repo must be
[HOST/]OWNER/REPO.

The record under --fp decides; only when the cache has no --fp key does the
record under --legacy-fp decide. On the record found, the first branch that
matches gives the verdict:

  1. no record under either fingerprint: unseen
  2. "action" is "resolved" (recorded once the defect was fixed):
     regression
  3. "action" is created, reacted or commented, and "issue_url" is set: the
     issue's own state decides, read with
     `gh issue view <issue_url> --json state,stateReason`, stopped after 10
     seconds (GH_TIMEOUT_SEC). State CLOSED with stateReason COMPLETED, or
     state MERGED (a resolving pull request), is regression. Every other
     answer (OPEN, a NOT_PLANNED or DUPLICATE close) and every failure (no
     gh, the time limit, a non-zero exit, output that is not that JSON) is
     handled. gh runs only for an issue_url that starts with https:// and
     holds no whitespace; any other value counts as a failure.
  4. one of those three actions with "issue_url" empty or absent: handled
  5. no "action", any other action, or a record that is not an object:
     unrecognized

A record found only under --legacy-fp may be another defect's, so two
verdicts change: handled becomes unseen (a legacy record never
suppresses) and regression becomes possible-regression. unrecognized
stays.

opening_line is the line a regression's issue body carries, null for every
other verdict. U is the record's issue_url when it starts with https:// and
holds no whitespace, D its date when that has the YYYY-MM-DD shape (else "on
an unrecorded date"), and P, after a possible-regression, ": that report's
fingerprint has no defect key, so it may be another defect in this section".
From a resolved record, whose date is the fix's:

  regression, with U:           Regression of U (resolved D).
  regression, without:          Regression of a previously resolved local
                                finding (resolved D).
  possible-regression, with U:  Possibly a regression of U (resolved D)P.
  possible-regression, without: Possibly a regression of a previously
                                resolved local finding in this section
                                (resolved D).

From branch 3, whose record dates the report, not the fix: "Regression of U,
closed as completed since its report on D." ("merged" for a merge), and
"Possibly a regression of U, ... on D" then P and "." after a legacy record.

  Output: {"verdict": "unseen" | "handled" | "regression"
                      | "possible-regression" | "unrecognized",
           "record": <the record found, as the cache holds it> | null,
           "matched_on": "fp" | "legacy_fp" | null,
           "opening_line": <the line> | null}

handled is the only verdict that suppresses a report.

record
------
Sets the --fp key alone to {"issue_url": ..., "action": ..., "date": ...}
and keeps every other key as it read them, records under a legacy
fingerprint included. --action is one of the three this workflow writes
(created, reacted, commented), with an --issue-url that starts with https://
and holds no whitespace, or resolved, which a maintainer records once the
defect is fixed, with such a URL (the issue or the pull request that fixed
it) or an empty one. --date is a real YYYY-MM-DD date.

A "resolved" record under --fp is never downgraded: it is replaced by one of
the three other actions only with --regression, which the step passes once a
regression verdict is followed by an open issue that tracks the recurrence:
the new issue it filed (created), or the matching one the user reacted or
commented on. Without it nothing is written and "written" is false. A
resolved record replaces any record, and a record that is not resolved is
set with or without --regression.

The read, merge and write run while this call holds <cache>.lock, taken
through skf-run-lock.py's acquire_within() and release() (the sibling in
this folder) as skf-forge-tier-rw.py does: a lock older than 15 seconds
(LOCK_STALE_SEC) was left by a killed call and is replaced, an empty lock
file at once (empty_is_stale), and the call waits up to 10 seconds
(LOCK_WAIT_SEC) for another one to finish. The parent folder is created.
The new file is written beside the cache, synced to disk and renamed over
it (on Windows the rename is retried while another process has the cache
open), so no reader sees it half written. A cache that exists and is not
a JSON object is first renamed to <cache>.corrupt-<UTC YYYYMMDDTHHMMSSZ>
(with -2, -3 and so on after a first one in the same second), so the
records in it can still be repaired by hand; when that rename fails,
nothing is written. An empty file is an empty cache.

  Output: {"written": true | false, "fp": ...,
           "record": <what the cache now holds under --fp>,
           "set_aside": <the path the corrupt cache was renamed to> | null}

version
-------
The version of the SKF this helper belongs to, first hit wins:

  1. the first line of VERSION in the module root (the installer writes
     _bmad/skf/VERSION)
  2. package.json in the folder above it, when its name is
     bmad-module-skill-forge (a checkout, or a plugin, which is one), read
     with skf-render-quick-metadata.py's probe_skf_version (the sibling in
     this folder)
  3. .claude-plugin/marketplace.json there, when its name is
     bmad-module-skill-forge: plugins[0].version

A file that is missing, unreadable or malformed, or gives no version or the
sentinel "unknown", falls through to the next. A sibling that cannot be
loaded gives no version.

  Output: {"version": "11.0.0", "source": "VERSION" | "package.json"
                                          | ".claude-plugin/marketplace.json"}
          or {"version": null, "source": "N/A"} when nothing gives one or
          the sibling cannot be loaded. Always exit 0.

No network and no gh call in fingerprint, record or version.

Exit codes (1 and 2 print one JSON line on stderr, {"status": "error",
"message": ...}, and nothing on stdout):
  0  answered
  1  record could not take the lock, read the cache, set a corrupt one
     aside or write it
  2  a bad argument: a missing or unknown one, or a value that breaks its
     rule
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import secrets
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

SEVERITIES = ("bug", "friction", "gap")
# The actions this workflow writes; each suppresses while its issue is live.
WRITTEN_ACTIONS = ("created", "reacted", "commented")
RESOLVED = "resolved"
ACTIONS = (*WRITTEN_ACTIONS, RESOLVED)

# The workflows whose references/health-check.md loads shared/health-check.md: every skf-* folder of the module
# but skf-forger, the agent. A literal list, so the fingerprint's workflow field never depends on what a folder holds.
WORKFLOWS = (
    "skf-analyze-source",
    "skf-audit-skill",
    "skf-brief-skill",
    "skf-campaign",
    "skf-create-skill",
    "skf-create-stack-skill",
    "skf-drop-skill",
    "skf-export-skill",
    "skf-quick-skill",
    "skf-refine-architecture",
    "skf-rename-skill",
    "skf-setup",
    "skf-test-skill",
    "skf-update-skill",
    "skf-verify-stack",
)
# The module's skill folders: a step file path that names one but the finding's workflow is another skill's file.
SKILL_FOLDERS = frozenset((*WORKFLOWS, "skf-forger"))
# Each workflow's relay: it only loads shared/health-check.md, so no finding is ever its own.
RELAY = "health-check.md"

# Each rule is matched with fullmatch: `$` alone would let a value that ends in a newline through.
SECTION_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
DEFECT_KEY_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+){0,3}")
FP_RE = re.compile(r"fp-[0-9a-f]{7}")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
URL_PREFIX = "https://"
# A repository as gh takes it: [HOST/]OWNER/REPO.
REPO_RE = re.compile(r"(?:[A-Za-z0-9][A-Za-z0-9.-]*/)?[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+")

# An ATX heading line: up to three spaces, one to six `#`, then its text.
_HEADING_LINE_RE = re.compile(r" {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*")
# The optional closing sequence of an ATX heading (`## Title ##`).
_HEADING_CLOSE_RE = re.compile(r"(?:^|[ \t]+)#+$")
# A fence line opens or closes a fenced code block, whose `#` lines are no headings.
_FENCE_RE = re.compile(r" {0,3}(`{3,}|~{3,})")
# A leading numbering token: `1.`, `5a.`, `0.5.`, `5a-ii.`, `4-headless.`.
_NUMBERING_RE = re.compile(r"[0-9][0-9A-Za-z]*(?:[.-][0-9A-Za-z]+)*\.\s+")
_NOT_SLUG_RE = re.compile(r"[^a-z0-9]+")

# The file extensions a defect name drops: `gate_eval.py` names the script `gate-eval`.
KNOWN_EXTENSIONS = (
    ".py", ".md", ".json", ".yaml", ".yml", ".toml", ".js", ".cjs", ".mjs", ".ts", ".sh", ".csv", ".txt",
)
_PATH_SEP_RE = re.compile(r"[/\\]")
_LINE_SUFFIX_RE = re.compile(r":[0-9]+(?:[-:][0-9]+)?$")
# What a name copied from Markdown or a log may be wrapped in.
_NAME_WRAPPERS = "`'\""
_NAME_SPLIT_RE = re.compile(r"[\s_.-]+")
_CASE_BOUNDARY_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")
_NOT_ALNUM_RE = re.compile(r"[^A-Za-z0-9]")
DEFECT_KEY_WORDS = 4
STDIN_KEYS = ("section_heading", "defect_name")
# The record date an opening line names when the record holds no YYYY-MM-DD date.
UNRECORDED_DATE = "on an unrecorded date"

GH_TIMEOUT_SEC = 10.0
LOCK_STALE_SEC = 15.0
LOCK_WAIT_SEC = 10.0
CORRUPT_STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
# Windows refuses to rename over a file another process has open (a lookup
# reading the cache, a virus scanner); the rename is retried for this long.
_IS_WINDOWS = os.name == "nt"
_REPLACE_WAIT_SECONDS = 5.0
_REPLACE_POLL_SECONDS = 0.02

HERE = Path(__file__).resolve().parent
# src/ in a checkout or a plugin, _bmad/skf/ when installed: where the workflow folders are.
MODULE_ROOT = HERE.parent.parent
SOURCE_TREE_HELPER = HERE / "skf-source-tree.py"
RUN_LOCK_HELPER = HERE / "skf-run-lock.py"
QUICK_METADATA_HELPER = HERE / "skf-render-quick-metadata.py"
# The name a package.json or marketplace.json above the module root must carry to give the version.
PACKAGE_NAME = "bmad-module-skill-forge"
# What probe_skf_version returns when it finds no version.
UNKNOWN_VERSION = "unknown"

_SIBLINGS: dict[str, object] = {}


class UsageError(Exception):
    """A value that breaks its rule (exit 2)."""


class WriteError(Exception):
    """record could not take the lock, read the cache, set a corrupt one aside or write it (exit 1)."""


def _load(path: Path):
    """A sibling script loaded by its path, once."""
    module = _SIBLINGS.get(path.name)
    if module is None:
        spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SIBLINGS[path.name] = module
    return module


def default_cache() -> Path:
    return Path.home() / ".skf" / "health-check-seen.json"


# --------------------------------------------------------------------------
# fingerprint: the fields in one form
# --------------------------------------------------------------------------


def _check_field(name: str, value: str) -> None:
    if not value:
        raise UsageError(f"{name} must not be empty")
    if "|" in value or "\n" in value or "\r" in value:
        raise UsageError(f"{name} must hold no '|' and no line break, got {value!r}")


def _check_workflow(workflow: str) -> None:
    if workflow not in WORKFLOWS:
        raise UsageError(f"--workflow must be the folder name of one of the {len(WORKFLOWS)} SKF workflows that end "
                         f"in the health check, {', '.join(WORKFLOWS)}, got {workflow!r}")


def step_file_path(workflow: str, step_file: str) -> tuple[str, Path]:
    """(the step file's hashed form, its path in this module). Raises UsageError for a file not of the workflow."""
    _check_field("--step-file", step_file)
    parts = [part for part in _PATH_SEP_RE.split(step_file.strip()) if part]
    if not parts:
        raise UsageError(f"--step-file names no file, got {step_file!r}")
    name = parts[-1]
    if name.lower() == RELAY:
        raise UsageError(f"--step-file {step_file!r} is {workflow}'s health-check relay, which only loads "
                         f"shared/health-check.md: give the step file whose instruction bit, or the one that was "
                         f"running when a defect in SKILL.md, a script or a shared file bit")
    # Only the folder that holds references/ names the step file's skill; a folder further up is the user's.
    owner = parts[-3] if len(parts) >= 3 and parts[-2] == "references" else None
    if owner in WORKFLOWS and owner != workflow:
        raise UsageError(f"--step-file {step_file!r} is in {owner}/references/, so --workflow is {owner}: the workflow "
                         f"whose references/ folder holds the step file")
    if owner in SKILL_FOLDERS and owner != workflow:
        raise UsageError(f"--step-file {step_file!r} is in {owner}/references/, which ends in no health check: "
                         f"--step-file is a file of the references/ folder of one of the workflows")
    references = MODULE_ROOT / workflow / "references"
    try:
        listing = set(os.listdir(references))
    except OSError:
        listing = set()
    path = references / name
    # The listing, not is_file() alone: a file system that ignores letter case would take a wrong-cased name.
    if name not in listing or not path.is_file():
        raise UsageError(f"--step-file {step_file!r} is no file of {workflow}/references/: --workflow is the workflow "
                         f"whose references/ folder holds the step file")
    return f"src/{workflow}/references/{name}", path


def _heading_text(text: str) -> str:
    """A heading's text: no leading `#`s, no ATX closing sequence, single spaces."""
    text = text.strip().lstrip("#")
    text = _HEADING_CLOSE_RE.sub("", text.strip())
    return " ".join(text.split())


def _stage_headings(step_file: Path) -> list[str]:
    """The text of every ATX heading line of step_file, outside its frontmatter and fenced code.

    Raises OSError or UnicodeDecodeError when the file cannot be read.
    """
    lines = step_file.read_text(encoding="utf-8-sig").splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                start = i + 1
                break
    headings = []
    fence = None
    for line in lines[start:]:
        run = _FENCE_RE.match(line)
        if fence is not None:
            # Only a run of the same character, at least as long and alone on its line, closes it.
            closes = run and run.group(1)[0] == fence[0] and len(run.group(1)) >= len(fence)
            if closes and not line.strip().strip(fence[0]):
                fence = None
            continue
        if run:
            fence = run.group(1)
        elif _HEADING_LINE_RE.fullmatch(line):
            headings.append(_heading_text(line))
    return headings


def section_slug(heading: str) -> str:
    """The slug rule: no leading `#`s or numbering token, lower-case, one `-` per run of other characters."""
    text = _heading_text(heading)
    numbering = _NUMBERING_RE.match(text)
    if numbering:
        text = text[numbering.end():]
    return _NOT_SLUG_RE.sub("-", text.lower()).strip("-")


def defect_key(name: str) -> str:
    """The defect-key rule; an empty string when the name yields no word."""
    text = name.strip().strip(_NAME_WRAPPERS).strip()  # `gate_eval.py`, in backticks or quotes
    text = _PATH_SEP_RE.split(text)[-1]  # `scripts/gate_eval.py` names `gate_eval.py`
    text = _LINE_SUFFIX_RE.sub("", text)  # `gate_eval.py:42`, `:42-50` and `:42:7` name it too
    for ext in KNOWN_EXTENSIONS:
        if text.lower().endswith(ext) and len(text) > len(ext):
            text = text[: -len(ext)]
            break
    text = text.lstrip("-_")
    words = []
    for part in _NAME_SPLIT_RE.split(text):
        for piece in _CASE_BOUNDARY_RE.split(part):
            word = _NOT_ALNUM_RE.sub("", piece).lower()
            if word:
                words.append(word)
    return "-".join(words[-DEFECT_KEY_WORDS:])


def read_stdin_names(raw: bytes) -> dict:
    """The {"section_heading", "defect_name"} object --stdin reads, as UTF-8. Raises UsageError for anything else."""
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, RecursionError):  # UnicodeDecodeError is a ValueError
        raise UsageError("--stdin did not read a JSON object") from None
    if not isinstance(data, dict):
        raise UsageError("--stdin did not read a JSON object")
    unknown = sorted(set(data) - set(STDIN_KEYS))
    if unknown:
        raise UsageError(f"unknown --stdin key(s) {', '.join(map(repr, unknown))}; expected only "
                         f"{' and '.join(STDIN_KEYS)}")
    for key, value in data.items():
        if not isinstance(value, str) or not value.strip():
            raise UsageError(f"--stdin {key} must be a non-empty string")
    return data


def _one_of(flag: str, flag_value: str | None, key: str, names: dict) -> None:
    """A section or defect given twice, or not at all, breaks its rule."""
    if flag_value is not None and key in names:
        raise UsageError(f"give {flag} or a --stdin {key}, not both")
    if flag_value is None and key not in names:
        raise UsageError(f"give {flag} or a --stdin {key}")


# --------------------------------------------------------------------------
# fingerprint
# --------------------------------------------------------------------------


def _sha7(text: str) -> str:
    try:
        data = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise UsageError(f"the fingerprint fields must be valid UTF-8: {exc}") from None
    return hashlib.sha1(data).hexdigest()[:7]


def fingerprint(severity: str, workflow: str, step_file: str, section: str | None = None, key: str | None = None,
                names: dict | None = None) -> dict:
    """The fingerprints of one finding and the fields they hash. Raises UsageError for a value that breaks its rule.

    `section` and `key` are --section and --defect-key. `names` is the object --stdin read: its section_heading
    stands for `section` and its defect_name for `key`, each pair given one way only.
    """
    names = names or {}
    if severity not in SEVERITIES:
        raise UsageError(f"--severity must be one of {', '.join(SEVERITIES)}, got {severity!r}")
    _check_workflow(workflow)
    hashed_step_file, path = step_file_path(workflow, step_file)
    _one_of("--section", section, "section_heading", names)
    _one_of("--defect-key", key, "defect_name", names)

    if "section_heading" in names:
        heading = names["section_heading"]
        try:
            headings = _stage_headings(path)
        except (OSError, UnicodeDecodeError) as exc:
            raise UsageError(f"cannot read {hashed_step_file}: {exc}") from None
        section = section_slug(heading)
        if not section:
            raise UsageError(f"--stdin section_heading {heading!r} yields no slug: take the heading that encloses it")
        # A heading copied in another letter case or with other punctuation still names its section.
        if section not in {section_slug(line) for line in headings}:
            raise UsageError(f"--stdin section_heading {heading!r} is no heading of {hashed_step_file}, in any form "
                             f"that gives its slug {section!r}: copy the heading line of the section whose instruction "
                             f"bit, or of the one that encloses it")
    elif not SECTION_RE.fullmatch(section):
        raise UsageError(f"--section must be a kebab-case heading slug (^[a-z0-9]+(-[a-z0-9]+)*$), got {section!r}")

    if "defect_name" in names:
        key = defect_key(names["defect_name"])
        if not key:
            raise UsageError(f"--stdin defect_name {names['defect_name']!r} yields no word: name the thing the fix "
                             f"would change")
    elif not DEFECT_KEY_RE.fullmatch(key):
        raise UsageError(f"--defect-key must be one to four lower-case words joined by hyphens "
                         f"(^[a-z0-9]+(-[a-z0-9]+){{0,3}}$), got {key!r}")

    legacy = f"{severity}|{workflow}|{hashed_step_file}|{section}"
    keyed = f"{legacy}|{key}"
    return {"fp": "fp-" + _sha7(keyed), "legacy_fp": "fp-" + _sha7(legacy), "tuple": keyed,
            "step_file": hashed_step_file, "section_slug": section, "defect_key": key}


# --------------------------------------------------------------------------
# The cache
# --------------------------------------------------------------------------


def _parse(raw: bytes) -> dict | None:
    """The cache object in raw bytes; {} for an empty file, None when it is not a JSON object."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):  # RecursionError: nested past the parser's depth
        return None
    return data if isinstance(data, dict) else None


def load_cache(cache: Path) -> dict:
    """The cache as a dict: missing, empty, unreadable or corrupt is {} (never raises)."""
    try:
        raw = cache.read_bytes()
    except OSError:
        return {}
    return _parse(raw) or {}


# --------------------------------------------------------------------------
# lookup
# --------------------------------------------------------------------------


def gh_issue_state(issue_url: str, timeout: float = GH_TIMEOUT_SEC) -> dict | None:
    """`gh issue view <issue_url> --json state,stateReason`: its JSON object, or None on any failure.

    gh is found and run through skf-source-tree.py's _resolve_outside_cwd
    (never a gh planted in the current folder) and _run (the call and all it
    started are stopped at the time limit).
    """
    try:
        tree = _load(SOURCE_TREE_HELPER)
        exe = tree._resolve_outside_cwd("gh")
        if exe is None:
            return None
        rc, out, _err, _killed = tree._run([exe, "issue", "view", issue_url, "--json", "state,stateReason"],
                                           timeout)
    except (ImportError, OSError, SyntaxError, ValueError, AttributeError):
        return None
    if rc != 0:
        return None
    try:
        answer = json.loads(out.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    if not isinstance(answer, dict) or not isinstance(answer.get("state"), str):
        return None
    return answer


def _gh_url(value) -> bool:
    """An issue_url gh may be given: https://, no whitespace (so never a flag)."""
    return isinstance(value, str) and value.startswith(URL_PREFIX) and not any(ch.isspace() for ch in value)


def _issue_verdict(issue_url) -> tuple[str, str | None]:
    """Branch 3: regression for a completed close ("closed") or a merge ("merged"), handled for anything else."""
    if not _gh_url(issue_url):
        return "handled", None
    answer = gh_issue_state(issue_url, GH_TIMEOUT_SEC)
    if answer is None:
        return "handled", None
    state = answer["state"].upper()
    reason = answer.get("stateReason")
    reason = reason.upper() if isinstance(reason, str) else ""
    if state == "CLOSED" and reason == "COMPLETED":
        return "regression", "closed"
    if state == "MERGED":
        return "regression", "merged"
    return "handled", None


def _verdict(record) -> tuple[str, str | None]:
    """Branches 2 to 5 on a record that exists: the verdict, and for a regression how the fix is known."""
    if not isinstance(record, dict):
        return "unrecognized", None
    action = record.get("action")
    if action == RESOLVED:
        return "regression", RESOLVED
    if action in WRITTEN_ACTIONS:
        if record.get("issue_url") in (None, ""):
            return "handled", None
        return _issue_verdict(record.get("issue_url"))
    return "unrecognized", None


def _issue_prefix(repo: str) -> str:
    """The start of every issue URL of repo: github.com's, or the host's when repo names one."""
    return f"{URL_PREFIX}{repo}/" if repo.count("/") == 2 else f"{URL_PREFIX}github.com/{repo}/"


def _in_repo(record, repo: str | None) -> bool:
    """Whether record may decide a verdict for repo.

    A record that is not an object, or whose issue_url is empty or missing, names no repository, so it decides as it
    always did. Any other issue_url must be a string under repo's issue prefix: another repository's record, or one
    whose URL is not https:// or not a string, neither suppresses this one's finding nor gives its body a line
    linking that issue.
    """
    if repo is None or not isinstance(record, dict):
        return True
    url = record.get("issue_url")
    if url is None or url == "":
        return True
    return isinstance(url, str) and url.lower().startswith(_issue_prefix(repo).lower())


def opening_line(verdict: str, record, fixed: str | None) -> str | None:
    """The line a regression's or a possible regression's issue body carries; None for any other verdict.

    `fixed` is how the fix is known: RESOLVED (the record says so, and its date is the fix's), or "closed" or
    "merged" (the recorded issue's own state, and the record's date is only the day this machine reported it).
    """
    if verdict not in ("regression", "possible-regression") or not isinstance(record, dict):
        return None
    url = record.get("issue_url")
    day = record.get("date")
    dated = isinstance(day, str) and DATE_RE.fullmatch(day)
    possible = verdict == "possible-regression"
    lead = "Possibly a regression" if possible else "Regression"
    if fixed in ("closed", "merged"):
        how = "closed as completed" if fixed == "closed" else "merged"
        line = f"{lead} of {url}, {how} since its report " + (f"on {day}" if dated else UNRECORDED_DATE)
    else:
        resolved = f"(resolved {day if dated else UNRECORDED_DATE})"
        if not _gh_url(url):
            where = " in this section" if possible else ""
            return f"{lead} of a previously resolved local finding{where} {resolved}."
        line = f"{lead} of {url} {resolved}"
    if possible:
        return line + ": that report's fingerprint has no defect key, so it may be another defect in this section."
    return line + "."


def _check_repo(repo: str | None) -> None:
    if repo is not None and not REPO_RE.fullmatch(repo):
        raise UsageError(f"--repo must be [HOST/]OWNER/REPO, as gh takes it, got {repo!r}")


def lookup(fp: str, legacy_fp: str, cache: Path, repo: str | None = None) -> dict:
    """{"verdict", "record", "matched_on", "opening_line"} for one finding."""
    _check_fp("--fp", fp)
    _check_fp("--legacy-fp", legacy_fp)
    _check_repo(repo)
    loaded = load_cache(cache)
    # A record of another repository's issue counts as no record, before anything reads it (gh included).
    data = {key: loaded[key] for key in (fp, legacy_fp) if key in loaded and _in_repo(loaded[key], repo)}
    if fp in data:
        record = data[fp]
        verdict, fixed = _verdict(record)
        matched_on = "fp"
    elif legacy_fp in data:
        record = data[legacy_fp]
        verdict, fixed = _verdict(record)
        # A section fingerprint may be another defect's: it never suppresses, and a fix it records is only possible.
        verdict = {"handled": "unseen", "regression": "possible-regression"}.get(verdict, verdict)
        matched_on = "legacy_fp"
    else:
        return {"verdict": "unseen", "record": None, "matched_on": None, "opening_line": None}
    return {"verdict": verdict, "record": record, "matched_on": matched_on,
            "opening_line": opening_line(verdict, record, fixed)}


# --------------------------------------------------------------------------
# record
# --------------------------------------------------------------------------


def _check_fp(name: str, value: str) -> None:
    if not FP_RE.fullmatch(value):
        raise UsageError(f"{name} must be fp- and 7 lower-case hex characters, got {value!r}")


def _check_record_args(fp: str, action: str, issue_url: str, day: str) -> None:
    _check_fp("--fp", fp)
    if action not in ACTIONS:
        raise UsageError(f"--action must be one of {', '.join(ACTIONS)}, got {action!r}")
    if action == RESOLVED:
        if issue_url != "" and not _gh_url(issue_url):
            raise UsageError(f"--issue-url of a resolved record must be empty or start with {URL_PREFIX} and hold no "
                             f"whitespace, got {issue_url!r}")
    elif not _gh_url(issue_url):
        raise UsageError(f"--issue-url must start with {URL_PREFIX} and hold no whitespace, got {issue_url!r}")
    try:
        if not DATE_RE.fullmatch(day):
            raise ValueError
        date.fromisoformat(day)
    except ValueError:
        raise UsageError(f"--date must be a real date as YYYY-MM-DD, got {day!r}") from None


def _replace(src: Path, dst: Path) -> None:
    """os.replace, retried on Windows while another process has dst open."""
    deadline = time.monotonic() + _REPLACE_WAIT_SECONDS
    while True:
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if not _IS_WINDOWS or time.monotonic() >= deadline:
                raise
            time.sleep(_REPLACE_POLL_SECONDS)


def _atomic_write(target: Path, content: str) -> None:
    """Crash-safe write via temp + fsync + rename, as skf-forge-tier-rw.py's _atomic_write does."""
    tmp = target.with_name(f"{target.name}.skf-{secrets.token_hex(4)}-tmp")
    # O_BINARY (Windows only; 0 elsewhere) keeps \n from turning into \r\n.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(tmp, flags, 0o644)
        try:
            os.write(fd, content.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        _replace(tmp, target)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _set_aside(cache: Path) -> Path:
    """Rename a corrupt cache to <cache>.corrupt-<UTC stamp>, never over an earlier one."""
    stamp = datetime.now(timezone.utc).strftime(CORRUPT_STAMP_FORMAT)
    aside = cache.with_name(f"{cache.name}.corrupt-{stamp}")
    n = 2
    while os.path.lexists(aside):
        aside = cache.with_name(f"{cache.name}.corrupt-{stamp}-{n}")
        n += 1
    _replace(cache, aside)
    return aside


def _merge(cache: Path, fp: str, new: dict, regression: bool) -> dict:
    """The read, merge and write; runs while the caller holds the lock."""
    set_aside = None
    try:
        raw = cache.read_bytes()
    except FileNotFoundError:
        data = {}
    else:
        data = _parse(raw)
        if data is None:
            try:
                set_aside = _set_aside(cache)
            except OSError as exc:
                raise WriteError(f"cannot set aside {cache}, which is not a JSON object: {exc}. "
                                 f"Nothing was written.") from None
            data = {}
    existing = data.get(fp)
    if (isinstance(existing, dict) and existing.get("action") == RESOLVED and new["action"] != RESOLVED
            and not regression):
        # Never downgrade a fix: only an open issue that tracks the recurrence replaces it.
        return {"written": False, "fp": fp, "record": existing, "set_aside": None}
    data[fp] = new
    try:
        _atomic_write(cache, json.dumps(data, indent=2) + "\n")
    except OSError as exc:
        where = f" (the corrupt cache was renamed to {set_aside})" if set_aside else ""
        raise WriteError(f"cannot write {cache}: {exc}{where}") from None
    return {"written": True, "fp": fp, "record": new, "set_aside": str(set_aside) if set_aside else None}


def record(fp: str, action: str, issue_url: str, day: str, regression: bool, cache: Path) -> dict:
    """Set the --fp record under <cache>.lock. Raises UsageError or WriteError."""
    _check_record_args(fp, action, issue_url, day)
    new = {"issue_url": issue_url, "action": action, "date": day}
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        run_lock = _load(RUN_LOCK_HELPER)
    except (ImportError, OSError, SyntaxError) as exc:
        raise WriteError(f"cannot prepare {cache}: {exc}") from None
    lock = cache.with_name(cache.name + ".lock")
    owner = f"health-check-seen:record:{run_lock.new_run_id()}"
    try:
        run_lock.acquire_within(lock, owner, LOCK_STALE_SEC, LOCK_WAIT_SEC, empty_is_stale=True)
    except run_lock.LockBusy as busy:
        info = busy.result
        raise WriteError(f"{lock} is held by {info['held_by'] or 'an unnamed owner'} since {info['held_since']}: "
                         f"another run is writing {cache.name}. Nothing was written.") from None
    except (OSError, ValueError) as exc:
        raise WriteError(f"cannot take {lock}: {exc}") from None
    try:
        try:
            return _merge(cache, fp, new, regression)
        except OSError as exc:
            raise WriteError(f"cannot read {cache}: {exc}") from None
    finally:
        try:
            run_lock.release(lock, owner)
        except (OSError, ValueError):
            pass  # a lock this call could not delete goes stale on its own


# --------------------------------------------------------------------------
# version
# --------------------------------------------------------------------------


def _named_json(path: Path) -> dict | None:
    """The JSON object in path when its "name" is PACKAGE_NAME, else None (never raises)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) and data.get("name") == PACKAGE_NAME else None


def _usable(version) -> str | None:
    """A version a report may name: a non-empty string other than the sentinel probe_skf_version gives."""
    if not isinstance(version, str) or not version.strip() or version.strip() == UNKNOWN_VERSION:
        return None
    return version.strip()


def skf_version(module_root: Path = MODULE_ROOT) -> dict:
    """{"version", "source"} of the SKF the module root belongs to; {"version": None, "source": "N/A"} without one."""
    none = {"version": None, "source": "N/A"}
    try:
        probe = _load(QUICK_METADATA_HELPER).probe_skf_version
        above = module_root.parent
        try:  # read directly: probe_skf_version reads a package.json beside it first
            lines = (module_root / "VERSION").read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeDecodeError):
            lines = []
        version = _usable(lines[0]) if lines else None
        if version:
            return {"version": version, "source": "VERSION"}
        if _named_json(above / "package.json") is not None:
            version = _usable(probe(above))
            if version:
                return {"version": version, "source": "package.json"}
        marketplace = _named_json(above / ".claude-plugin" / "marketplace.json")
        plugins = marketplace.get("plugins") if marketplace else None
        if isinstance(plugins, list) and plugins and isinstance(plugins[0], dict):
            version = _usable(plugins[0].get("version"))
            if version:
                return {"version": version, "source": ".claude-plugin/marketplace.json"}
    except (Exception, SystemExit):  # noqa: BLE001 - a broken sibling (one that exits on load too) never blocks
        return none
    return none


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _error(message: str) -> None:
    print(json.dumps({"status": "error", "message": message}), file=sys.stderr)


class _JsonErrorParser(argparse.ArgumentParser):
    """Report a usage error as a JSON error with exit 2, like every value that breaks its rule."""

    def error(self, message: str) -> None:
        _error(f"usage error: {self.prog}: {message}")
        sys.exit(2)


def _build_parser() -> argparse.ArgumentParser:
    parser = _JsonErrorParser(
        description="Fingerprint a health-check finding, look it up in the seen-issue cache, record it there, and "
                    "print the installed SKF version.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="{fingerprint,lookup,record,version}")

    p_fp = sub.add_parser("fingerprint", help="print the fingerprint, the section (legacy) fingerprint and the "
                                              "fields they hash")
    p_fp.add_argument("--severity", required=True, choices=SEVERITIES)
    p_fp.add_argument("--workflow", required=True, help=f"the workflow's folder name, one of {', '.join(WORKFLOWS)}")
    p_fp.add_argument("--step-file", required=True, dest="step_file",
                      help="the step file: its name or any path to it, of which only the name is kept")
    p_fp.add_argument("--stdin", action="store_true",
                      help='read {"section_heading": ..., "defect_name": ...} from stdin, in place of --section and '
                           "--defect-key: the heading must be one of the step file's own")
    p_fp.add_argument("--section", help="the kebab-case section heading slug, in place of a --stdin section_heading "
                                        "(no heading check)")
    p_fp.add_argument("--defect-key", dest="defect_key",
                      help="one to four lower-case words joined by hyphens, in place of a --stdin defect_name")

    p_lookup = sub.add_parser("lookup", help="the verdict for a finding from the seen-issue cache")
    p_lookup.add_argument("--fp", required=True)
    p_lookup.add_argument("--legacy-fp", required=True, dest="legacy_fp")
    p_lookup.add_argument("--repo", help="the repository findings are filed on, [HOST/]OWNER/REPO: a record of an "
                                         "issue on another one counts as no record")
    p_lookup.add_argument("--cache", help="the cache file (default $HOME/.skf/health-check-seen.json)")

    p_record = sub.add_parser("record", help="record a finding's issue, or its fix, in the seen-issue cache")
    p_record.add_argument("--fp", required=True)
    p_record.add_argument("--action", required=True, choices=ACTIONS)
    p_record.add_argument("--issue-url", required=True, dest="issue_url",
                          help="an https:// URL; empty is allowed with --action resolved")
    p_record.add_argument("--date", required=True, help="YYYY-MM-DD")
    p_record.add_argument("--regression", action="store_true",
                          help="after a regression verdict: the issue tracks the recurrence, so it replaces a resolved "
                               "record")
    p_record.add_argument("--cache", help="the cache file (default $HOME/.skf/health-check-seen.json)")

    sub.add_parser("version", help="the version of the SKF this helper belongs to")
    return parser


def _cache_arg(value: str | None) -> Path:
    return Path(value).expanduser() if value else default_cache()


def _stdin_bytes() -> bytes:
    """stdin as bytes, so a heading's non-ASCII character survives whatever the locale is."""
    raw = getattr(sys.stdin, "buffer", None)
    try:
        return raw.read() if raw is not None else sys.stdin.read().encode("utf-8")
    except (OSError, ValueError, AttributeError):  # AttributeError: no stdin at all
        raise UsageError("--stdin did not read a JSON object") from None


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.cmd == "fingerprint":
            if not args.stdin:
                missing = [flag for flag, value in (("--section", args.section), ("--defect-key", args.defect_key))
                           if value is None]
                if missing:
                    _error(f"usage error: {parser.prog} fingerprint: the following arguments are required without "
                           f"--stdin: {', '.join(missing)}")
                    return 2
            names = read_stdin_names(_stdin_bytes()) if args.stdin else None
            out = fingerprint(args.severity, args.workflow, args.step_file, args.section, args.defect_key, names)
        elif args.cmd == "lookup":
            out = lookup(args.fp, args.legacy_fp, _cache_arg(args.cache), args.repo)
        elif args.cmd == "record":
            out = record(args.fp, args.action, args.issue_url, args.date, args.regression, _cache_arg(args.cache))
        else:
            out = skf_version()
    except UsageError as exc:
        _error(str(exc))
        return 2
    except WriteError as exc:
        _error(str(exc))
        return 1
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
