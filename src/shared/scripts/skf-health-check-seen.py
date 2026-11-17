# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Health Check Seen: the health check's settings, the fingerprints, the
issue title and the top of the issue body of a health-check finding, the check
that its draft names no folder of the user's, the seen-issue cache that every
SKF workflow on the machine shares, the local queue a finding waits in, and
the SKF version a report names.

src/shared/health-check.md, the last step of every SKF workflow, files a
finding as a GitHub issue once per defect on a machine and reports a fixed
defect that comes back as a regression. This helper owns the deterministic
part of that: the repository and autosubmit setting read from config.yaml,
the workflow and step file in one form whatever the install,
the section slug from its heading and the defect key from a name, the two
hashes, the issue title and the machine-read top of the issue body, the
tolerant read of the cache, the bounded check of a recorded issue's state,
the verdict and the line a regression's issue opens with, the locked
merge-write of a record, a draft's check for the project's and the home
folder, the queue file a finding is saved to with the commands that submit
it, and the installed SKF version. The step keeps the
judgment: whether a finding is real, its severity, which section and which
thing it names, its short description, the user's pick at the review gate
and at a matching issue, and the rest of the issue's wording.

CLI:

  uv run skf-health-check-seen.py settings --config <config.yaml>
  uv run skf-health-check-seen.py fingerprint --severity <bug|friction|gap> \\
      --workflow <skf-name|health-check> --step-file <path> \\
      (--stdin | --section <slug> --defect-key <key>)
  uv run skf-health-check-seen.py check-draft --body-file <draft> \\
      --project-dir <absolute path> [--title <title>]
  uv run skf-health-check-seen.py lookup --fp <fp> --legacy-fp <fp> \\
      [--repo <[HOST/]OWNER/REPO>] [--cache <path>]
  uv run skf-health-check-seen.py record --fp <fp> \\
      --action <created|reacted|commented|resolved> --issue-url <url> \\
      --date <YYYY-MM-DD> [--regression] [--cache <path>]
  uv run skf-health-check-seen.py queue --queue-dir <dir> --body-file <draft> \\
      --title <title> --repo <[HOST/]OWNER/REPO>
  uv run skf-health-check-seen.py version

--cache is $HOME/.skf/health-check-seen.json (Path.home()) by default. The
step passes none, so every workflow reads and writes the same file.

Every file this helper reads besides the cache it finds from its own place:
the SKF module root is the folder two levels up (src/ in a checkout or a
plugin, _bmad/skf/ when installed), never {project-root}.

settings
--------
Reads health_check_repo and health_check_autosubmit from --config (the step
passes {project-root}/_bmad/skf/config.yaml) with no YAML library: only a
top-level `key: value` line counts, the key bare or in a matching pair of
quotes, the last of a key winning. A value drops its single or double quotes
('' and the double-quoted escapes decoded) and a trailing comment, whose `#`
follows whitespace. Nothing after the colon, a comment
alone, '', "" and a plain ~, null, Null or NULL are empty. A block or flow
value, an anchor, alias or tag, a quoted value that does not close on its
line and a value that goes on below its line are invalid. A missing file
holds neither key; one that cannot be read or is not UTF-8 makes the
repository invalid.

  repo_state  off      health_check_repo is empty: the check is off
              default  no health_check_repo: repo is DEFAULT_REPO
              set      a [HOST/]OWNER/REPO value (REPO_RE): repo is it
              invalid  anything else: repo is the value as written, or
                       null for a file that cannot be read
  host        repo_state is default or set: the HOST a HOST/OWNER/REPO
              value names, lower-cased, else github.com (DEFAULT_HOST);
              null otherwise. `gh api` takes no --repo, so the step passes
              it --hostname with this host
  owner_repo  repo_state is default or set: repo without its host, the
              OWNER/REPO of a `gh api` path; null otherwise
  is_default  repo_state is default or set, and host and owner_repo are
              DEFAULT_HOST and DEFAULT_REPO, owner_repo in any letter case
  autosubmit  true only for a plain `true`; True, "true", yes and an
              absent key are false

  Output: {"repo_state": ..., "repo": ... | null, "host": ... | null,
           "owner_repo": ... | null, "is_default": ..., "autosubmit": ...}.
  Always exit 0 (2 for a bad argument).

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
             or Test Skill. Or health-check (OWN_STAGE), the health check's
             own stage, for a defect in shared/health-check.md itself.
  step_file  src/<workflow>/references/<file>.md. With --workflow
             health-check it is src/shared/health-check.md: --step-file is
             health-check.md, alone or under a shared/ folder, and the heading
             is checked against the health-check.md beside this script's
             folder. Otherwise --step-file may be the
             file's name, references/<file>.md, its src/ path, its installed
             _bmad/skf/ path or an absolute one: only its last component is
             kept, and it must be, letter case included, the name of a file
             in the module's <workflow>/references/ folder. It may be
             health-check.md, the workflow's relay, only for a workflow whose
             relay holds an instruction besides the load
             (RELAYS_WITH_INSTRUCTIONS): a bare relay, which only loads this
             step, is refused in any letter case. When the folder above
             references/ in the path
             is another SKF skill's, the step file is that skill's: the
             workflow is the one whose references/ folder holds the step
             file, so a step file one workflow loads from another's
             references/ is that other workflow's.

The section comes from a --stdin section_heading or from --section, never
both, and the defect key from a --stdin defect_name or from --defect-key,
never both; each pair is checked on its own, so a --stdin object may hold
one key while the other value is a flag. --stdin reads one JSON object, as
UTF-8, holding only those keys and an optional short_description, each a
non-empty string.

  section_heading: a heading of the step file, outside its frontmatter and
    fenced code, as the file writes it or in any form that gives the same
    slug (another letter case, other punctuation). Its slug: drop the
    leading `#`s, fold it (NFKD, the compatibility decomposition, then drop
    the combining marks: an accented letter gives its base letter, and a
    ligature, a superscript or a full-width form its plain characters; a
    letter NFKD cannot split, such as `ß`, `ø`, `ł`, `æ`, `œ` or `ı`, stays,
    so it becomes a hyphen below), drop a leading numbering token (`1.`, `5a.`,
    `5a-ii.`, `4-headless.`), lower-case, turn each run of characters that
    are not ASCII letters or digits into `-`, and trim hyphens. A heading
    whose slug is empty, or no heading of the step file gives, exits 2.
  defect_name: fold it as a heading is; drop whitespace and the edge
    characters (_NAME_EDGES: backticks, straight and curly quotes, `*`,
    `()[]{}<>`, `.`, `,`, `;`, `!` and `?`) from both ends, in any
    layering; keep its last path component (after `/` or `\\`); drop a
    trailing location (_NAME_LOCATION_RE): a `:N`, then up to two more
    `-N` or `:N`, then an optional `:` or `-` (`:42`, `:42-50`, `:42:7:`,
    `:42:7-12`, `:42-`); a lone `:`; or a GitHub anchor, an optional
    `?plain=1`, then `#L42`, an optional column `C7` and an optional range
    `-L50`, `-L50C3` or `-50` (`#L42`, `#L42-L50`, `#L42C7-L50C3`,
    `?plain=1#L42`); drop whitespace and the edge characters from both ends
    again, and repeat the location and the edges until the name stops
    changing (`` `gate_eval.py:42`: `` gives `gate-eval`); drop a known
    file extension (KNOWN_EXTENSIONS) and then leading dashes and
    underscores; split at whitespace, `_`, `-`, `.` and each lower-case
    letter followed by an upper-case one; drop each character that is not
    an ASCII letter or digit; lower-case; keep the last four words, joined
    by `-`. `scripts/gate_eval.py:42` gives `gate-eval`, `composeStories`
    gives `compose-stories`. A name that yields no word (one written in
    another alphabet included) exits 2.
  short_description: the issue title's description, its surrounding
    whitespace dropped. It may hold no backtick, `$`, double quote,
    backslash, `!` or character that is not printable (a tab, a line break,
    NUL, U+2028 and the like), since the title goes on a command line inside
    double quotes, and may not make regression_title longer than 256
    characters (TITLE_MAX, GitHub's limit).
  --section <slug>: kebab-case (^[a-z0-9]+(-[a-z0-9]+)*$), with no heading
    check. --defect-key <key>: one to four such words
    (^[a-z0-9]+(-[a-z0-9]+){0,3}$). These flags stay for tests and old
    calls.

Each value must keep its rule, else exit 2 naming it: the severity is bug,
friction or gap; the workflow, the step file, the JSON object and its keys,
the heading, the name (it yields a word) and the description as above; the
step file holds no "|" and no line break.

  Output: {"fp": "fp-a54e7a6", "legacy_fp": "fp-eb2d6f2",
           "tuple": <fp's sha1 input>, "step_file": "src/skf-.../...md",
           "section_slug": ..., "defect_key": ...}

With a short_description D, three more keys:

  title             [health-check][<severity>][<fp>] <workflow>: D
  regression_title  [health-check][<severity>][<fp>] <workflow>: REGRESSION: D
  body_header       the machine-read top of the issue body: the sections
                    `## Workflow`, `## Step File`, `## Section`,
                    `## Severity`, `## Fingerprint` (fp alone on its line,
                    then the line "Section fingerprint: `<legacy_fp>`", which
                    the dedup Action reads) and `## Defect Key`, each value in
                    backticks, ending in a newline

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

handled is the only verdict that suppresses a report. Anything uncertain
reports instead: a fresh sighting of a fixed defect is a regression, the
most valuable report the loop makes, and a duplicate heals itself (the dedup
Action closes it and moves its upvote to the canonical issue) while a
silenced regression is caught by nothing.

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

queue
-----
Reads --body-file, a finding's draft, which must open (after a UTF-8 BOM,
its line endings LF or CRLF) with the body_header fingerprint prints: the
workflow (one of WORKFLOWS, or health-check), its step file in the form
fingerprint writes it, the severity and the fingerprint are read from it.
Each of these exits 2 and writes nothing: a draft that opens with no such
header (one whose Fingerprint is N/A included); a --title that does not
start with `[health-check][<severity>][<fp>] <workflow>: ` and a
description, the title fingerprint printed for another finding; a --title
longer than TITLE_MAX or holding a character a short_description may not;
a --repo that is not [HOST/]OWNER/REPO. A --body-file that cannot be read
exits 1.

Creates --queue-dir when absent and writes the draft's bytes, unchanged
and with no frontmatter, to <queue-dir>/hc-<workflow>-<UTC
YYYYMMDD-HHmmss>.md, opened with O_CREAT|O_EXCL so no file is ever
overwritten: a taken name gets -2, -3 and so on before `.md`. A folder or a
file that cannot be created or written exits 1, and a file half written is
removed.

  Output: {"path": <the absolute path written>, "commands": [L, C, B]}

L, C and B submit it: the label create and the create, run in that order (a
failed L, the label there already or no push access, is no error), and B,
the create without labels, for a reporter without push access to run
alone:

  L  gh label create --repo REPO FP --color ededed
       --description 'Health-check fingerprint dedup key'
  C  gh issue create --repo REPO --title TITLE
       --label health-check,workflow-improvement,SEVERITY,FP --body-file PATH
  B  gh issue create --repo REPO --title TITLE --body-file PATH

each on one line, every argument quoted for a POSIX shell (shlex.quote), so
a space or a quote in TITLE or PATH reaches gh as written, and --repo right
after the subcommand, so an allow rule scoped to the repository matches.

check-draft
-----------
Reads --body-file, a draft or a comment's body, and refuses it (exit 2,
naming each line, and the title) when a line or --title holds the
project's folder (--project-dir, {project-root} in the step, and its
realpath) or the home folder (Path.home()): an issue on the default
repository is public. A folder matches in either separator and any letter
case, as a whole path or after file://, before a period that ends a
sentence, never as the start of a longer name (`.bak` included) or inside
another path; a root folder (/ or C:\\) matches nothing. The home folder,
and a project folder below it, also match as ~/, $HOME, ${HOME} or
%USERPROFILE% writes them, but for SKF's own ~/.skf/ (the seen cache).
--project-dir must be absolute. A --body-file that cannot be read exits 1.

  Output: {"clean": true}

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

No network and no gh call in settings, fingerprint, check-draft, record,
queue or version. Every
answer is one JSON line on stdout, in UTF-8 whatever the locale, a
non-ASCII character as itself, so a title is used as printed.

Exit codes (1 and 2 print one JSON line on stderr, {"status": "error",
"message": ...}, and nothing on stdout):
  0  answered
  1  record could not take the lock, read the cache, set a corrupt one
     aside or write it; queue could not read the draft, or create or write
     the queue file; check-draft could not read the draft
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
import shlex
import sys
import time
import unicodedata
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
# Each workflow's relay, the step that loads shared/health-check.md. A bare relay holds nothing else, so no finding is
# ever its own. These relays hold an instruction besides the load (Update Skill releases its lock and removes its
# source tree and run folder, Quick Skill prints its done event, Verify Stack logs a health check it cannot load), so a
# defect there is the relay's. A literal list, as WORKFLOWS is: test-skf-health-check-seen.py derives it from the
# relay files.
RELAY = "health-check.md"
RELAYS_WITH_INSTRUCTIONS = ("skf-quick-skill", "skf-update-skill", "skf-verify-stack")
# The health check's own stage: a defect in shared/health-check.md itself, which the step queues and never posts.
OWN_STAGE = "health-check"
OWN_STEP_FILE = "src/shared/health-check.md"
# The folder that holds shared/health-check.md, as a --step-file path may name it.
OWN_FOLDER = "shared"

# Each rule is matched with fullmatch: `$` alone would let a value that ends in a newline through.
SECTION_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
DEFECT_KEY_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+){0,3}")
FP_RE = re.compile(r"fp-[0-9a-f]{7}")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
URL_PREFIX = "https://"
# The host gh files on for a repository that names none (its OWNER/REPO form).
DEFAULT_HOST = "github.com"
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
# What a name copied from Markdown, a log or a compiler may be wrapped in or end with, besides whitespace: backticks,
# straight and curly quotes, emphasis, brackets and sentence punctuation.
_NAME_EDGES = "`'\"\u2018\u2019\u201c\u201d*()[]{}<>.,;!?"
# A location after the name: `:42`, then up to two more `-N` or `:N`, then an optional `:` or `-` (`:42-50`, `:42:7`,
# `:42:7:`, `:42:7-12`, `:42-`); a lone `:`; or a GitHub anchor, an optional `?plain=1` then `#L42`, an optional
# column `C7` and an optional range `-L50`, `-L50C3` or `-50`. Its repetition is bounded, so a try at one position
# reads no more than three numbers.
_NAME_LOCATION_RE = re.compile(
    r"(?::(?:[0-9]+(?:[-:][0-9]+){0,2}[:-]?)?"
    r"|(?:\?plain=1)?#L[0-9]+(?:C[0-9]+)?(?:-(?:L[0-9]+(?:C[0-9]+)?|[0-9]+))?)\Z"
)
# The most characters that are not digits a location holds (`?plain=1#L42C7-L50C3`), so the one a name ends with
# starts no further back than its last this many: the search for it starts there, whatever the name's length.
_NAME_LOCATION_NON_DIGITS = 13
_DIGITS = "0123456789"
_NAME_SPLIT_RE = re.compile(r"[\s_.-]+")
_CASE_BOUNDARY_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")
_NOT_ALNUM_RE = re.compile(r"[^A-Za-z0-9]")
DEFECT_KEY_WORDS = 4
STDIN_KEYS = ("section_heading", "defect_name", "short_description")
# What a title may not hold besides a character that is not printable (a tab, a line break, NUL, U+2028): it goes
# on a command line inside double quotes, where each of these is special (`!` to an interactive shell's history).
TITLE_UNSAFE = "`$\"\\!"
# GitHub refuses an issue title longer than this many characters.
TITLE_MAX = 256
# The record date an opening line names when the record holds no YYYY-MM-DD date.
UNRECORDED_DATE = "on an unrecorded date"

QUEUE_STAMP_FORMAT = "%Y%m%d-%H%M%S"
# What every health-check issue is filed with besides its severity and fingerprint labels, and the fp-* label's
# look as the step creates it (the dedup Action creates it the same way).
ISSUE_LABELS = ("health-check", "workflow-improvement")
FP_LABEL_COLOR = "ededed"
FP_LABEL_DESCRIPTION = "Health-check fingerprint dedup key"
# The start of a draft: the body_header fingerprint prints, its line endings LF or CRLF. Which workflow and step
# file go together is checked after the match.
_DRAFT_HEADER_RE = re.compile(
    r"## Workflow\r?\n`(?P<workflow>[a-z][a-z-]*)`\r?\n\r?\n"
    r"## Step File\r?\n`(?P<step_file>[^`\r\n]+)`\r?\n\r?\n"
    r"## Section\r?\n`[^`\r\n]+`\r?\n\r?\n"
    r"## Severity\r?\n`(?P<severity>" + "|".join(SEVERITIES) + r")`\r?\n\r?\n"
    r"## Fingerprint\r?\n`(?P<fp>fp-[0-9a-f]{7})`\r?\n\r?\n"
    r"Section fingerprint: `fp-[0-9a-f]{7}`\r?\n\r?\n"
    r"## Defect Key\r?\n`[^`\r\n]+`(?:\r?\n|\Z)"
)
# A workflow's step file as fingerprint writes it: a file of its references/ folder, never a path below it.
_WORKFLOW_STEP_FILE_RE = re.compile(r"src/(?P<workflow>[a-z][a-z-]*)/references/(?P<name>[^/\\`\r\n]+\.md)")

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
# The shared health check, beside this script's folder: the step file of a finding of the own stage.
OWN_STEP_PATH = HERE.parent / RELAY
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
    """A file a call needs could not be read or written, or record could not take the lock (exit 1)."""


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
    if workflow not in WORKFLOWS and workflow != OWN_STAGE:
        raise UsageError(f"--workflow must be the folder name of one of the {len(WORKFLOWS)} SKF workflows that end "
                         f"in the health check, {', '.join(WORKFLOWS)}, or {OWN_STAGE} for a defect in the shared "
                         f"health check's own instructions, got {workflow!r}")


def _own_step_file(step_file: str, parts: list[str]) -> tuple[str, Path]:
    """The own stage's step file: health-check.md, alone or under a shared/ folder, never a workflow's relay."""
    if parts[-1] != RELAY or (len(parts) >= 2 and parts[-2] != OWN_FOLDER):
        raise UsageError(f"--step-file {step_file!r} is not the shared health check: with --workflow {OWN_STAGE}, "
                         f"--step-file is {OWN_FOLDER}/{RELAY}")
    if not OWN_STEP_PATH.is_file():
        raise UsageError(f"--step-file {step_file!r}: {OWN_FOLDER}/{RELAY} is not beside this helper's folder, so "
                         f"its headings cannot be read")
    return OWN_STEP_FILE, OWN_STEP_PATH


def step_file_path(workflow: str, step_file: str) -> tuple[str, Path]:
    """(the step file's hashed form, its path in this module). Raises UsageError for a file not of the workflow."""
    _check_field("--step-file", step_file)
    parts = [part for part in _PATH_SEP_RE.split(step_file.strip()) if part]
    if not parts:
        raise UsageError(f"--step-file names no file, got {step_file!r}")
    if workflow == OWN_STAGE:
        return _own_step_file(step_file, parts)
    name = parts[-1]
    # Only the folder that holds references/ names the step file's skill; a folder further up is the user's. It is
    # checked first, so a relay of another workflow names that workflow rather than the relay rule.
    owner = parts[-3] if len(parts) >= 3 and parts[-2] == "references" else None
    if owner in WORKFLOWS and owner != workflow:
        raise UsageError(f"--step-file {step_file!r} is in {owner}/references/, so --workflow is {owner}: the workflow "
                         f"whose references/ folder holds the step file")
    if owner in SKILL_FOLDERS and owner != workflow:
        raise UsageError(f"--step-file {step_file!r} is in {owner}/references/, which ends in no health check: "
                         f"--step-file is a file of the references/ folder of one of the workflows")
    if name.lower() == RELAY and workflow not in RELAYS_WITH_INSTRUCTIONS:
        raise UsageError(f"--step-file {step_file!r} is {workflow}'s health-check relay, which only loads "
                         f"shared/health-check.md: give the step file whose instruction bit, or the one that was "
                         f"running when a defect in SKILL.md, a script or a shared file bit, or --workflow "
                         f"{OWN_STAGE} and {OWN_FOLDER}/{RELAY} for a defect in the shared health check itself")
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


def _fold(text: str) -> str:
    """NFKD, then no combining mark: an accented letter gives its base letter, a ligature or a superscript its plain
    characters. A letter NFKD cannot split (`ß`, `ø`, `ł`, `æ`, `œ`, `ı`) stays as it is."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def section_slug(heading: str) -> str:
    """The slug rule: no leading `#`s, folded, no numbering token, lower-case, one `-` per run of others."""
    text = _fold(_heading_text(heading))  # folded first, as a name is, so `１.` is the numbering `1.`
    numbering = _NUMBERING_RE.match(text)
    if numbering:
        text = text[numbering.end():]
    return _NOT_SLUG_RE.sub("-", text.lower()).strip("-")


def _edge_bounds(text: str, begin: int, end: int) -> tuple[int, int]:
    """text[begin:end]'s bounds once the whitespace and _NAME_EDGES at either end are gone, in any layering."""
    while begin < end and (text[begin].isspace() or text[begin] in _NAME_EDGES):
        begin += 1
    while end > begin and (text[end - 1].isspace() or text[end - 1] in _NAME_EDGES):
        end -= 1
    return begin, end


def _location_start(text: str, begin: int, end: int) -> int:
    """Where the location text[begin:end] ends with starts (_NAME_LOCATION_RE); end when it ends with none."""
    start, non_digits = end, 0
    while start > begin and (text[start - 1] in _DIGITS or non_digits < _NAME_LOCATION_NON_DIGITS):
        non_digits += text[start - 1] not in _DIGITS
        start -= 1
    location = _NAME_LOCATION_RE.search(text, start, end)
    return location.start() if location else end


def defect_key(name: str) -> str:
    """The defect-key rule; an empty string when the name yields no word."""
    text = _fold(name)
    begin, end = _edge_bounds(text, 0, len(text))  # `gate_eval.py` in backticks, quotes, `**`, brackets or a sentence
    text = _PATH_SEP_RE.split(text[begin:end])[-1]  # `scripts/gate_eval.py` names `gate_eval.py`
    # `gate_eval.py:42:7:` and `gate_eval.py#L42` name it too, and `` `gate_eval.py:42`: `` sheds its `:`, its backtick,
    # then its `:42`: drop a location, then the edges, until neither drops anything. Each round looks back no further
    # than a location reaches and moves bounds instead of copying, so the whole takes time linear in the name's length.
    begin, end = 0, len(text)
    while True:
        bounds = _edge_bounds(text, begin, _location_start(text, begin, end))
        if bounds == (begin, end):
            break
        begin, end = bounds
    text = text[begin:end]
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


def _title_unsafe(text: str) -> bool:
    """True when text holds a character a title on a command line may not: TITLE_UNSAFE, or one not printable."""
    return any(ch in TITLE_UNSAFE or not ch.isprintable() for ch in text)


def read_stdin_names(raw: bytes) -> dict:
    """The {"section_heading", "defect_name", "short_description"} object --stdin reads, as UTF-8.

    Raises UsageError for anything else.
    """
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, RecursionError):  # UnicodeDecodeError is a ValueError
        raise UsageError("--stdin did not read a JSON object") from None
    if not isinstance(data, dict):
        raise UsageError("--stdin did not read a JSON object")
    unknown = sorted(set(data) - set(STDIN_KEYS))
    if unknown:
        raise UsageError(f"unknown --stdin key(s) {', '.join(map(repr, unknown))}; expected only "
                         f"{', '.join(STDIN_KEYS[:-1])} and {STDIN_KEYS[-1]}")
    for key, value in data.items():
        if not isinstance(value, str) or not value.strip():
            raise UsageError(f"--stdin {key} must be a non-empty string")
    if _title_unsafe(data.get("short_description", "").strip()):
        raise UsageError(f"--stdin short_description {data['short_description']!r} holds a backtick, `$`, double "
                         f"quote, backslash, `!` or a character that is not printable (a tab or a line break "
                         f"included); the title goes on a command line, so it may hold none")
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
    fp, legacy_fp = "fp-" + _sha7(keyed), "fp-" + _sha7(legacy)
    out = {"fp": fp, "legacy_fp": legacy_fp, "tuple": keyed, "step_file": hashed_step_file, "section_slug": section,
           "defect_key": key}
    if "short_description" in names:
        description = names["short_description"].strip()
        prefix = title_prefix(severity, fp, workflow)
        regression_title = f"{prefix}REGRESSION: {description}"
        if len(regression_title) > TITLE_MAX:
            raise UsageError(f"--stdin short_description makes the regression title {len(regression_title)} "
                             f"characters long; GitHub takes at most {TITLE_MAX}, so shorten it by "
                             f"{len(regression_title) - TITLE_MAX}")
        out.update(title=prefix + description, regression_title=regression_title,
                   body_header=body_header(severity, workflow, hashed_step_file, section, key, fp, legacy_fp))
    return out


def title_prefix(severity: str, fp: str, workflow: str) -> str:
    """The start of every title of a finding: the dedup Action reads the severity and the fingerprint from it."""
    return f"[health-check][{severity}][{fp}] {workflow}: "


def body_header(severity: str, workflow: str, step_file: str, section: str, key: str, fp: str,
                legacy_fp: str) -> str:
    """The machine-read top of an issue body: the sections the dedup Action and a maintainer's triage read."""
    return (
        f"## Workflow\n`{workflow}`\n\n"
        f"## Step File\n`{step_file}`\n\n"
        f"## Section\n`{section}`\n\n"
        f"## Severity\n`{severity}`\n\n"
        f"## Fingerprint\n`{fp}`\n\n"
        # At the start of a line of its own: the dedup Action's SECTION_RE reads it there.
        f"Section fingerprint: `{legacy_fp}`\n\n"
        f"## Defect Key\n`{key}`\n"
    )


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


def split_repo(repo: str) -> tuple[str, str]:
    """(HOST, OWNER/REPO) of repo, which REPO_RE has accepted: the host it names, lower-cased as gh writes it, else
    DEFAULT_HOST."""
    if repo.count("/") == 2:
        host, owner_repo = repo.split("/", 1)
        return host.lower(), owner_repo
    return DEFAULT_HOST, repo


def _issue_prefix(repo: str) -> str:
    """The start of every issue URL of repo: github.com's, or the host's when repo names one."""
    host, owner_repo = split_repo(repo)
    return f"{URL_PREFIX}{host}/{owner_repo}/"


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
# queue
# --------------------------------------------------------------------------


def _queue_stamp() -> str:
    return datetime.now(timezone.utc).strftime(QUEUE_STAMP_FORMAT)


def _draft_keys(body: bytes) -> tuple[str, str, str] | None:
    """The (workflow, severity, fp) of the body_header a draft opens with, or None when it opens with none."""
    match = _DRAFT_HEADER_RE.match(body.decode("utf-8-sig", errors="replace"))
    if not match:
        return None
    workflow, step_file = match.group("workflow"), match.group("step_file")
    if workflow == OWN_STAGE:
        if step_file != OWN_STEP_FILE:
            return None
    else:
        named = _WORKFLOW_STEP_FILE_RE.fullmatch(step_file)
        if (workflow not in WORKFLOWS or not named or named.group("workflow") != workflow
                or (named.group("name").lower() == RELAY and workflow not in RELAYS_WITH_INSTRUCTIONS)):
            return None
    return workflow, match.group("severity"), match.group("fp")


def submit_commands(repo: str, title: str, severity: str, fp: str, path: str) -> list[str]:
    """The label create, the create, and the create without labels that file a queued draft.

    Each argument is quoted for a POSIX shell, and --repo follows the subcommand, so an allow rule scoped to the
    repository (`gh issue create --repo OWNER/REPO`) matches.
    """

    def line(*argv: str) -> str:
        return " ".join(shlex.quote(arg) for arg in argv)

    label = line("gh", "label", "create", "--repo", repo, fp, "--color", FP_LABEL_COLOR,
                 "--description", FP_LABEL_DESCRIPTION)
    create = line("gh", "issue", "create", "--repo", repo, "--title", title,
                  "--label", ",".join((*ISSUE_LABELS, severity, fp)), "--body-file", path)
    bare = line("gh", "issue", "create", "--repo", repo, "--title", title, "--body-file", path)
    return [label, create, bare]


def _create_new(queue_dir: Path, stem: str) -> tuple[int, Path]:
    """Open queue_dir/<stem>.md for writing, never over a file: <stem>-2.md, -3 and so on when taken.

    Raises OSError when a free name cannot be opened.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    target = queue_dir / f"{stem}.md"
    n = 2
    while True:
        try:
            return os.open(target, flags, 0o644), target
        except FileExistsError:
            target = queue_dir / f"{stem}-{n}.md"
            n += 1


def queue(queue_dir: Path, body_file: Path, title: str, repo: str) -> dict:
    """Write a draft into the local queue under a free name. Raises UsageError or WriteError."""
    if not REPO_RE.fullmatch(repo):
        raise UsageError(f"--repo must be [HOST/]OWNER/REPO, as gh takes it, got {repo!r}")
    try:
        body = body_file.read_bytes()
    except OSError as exc:
        raise WriteError(f"cannot read --body-file {body_file}: {exc}. Nothing was queued.") from None
    keys = _draft_keys(body)
    if keys is None:
        raise UsageError(f"--body-file {body_file} opens with no body_header: open the draft with the body_header the "
                         f"fingerprint call printed for it (a draft whose Fingerprint is N/A has none)")
    workflow, severity, fp = keys
    prefix = title_prefix(severity, fp, workflow)
    if not title.startswith(prefix) or not title[len(prefix):].strip():
        raise UsageError(f"--title {title!r} is not this draft's: its body_header gives {workflow}, {severity} and "
                         f"{fp}, so its title is {prefix!r} and a description, as the fingerprint call printed it")
    if len(title) > TITLE_MAX:
        raise UsageError(f"--title is {len(title)} characters long; GitHub takes at most {TITLE_MAX}")
    if _title_unsafe(title):
        raise UsageError(f"--title {title!r} holds a backtick, `$`, double quote, backslash, `!` or a character that "
                         f"is not printable (a tab or a line break included)")
    try:
        queue_dir.mkdir(parents=True, exist_ok=True)
        fd, target = _create_new(queue_dir, f"hc-{workflow}-{_queue_stamp()}")
    except OSError as exc:
        raise WriteError(f"cannot create a queue file in {queue_dir}: {exc}. Nothing was queued.") from None
    try:
        try:
            data = memoryview(body)
            while data:
                data = data[os.write(fd, data):]  # os.write may write fewer bytes than asked
        finally:
            os.close(fd)
    except OSError as exc:
        try:
            target.unlink()
        except OSError:
            pass
        raise WriteError(f"cannot write {target}: {exc}. Nothing was queued.") from None
    path = os.path.abspath(target)
    return {"path": path, "commands": submit_commands(repo, title, severity, fp, path)}


# --------------------------------------------------------------------------
# settings
# --------------------------------------------------------------------------

# The repository a health check files on when config.yaml names none, as src/module.yaml's default.
DEFAULT_REPO = "armelhbobdad/bmad-module-skill-forge"
REPO_KEY = "health_check_repo"
AUTOSUBMIT_KEY = "health_check_autosubmit"
# The YAML spellings of null: a key holding one, or nothing, is empty.
_YAML_NULLS = ("~", "null", "Null", "NULL")
# A top-level `key:` line: the key at column 0, bare or in a matching pair of quotes, then whitespace or the end of
# the line after the colon.
_CONFIG_LINE_RE = re.compile(
    r"(?P<quote>[\"']?)(?P<key>[A-Za-z_][A-Za-z0-9_-]*)(?P=quote)[ \t]*:(?=[ \t]|$)(?P<rest>.*)")
# What a plain scalar may not start with: a block scalar, a flow collection, an anchor, an alias, a tag or a
# reserved indicator.
_NOT_PLAIN_START = "|>[]{}&*!%@`"
# A plain scalar's comment: a `#` after whitespace.
_PLAIN_COMMENT_RE = re.compile(r"[ \t]#.*$")
PLAIN, QUOTED, EMPTY, INVALID = "plain", "quoted", "empty", "invalid"


def _quoted(rest: str) -> str | None:
    """The value of a quoted scalar that opens rest, or None when it does not close on the line, cannot be decoded or
    is followed by anything but a comment."""
    quote = rest[0]
    i, chars = 1, []
    while i < len(rest):
        ch = rest[i]
        if quote == "'" and ch == "'":
            if rest[i + 1:i + 2] == "'":  # '' is one quote
                chars.append("'")
                i += 2
                continue
            break
        if quote == '"' and ch == "\\":
            chars.append(rest[i:i + 2])
            i += 2
            continue
        if quote == '"' and ch == '"':
            break
        chars.append(ch)
        i += 1
    else:
        return None
    after = rest[i + 1:]
    if after.strip() and not (after[0] in " \t" and after.strip().startswith("#")):
        return None
    if quote == "'":
        return "".join(chars)
    try:
        return json.loads('"' + "".join(chars) + '"')  # YAML's double-quoted escapes, as far as a repository needs
    except ValueError:
        return None


def _continues(lines: list[str], i: int) -> bool:
    """Whether the value of the key on line i goes on below it: an indented line or a block sequence entry follows,
    blank and comment lines aside."""
    for line in lines[i + 1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        return line[0] in " \t" or stripped == "-" or stripped.startswith("- ")
    return False


def config_values(text: str) -> dict:
    """{key: (kind, text)} for each top-level `key:` line of a YAML text, the last line of a key winning.

    kind is PLAIN or QUOTED for a scalar, whose text drops its quotes (decoding `''` and the double-quoted escapes),
    a trailing ` #` comment and the whitespace around it; EMPTY for nothing after the colon, a comment alone, `''`,
    `""` or a YAML null (`~`, `null`, `Null`, `NULL`); INVALID, with the text after the colon, for a block or flow
    value, an anchor, alias or tag, a quoted scalar that does not close on its line, or a value that goes on below
    its line.
    """
    values: dict = {}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        match = _CONFIG_LINE_RE.fullmatch(line)
        if not match:
            continue
        rest = match.group("rest").strip()
        value, kind = None, INVALID
        if rest[:1] in ("'", '"'):
            value = _quoted(rest)
            kind = QUOTED
        elif rest and rest[0] not in _NOT_PLAIN_START and not rest.startswith("#"):
            value = _PLAIN_COMMENT_RE.sub("", rest).strip()
            kind = PLAIN
        elif not rest or rest.startswith("#"):
            value, kind = "", EMPTY
        if value is None or (kind != QUOTED and _continues(lines, i)):
            values[match.group("key")] = (INVALID, rest)
        elif value == "" or (kind == PLAIN and value in _YAML_NULLS):
            values[match.group("key")] = (EMPTY, "")
        else:
            values[match.group("key")] = (kind, value)
    return values


def settings(config: Path) -> dict:
    """The health check's two settings in config, as {"repo_state", "repo", "host", "owner_repo", "is_default",
    "autosubmit"}."""
    try:
        values = config_values(config.read_bytes().decode("utf-8-sig"))
    except FileNotFoundError:
        values = {}
    except (OSError, UnicodeDecodeError):
        values = {REPO_KEY: (INVALID, None)}
    kind, repo = values.get(REPO_KEY, (None, DEFAULT_REPO))
    if kind is None:
        state = "default"
    elif kind == EMPTY:
        state, repo = "off", None
    elif kind == INVALID or not REPO_RE.fullmatch(repo):
        state = "invalid"
    else:
        state = "set"
    host, owner_repo = split_repo(repo) if state in ("default", "set") else (None, None)
    return {"repo_state": state, "repo": repo, "host": host, "owner_repo": owner_repo,
            "is_default": host == DEFAULT_HOST and owner_repo.lower() == DEFAULT_REPO.lower(),
            "autosubmit": values.get(AUTOSUBMIT_KEY) == (PLAIN, "true")}


# --------------------------------------------------------------------------
# check-draft
# --------------------------------------------------------------------------


# The home folder as a draft may write it without its path: each stands for it before a separator, or alone.
HOME_VARIABLES = ("$HOME", "${HOME}", "%USERPROFILE%")
# SKF's own folder under the home folder, where the step keeps its seen cache ($HOME/.skf/health-check-seen.json):
# written through the tilde or a variable it names nothing of the user's.
SKF_HOME_FOLDER = ".skf"
# Where a folder's path starts: not inside a longer name or another path, but right after a file:// scheme.
_PATH_START = r"(?:(?<![\w.\-/\\])|(?<=file://)|(?<=file:///))"
# Where it ends: not in a longer name, and a period only when it ends the sentence (`/work/project.`, not `.bak`).
_PATH_END = r"(?![\w\-]|\.[\w\-])"
_NOT_SKF_HOME = r"(?![\\/]" + re.escape(SKF_HOME_FOLDER) + r"\b)"


def _path_forms(folder: str) -> list[str]:
    """folder in either separator, its trailing separators dropped; [] for a root (`/` or a bare drive, `C:`)."""
    path = folder.rstrip("/\\")
    parts = [part for part in _PATH_SEP_RE.split(path) if part]
    if not parts or (len(parts) == 1 and parts[0].endswith(":")):
        return []
    return sorted({path, path.replace("\\", "/"), path.replace("/", "\\")}, key=len, reverse=True)


def _under_home(folder: str, home: str | None) -> str | None:
    """folder's path below home, "" for home itself, or None when it is not there (letter case aside)."""
    folders, homes = _path_forms(folder), _path_forms(home) if home else []
    if not folders or not homes:
        return None
    path, base = folders[0].replace("\\", "/"), homes[0].replace("\\", "/")
    if path.lower() == base.lower():
        return ""
    if path.lower().startswith(base.lower() + "/"):
        return path[len(base) + 1:]
    return None


def _folder_re(*folders: str, home: str | None = None) -> re.Pattern | None:
    """Each folder's path in either separator and any letter case, as a whole path; with home, a folder that is home
    or below it also as `~`, `$HOME`, `${HOME}` or `%USERPROFILE%` writes it. None when every folder is a root."""
    forms = []
    for folder in folders:
        forms += [re.escape(form) + _PATH_END for form in _path_forms(folder)]
        below = _under_home(folder, home)
        if below == "":
            forms += [re.escape(variable) + _PATH_END + _NOT_SKF_HOME for variable in HOME_VARIABLES]
            forms.append(r"~(?=[\\/])" + _NOT_SKF_HOME)
        elif below:
            forms += [re.escape(prefix + sep + below.replace("/", sep)) + _PATH_END
                      for prefix in ("~", *HOME_VARIABLES) for sep in ("/", "\\")]
    if not forms:
        return None
    return re.compile(_PATH_START + "(?:" + "|".join(forms) + ")", re.IGNORECASE)


def check_draft(body_file: Path, project_dir: str, title: str | None = None) -> dict:
    """Refuse a draft, or its title, that names the project's folder or the home folder. Raises UsageError or
    WriteError."""
    if not os.path.isabs(project_dir):
        raise UsageError(f"--project-dir must be the project's absolute path, got {project_dir!r}")
    try:
        text = body_file.read_bytes().decode("utf-8-sig", errors="replace")
    except OSError as exc:
        raise WriteError(f"cannot read --body-file {body_file}: {exc}") from None
    try:
        home = str(Path.home())
    except (RuntimeError, KeyError):  # no home folder to name
        home = None
    # The project as given and as the file system resolves it: a project reached through a symlink has two paths.
    project = _folder_re(project_dir, os.path.realpath(project_dir), home=home)
    patterns = [("the project's folder", project_dir, project),
                ("the home folder", home, _folder_re(home, home=home) if home else None)]
    lines = ([("the title", title)] if title is not None else []) + [
        (f"line {n}", line) for n, line in enumerate(text.splitlines(), 1)]
    found = []
    for where, line in lines:
        # The first that matches: the project's folder, more specific than a home folder it sits in.
        hit = next(((label, folder) for label, folder, pattern in patterns if pattern and pattern.search(line)), None)
        if hit:
            found.append(f"{where} holds {hit[0]}, {hit[1]}")
    if found:
        raise UsageError(f"--body-file {body_file} names a folder of the user's, which an issue never does: "
                         f"{'; '.join(found)}. Rewrite each such line or the title, citing SKF's files by their "
                         f"module path (src/<workflow>/references/<file>.md, src/shared/...)")
    return {"clean": True}


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


def _print_utf8(payload: dict) -> None:
    """Print payload as JSON in UTF-8 whatever the locale, non-ASCII as itself: a title is used as printed."""
    text = json.dumps(payload, ensure_ascii=False) + "\n"
    out = getattr(sys.stdout, "buffer", None)
    if out is None:
        sys.stdout.write(text)
        return
    sys.stdout.flush()
    out.write(text.encode("utf-8"))
    out.flush()


class _JsonErrorParser(argparse.ArgumentParser):
    """Report a usage error as a JSON error with exit 2, like every value that breaks its rule."""

    def error(self, message: str) -> None:
        _error(f"usage error: {self.prog}: {message}")
        sys.exit(2)


def _build_parser() -> argparse.ArgumentParser:
    parser = _JsonErrorParser(
        description="Read the health check's settings, fingerprint a finding and print its title and the top of "
                    "its issue body, check its draft names no folder of the user's, look it up in the seen-issue "
                    "cache, record it there, save its draft to the local queue, and print the installed SKF version.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True,
                                metavar="{settings,fingerprint,check-draft,lookup,record,queue,version}")

    p_settings = sub.add_parser("settings", help="the health check's repository, with its host and OWNER/REPO, and "
                                                 "autosubmit setting, read from the config file")
    p_settings.add_argument("--config", required=True, help="the module's config.yaml; a missing one gives the "
                                                            "defaults")

    p_fp = sub.add_parser("fingerprint", help="print the fingerprint, the section (legacy) fingerprint and the "
                                              "fields they hash, and with a short_description the title, the "
                                              "regression title and the body header")
    p_fp.add_argument("--severity", required=True, choices=SEVERITIES)
    p_fp.add_argument("--workflow", required=True,
                      help=f"the workflow's folder name, one of {', '.join(WORKFLOWS)}, or {OWN_STAGE} for a defect "
                           f"in the shared health check itself")
    p_fp.add_argument("--step-file", required=True, dest="step_file",
                      help="the step file: its name or any path to it, of which only the name is kept "
                           f"({OWN_FOLDER}/{RELAY} with --workflow {OWN_STAGE})")
    p_fp.add_argument("--stdin", action="store_true",
                      help='read {"section_heading": ..., "defect_name": ..., "short_description": ...} from stdin: '
                           "the first two in place of --section and --defect-key (the heading must be one of the "
                           "step file's own), the optional third for the title and the body header")
    p_fp.add_argument("--section", help="the kebab-case section heading slug, in place of a --stdin section_heading "
                                        "(no heading check)")
    p_fp.add_argument("--defect-key", dest="defect_key",
                      help="one to four lower-case words joined by hyphens, in place of a --stdin defect_name")

    p_check = sub.add_parser("check-draft", help="refuse a draft that names the project's folder or the home "
                                                 "folder")
    p_check.add_argument("--body-file", required=True, dest="body_file", help="the draft, or a comment's body")
    p_check.add_argument("--project-dir", required=True, dest="project_dir", help="the project's absolute path")
    p_check.add_argument("--title", help="the issue title, checked as the draft's lines are")

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

    p_queue = sub.add_parser("queue", help="save a finding's draft to the local queue, unchanged, and print the "
                                           "commands that submit it")
    p_queue.add_argument("--queue-dir", required=True, dest="queue_dir", help="the local queue folder")
    p_queue.add_argument("--body-file", required=True, dest="body_file",
                         help="the draft, opening with the body_header the fingerprint call printed: the queue file "
                              "is named after its workflow")
    p_queue.add_argument("--title", required=True, help="the title the fingerprint call printed for the draft")
    p_queue.add_argument("--repo", required=True,
                         help="the repository the commands file the issue on, [HOST/]OWNER/REPO")

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
        if args.cmd == "settings":
            out = settings(Path(args.config).expanduser())
        elif args.cmd == "check-draft":
            out = check_draft(Path(args.body_file).expanduser(), args.project_dir, args.title)
        elif args.cmd == "fingerprint":
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
        elif args.cmd == "queue":
            out = queue(Path(args.queue_dir).expanduser(), Path(args.body_file).expanduser(), args.title, args.repo)
        else:
            out = skf_version()
    except UsageError as exc:
        _error(str(exc))
        return 2
    except WriteError as exc:
        _error(str(exc))
        return 1
    _print_utf8(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
