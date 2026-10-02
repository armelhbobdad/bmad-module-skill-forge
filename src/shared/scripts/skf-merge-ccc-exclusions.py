# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""SKF Merge CCC Exclusions — prepare .cocoindex_code/settings.yml and keep
the SKF exclusion patterns in it current.

One invocation from setup step 1b (`src/skf-setup/references/ccc-index.md`)
owns every decision about the project's ccc settings file, so none of it
lives in step prose:

  1. run `ccc init -f` when settings.yml is missing, and rebuild a file that
     lacks the ccc default exclusions;
  2. validate the two folder values from `_bmad/skf/config.yaml`;
  3. exclude each folder whole, or entry by entry when it also holds
     content SKF did not generate; leave out a folder with no SKF output,
     and leave alone a folder the user already excluded;
  4. merge the SKF patterns and prune the SKF-owned patterns the current
     config no longer produces;
  5. warn when `/.cocoindex_code/` is not gitignored;
  6. return one `index_action` telling the step whether to run `ccc index`,
     and with --build-index act on it: run `ccc index` itself, read the
     file count from `ccc status` and stamp the time (Index build, below).

CLI — invoke via `uv run` so the PEP 723 PyYAML dependency declared
above is auto-resolved on first call and cached. `docs/getting-started.md`
documents uv as the runtime prerequisite for exactly this. Bare
`python3` will fail with `ModuleNotFoundError: No module named 'yaml'`
on a fresh interpreter:

  uv run skf-merge-ccc-exclusions.py \\
      --project-root /abs/path \\
      --skills-output-folder skills \\
      --forge-data-folder _bmad-output/forge-data \\
      --prior-state-from /abs/path/_bmad/_memory/forger-sidecar/forge-tier.yaml \\
      --index-fresh false \\
      --skip-index false

  uv run skf-merge-ccc-exclusions.py \\
      --project-root /abs/path \\
      --config /abs/path/_bmad/skf/config.yaml \\
      --prior-state-from /abs/path/_bmad/_memory/forger-sidecar/forge-tier.yaml \\
      --index-fresh false --skip-index false \\
      --build-index --result-to /abs/run/ccc-exclusions.json

Flags:

  --project-root          required; the directory holding .cocoindex_code/
  --skills-output-folder  raw skills_output_folder config value, forwarded
                          verbatim (`{project-root}/...` is resolved here)
  --forge-data-folder     raw forge_data_folder config value, same handling
  --config                instead of the two folder flags: the
                          `_bmad/skf/config.yaml` to read both raw values
                          from, so no caller forwards them by hand (a key
                          the file lacks reads as an empty value)
  --prior-state-from      forge-tier.yaml; its ccc_index.exclude_patterns is
                          the record of the patterns SKF owns
  --index-fresh           true|false (case-insensitive); the prior index is
                          still fresh, so an unchanged settings.yml keeps it
  --skip-index            true|false; the setup run opted out of indexing
  --no-ccc-init           never run ccc init (tests and diagnostics)
  --build-index           setup mode only: act on index_action and add the
                          `index` result (Index build, below)
  --result-to             also write the JSON result, or the JSON error of a
                          run that fails, to this file, so the caller's
                          next steps read it from there; with
                          --build-index it is written before `ccc index`
                          runs too (Index build, below)
  --clone-root            instead of --project-root: an SKF workspace clone
                          (clone mode, below)
  --include-ext           clone mode only, repeatable: a file extension whose
                          files ccc must index (`ex`, `.ex`)

Clone mode (create-skill step 3 and step 7) prepares the settings.yml of an
SKF workspace clone, a source repository rather than an SKF project, so the
list merges its step prose used to make by hand live here too:

  uv run skf-merge-ccc-exclusions.py --clone-root /abs/clone \\
      [--include-ext ex --include-ext exs]

  1. run `ccc init -f` when settings.yml is missing, so the clone gets a
     project of its own instead of an enclosing one's;
  2. quote each bare `- *...` list item an earlier hand edit left, which
     YAML reads as an alias, so ccc can load the file again;
  3. append each standard build and dependency exclusion (CLONE_EXCLUDES)
     that exclude_patterns lacks, keeping every entry already there;
  4. with --include-ext, append `**/*.<ext>` to include_patterns for each
     extension no include_patterns entry matches, reading each entry as
     ccc's glob library does.

A file with no exclude_patterns list, or no include_patterns list, gets
nothing added to that list: a list written from scratch replaces the ccc
defaults. Clone mode never removes an entry, never rebuilds the file, and
takes none of the folder, record or index flags of setup mode. Its writes
go through a temporary file of their own, so two runs merging the same
clone never tear the file; they add the same entries.

Settings states (target = {project-root}/.cocoindex_code/settings.yml):

  missing   `ccc init -f` creates it (ccc_init "created"). With
            --no-ccc-init, or when ccc init leaves no file (ccc_init
            "failed"), settings_ready is false and index_action is "fail":
            a later `ccc index` would auto-initialise at the enclosing git
            root and index it without the SKF exclusions. When the created
            file has no exclude_patterns list, SKF adds nothing to it.
  rebuild   the file is empty, has no `exclude_patterns` key, or has
            neither an `include_patterns` key nor `**/.cocoindex_code` in
            its exclusions — every file ccc writes has both, so such a file
            suppresses the ccc defaults (hidden folders, node_modules, the
            ccc database). The original is moved aside to
            `settings.yml.skf-repair`, `ccc init -f` writes a fresh file,
            and the result is the fresh file plus every original top-level
            key plus every original exclude entry not already there
            (ccc_init "rebuilt"). The backup is removed only after the
            write succeeds; a leftover backup found on startup is restored
            and the repair runs again. If ccc init produces no usable file,
            the original bytes are restored, ccc_init is "failed", and no
            SKF change is applied that run; a fresh prior index is kept, but
            no new index is built from that file (index_action "keep" or
            "fail"). With --no-ccc-init the rebuild is skipped with a
            warning and the file is left alone.
  ready     any other file is reconciled in place (ccc_init "not_needed").

The script never writes settings.yml from scratch. `ccc init -f` is the
only creator: `-f` merely skips ccc's parent-marker check, so one call
covers the git-root, nested-folder and repair cases, and on an existing
file ccc prints "Project already initialized." and changes nothing. At the
top of a git checkout ccc also adds `/.cocoindex_code/` to `.gitignore`;
SKF never writes `.gitignore` itself.

Patterns SKF owns:

  **/_bmad           SKF framework module (workflows, agents, knowledge)
  **/_bmad-output    Build output artifacts
  **/.claude         Claude Code configuration
  **/_skf-learn      SKF learning materials
  {skills_output_folder}   Generated skill files (default `skills`)
  {forge_data_folder}      Compilation workspace

The four `**/` patterns are always produced. The two folder patterns are
the project-relative value itself, anchored to the project root: ccc reads
`skills` as that one root folder, while `**/skills` would also drop every
nested folder with the same name.

A folder that also holds content SKF did not generate gets per-entry
patterns instead of the bare value, each anchored the same way:

  {folder}/<entry>              each SKF-owned first-level directory or
                                root file, named as it is on disk
  {folder}/<fixed entry>        always, present or not: `_batch` and
                                `.export-manifest.json` (skills),
                                `_campaign` and `improvement-queue` (forge)
  {folder}/<stem>-result*.json  always for the `export-skill` and
                                `drop-skill` stems (skills), and for the
                                stem of any other SKF result at the root
  {folder}/<prefix>*            forge only, one per SKF report prefix

Glob characters in an entry name are written as one-character classes
(`[x]` becomes `[[]x[]]`); a backslash escape is never used, because ccc's
matcher reads a backslash as `/` on Windows. A name holding `'`, `\\`, a
control character, U+FFFD or an undecodable byte cannot go through a
quoted shell payload, so that entry stays indexed with a warning. No
pattern is ever `{folder}/*` or a `!` negation: ccc applies a negation
against every pattern, its own defaults included, and a `!{folder}/...`
also cancels a bare `{folder}` pattern.

A `!` entry of the user's cancels an SKF pattern the same way. ccc walks
into an excluded folder when a `!` entry matches the folder, matches the
one child name ccc probes it with (in practice a wildcard child: `!*/*`
and `!**/skills/*` re-open `skills`, `!*/x` does not), or starts with
`{folder}/`, and then indexes everything below it that no other pattern
excludes. So once the patterns are merged, each folder with the bare
value or per-entry patterns gets one warning naming the entries that
re-open one of its patterns, when ccc, reading the exclude_patterns this
run writes, walks down to a file of SKF output git lists below that
pattern (or, with none there yet, into the child it probes). Result and
report families are not checked. Inside a hidden folder ccc's own `**/.*`
still excludes that output, so an entry there warns only when it
re-opens every level down to it, and the bare value's warning says all
SKF output is back only when every SKF entry there is reached. A folder
inside an always-excluded one never switches to per-entry patterns, so
its warning offers no folder of the user's own there. A backslash in an
entry is read as ccc's glob library reads it on the machine the helper
runs on: `/` on Windows, an escape elsewhere. The warning repeats on
every run while the entry stays, including after a folder that held
other content goes back to the bare value; SKF never removes the entry.

Folder values are normalized first: surrounding whitespace is stripped,
`\\` becomes `/`, a leading `{project-root}/` is dropped, and `./`, `//`
and a trailing `/` collapse. A normalized value is then refused, with a
warning naming the key and the file to fix, when it is:

  - empty or `.`                     (would exclude the whole repository)
  - absolute or anchored: a leading `/`, `~` or `./`, a drive letter, or
    a trailing `/`                   (absolute paths are never rewritten)
  - carrying a `..` segment          (outside the project)
  - starting with `!`                (ccc reads it as a negation)
  - carrying `*`, `?`, `[`, `]` or `\\` (ccc reads them as glob syntax)
  - carrying `{` or `}`              (an unresolved template placeholder)
  - carrying a control character     (does not survive a quoted payload)
  - carrying `'`                     (breaks a single-quoted payload)

A refused value is left out; the four `**/` patterns still merge.

Folder check: for each accepted folder that exists, the script lists it
with `git --literal-pathspecs ls-files -z --cached --others
--exclude-per-directory=.gitignore -- <folder>`: tracked files plus
untracked files no `.gitignore` excludes, the only ignore files ccc reads
(`.git/info/exclude` and a global excludes file hide nothing from ccc, so
they hide nothing here either). A tracked file deleted from the worktree
is dropped. The paths are grouped by first-level entry. A group is SKF
output by the same rule the workflows use before they write into, move or
delete a skill's folders (skf-skill-inventory.py):

  skills  it is `_batch` or its name contains `.skf-`, or its
          `metadata.json` or a `<v>/<n>/metadata.json` carries an SKF
          marker (generated_by, tool_versions.skf, or skill_type with
          forge_tier / confidence_tier); a linked group never is. The
          versioned layout, an `active` pointer, a manifest key or a
          `*-result*.json` alone do not count, so a module's skills that an
          earlier SKF moved into the versioned layout stay indexed
  forge   its name contains `.skf-`, it is `_campaign` or
          `improvement-queue`, or it holds a `skill-brief.yaml*`,
          `.brief-draft.json` or `*-result*.json` file directly, or a
          provenance map, evidence report, extraction rules or
          `*-result*.json` file directly in a folder of it; a linked group,
          folder or file never counts. Like the skills rule it reads the
          group on disk, so a file `.gitignore` hides still counts

Root files named `*-result*.json`, `.export-manifest.json` (skills) or
with an SKF report prefix (forge) are SKF output. Neutral entries never
count: `.gitkeep`, `.gitignore`, `.gitattributes`, `.DS_Store`,
`Thumbs.db`, `desktop.ini` and README files, plus any other dot-named
entry when `**/.*` (the ccc default) is in exclude_patterns and no entry
there starts with `!`. Everything else is foreign. A group that is, or
contains, the other configured SKF folder counts as SKF output but gets no
pattern of its own: that folder is reconciled separately, deepest first.
When both settings name the same folder, an entry either kind accepts is
SKF output. A submodule or nested repository is classified too: when the
folder itself is one, its own files are listed from inside it, and one
deeper down is a group of its own.

Each folder gets one verdict:

  user      the folder value is already in exclude_patterns and SKF does
            not own it (see the record below): no pattern, no warning
  bare      no foreign group, and either SKF output or no other root file
            (loose notes beside SKF output are tolerated): the bare value
  entries   foreign entries next to SKF output, or a folder nested inside
            it that is itself `entries` or `left_out`: the per-entry
            patterns, with a note naming the foreign entries when there
            are any
  left_out  foreign entries and no SKF output: nothing, with a warning
            naming the setting to change

The check is skipped, giving the bare value, silently when git is missing,
the project is not a git repository, the folder does not exist, or an
always-included `**/` pattern already covers the folder; it is skipped
with a warning when git times out or fails in any other way (for example
a repository git refuses as unsafe). Every git and ccc child runs with
the git location variables (GIT_DIR, GIT_INDEX_FILE, ...) removed from
its environment, so a git hook's index never leaks into the check; git
also runs with LC_ALL=C so its messages are recognised in any locale.

Ownership record and pruning: `ccc_index.exclude_patterns` in the
forge-tier.yaml passed through --prior-state-from is the set of patterns
SKF owned after its last reconcile, per-entry patterns included. A
recorded pattern the current run does not produce is removed from
settings.yml, so a dropped or renamed skill loses its pattern and a folder
that changes verdict swaps its bare value for per-entry patterns or back;
entries SKF never recorded (user entries and the ccc defaults) are never
removed, and the four `**/` patterns are always produced so are never
pruned. A record is legacy when forge-tier.yaml exists, the record names
no folder pattern (it holds at most the four `**/` patterns), and it is
empty or settings.yml still holds a `**/{value}` form of an accepted
folder value; those `**/{value}` forms then count as owned, so installs
migrate to the anchored forms. A `**/skills` added by the user after a
folder pattern is recorded survives, and with no forge-tier.yaml at all
SKF owns nothing yet. A record is trusted when forge-tier.yaml exists and
the record is not legacy: with a trusted record, a folder value already in
exclude_patterns that the record does not hold is the user's (verdict
`user`), unless the record holds `{value}/...` per-entry patterns and none
of them is still in exclude_patterns. SKF then swapped them for the bare
value in a run that stopped before its record was saved, so the value is
SKF's and is classified again. Without a trusted record the folder is
still classified: an all-SKF folder adopts the bare value already there,
and a folder with foreign entries keeps it untouched with a one-time
warning (the next run has a trusted record). When a folder value is refused, pruning is blocked
for the whole run and the recorded patterns that would have been removed
stay (warning): a config typo must not silently un-exclude real output. If
that run also used the legacy fallback, effective_patterns is null so the
record stays folder-free and the next valid run can still migrate.

Index decision: "fail" when no settings.yml exists; otherwise "skip"
under --skip-index true (with a warning when settings.yml changed);
otherwise, after a failed rebuild, "keep" when the prior index is fresh
and "fail" when it is not; otherwise "index" when settings.yml changed or
the prior index is not fresh; otherwise "keep".

After a reconcile, `/.cocoindex_code/` coverage is checked with
`git check-ignore -q --no-index -- .cocoindex_code/target_sqlite.db`; an
uncovered path adds a warning. `gitignore_updated` compares the
`.gitignore` bytes before and after the run (only ccc init writes it).

Index build (--build-index): the script acts on index_action itself and
returns the index state the run ends with, so no step reads `ccc status`
or types a timestamp:

  keep   status "fresh"; last_indexed and file_count carry over from the
         prior forge-tier.yaml (--prior-state-from)
  skip   status "skipped"
  fail   status "failed", with not_ready_reason as failed_reason
  index  `ccc index` runs in the project root (up to CCC_INDEX_TIMEOUT_SEC).
         Then `ccc status` gives the file count. While it prints an
         `Indexing in progress:` line, `ccc index` runs again (it waits
         for the running pass, then makes a quick incremental one), up to
         CCC_INDEX_RERUNS times; a pass still running after that adds a
         warning and the count read last. Status "created", stamped with
         this script's UTC clock, when ccc indexed at least one file;
         status "failed", with the reason, when `ccc index` or `ccc status`
         fails, the status shows no file count, or the count is 0.
         Before `ccc index` starts, --result-to already holds the merge
         result with the index "failed" ("ccc index did not finish"),
         so a call its host stops during a long index still leaves this
         run's exclusion record for the next steps; the final result
         replaces it.

indexed_path is the --project-root value exactly as given, which is what
skf-detect-tools.py compares the next run's --project-root with.

Output (single JSON document on stdout, ASCII only):

  {
    "status": "ok",
    "version": "v2",
    "settings_yml_path":         "/abs/path/.cocoindex_code/settings.yml",
    "settings_yml_existed":      bool,   after crash recovery, before init
    "ccc_init":                  "not_needed" | "created" | "rebuilt"
                                 | "failed",
    "settings_ready":            bool,   false only when no usable
                                         settings.yml exists
    "not_ready_reason":          str | null,  why index_action is
                                         "fail" (null otherwise)
    "patterns_added":            int,
    "patterns_added_list":       [str],  produced patterns not in the
                                         pre-run list
    "patterns_removed":          int,
    "patterns_removed_list":     [str],  SKF-owned patterns pruned
    "patterns_already_present":  int,
    "effective_patterns":        [str] | null,  sorted SKF-owned set to
                                         record, per-entry patterns
                                         included (copy every entry
                                         exactly); null when nothing was
                                         reconciled, or a legacy-record run
                                         with a refused value (keep the
                                         old record)
    "written":                   bool,   settings.yml changed this run
                                         (ccc init create, rebuild, or
                                         SKF edit)
    "gitignore_updated":         bool,
    "index_action":              "index" | "keep" | "skip" | "fail",
    "index":                     only with --build-index:
                                 {"status": "fresh" | "created" | "skipped"
                                            | "failed",
                                  "indexed_path": str | null,
                                  "last_indexed": str | null,  ISO-8601 UTC
                                  "file_count": int | null,
                                  "failed_reason": str | null},
    "warnings":                  [str]   refused values and other notes for
                                         the report, a user `!` entry that
                                         cancels an SKF pattern included
  }

Clone mode output (single JSON document on stdout, ASCII only):

  {
    "status": "ok",
    "version": "v2",
    "settings_yml_path":         "/abs/clone/.cocoindex_code/settings.yml",
    "settings_yml_existed":      bool,
    "ccc_init":                  "not_needed" | "created" | "failed",
    "settings_ready":            bool,   false only when no settings.yml
                                         exists after the ccc init
    "not_ready_reason":          str | null,
    "patterns_added":            int,
    "patterns_added_list":       [str],  standard exclusions appended
    "patterns_already_present":  int,
    "includes_added_list":       [str],  `**/*.<ext>` entries appended
    "includes_covered_list":     [str],  extensions an include_patterns
                                         entry already matched
    "written":                   bool,   settings.yml changed this run
    "warnings":                  [str]
  }

Payload safety: setup's steps once embedded these strings in
single-quoted `echo '...'` payloads, where dash's `echo` rewrites
backslash escapes; they now read the --result-to file, and the strings
stay safe for any caller that still quotes them. So every warning,
`not_ready_reason` and error message has `'` replaced by a
backtick, `\\` by `/`, and control characters and lone surrogates by `?`;
folder values carrying `'`, `\\` or a control character are refused, and
an entry name carrying one gets no pattern. No pattern SKF produces, and
so no effective_patterns entry, holds any of them. Data fields such as
`settings_yml_path` are emitted as they are.

Paths in messages: when a warning or `not_ready_reason` names the
project root in SKF's own words, it writes the literal `{project-root}`
placeholder, never the absolute path. Setup's step 4 banner renders a
warning's placeholder like its own `{project-root}` paths, and the
envelope keeps it verbatim. The unresolved-placeholder refusal names the
placeholder this script resolves in words ("the project-root
placeholder"), so a `{project-root}` in SKF's own words always means the
project root. Output and errors quoted from `ccc init` or git can carry
paths of their own, the project root included. Error messages on stderr
name absolute paths.

Writes to settings.yml use temp + fsync + rename (mirrors
skf-atomic-write.py), emit ASCII-only YAML (non-ASCII escaped, as ccc
writes it — ccc reads the file with the platform default encoding), and
drop YAML comments; ccc ignores them and keeps unknown top-level keys,
which are preserved. Concurrent writers must
coordinate via external `flock` (the typical pattern for shared-file
mutation in this module).

Exit codes:
  0 success, including "not ready" (warnings stay on the success path)
  1 --project-root (or --clone-root) is not a directory; settings.yml
    cannot be parsed, is not a mapping, or has an exclude_patterns (clone
    mode: or include_patterns) that is neither a list nor null (JSON error
    on stderr)
  2 usage error (including a non-boolean --index-fresh / --skip-index, an
    --include-ext that is not a plain extension, and a setup flag or
    --include-ext given in the other mode), a write, move-aside or restore
    failure, or any unexpected internal error (always JSON on stderr, never
    a traceback)
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import NamedTuple

import yaml


ALWAYS_INCLUDE = (
    "**/_bmad",
    "**/_bmad-output",
    "**/.claude",
    "**/_skf-learn",
)
GLOB_META_CHARS = set("*?[]\\")
PLACEHOLDER_CHARS = set("{}")
CCC_SELF_EXCLUDE = "**/.cocoindex_code"
CCC_INIT_TIMEOUT_SEC = 75
# A first index of a large codebase can take many minutes.
CCC_INDEX_TIMEOUT_SEC = 3600
CCC_STATUS_TIMEOUT_SEC = 75
CCC_INDEX_RERUNS = 3
# The index failed_reason --result-to holds while `ccc index` runs.
INDEX_UNFINISHED = "ccc index did not finish"
CCC_IN_PROGRESS = "Indexing in progress:"
CCC_FILES_RE = re.compile(r"^\s*Files:\s*(\d+)\s*$", re.MULTILINE)
GIT_TIMEOUT_SEC = 10
SAMPLE_SIZE = 3
INDEX_ACTIONS = ("index", "keep", "skip", "fail")
# Keep identical to GIT_LOCATION_VARS in skf-check-workspace-drift.py.
GIT_LOCATION_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_PREFIX",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE",
)
# Keep identical to RESULT_JSON_RE in skf-skill-inventory.py
# (test/test-skf-skill-inventory.py pins the copies).
RESULT_JSON_RE = re.compile(r"^([a-z0-9][a-z0-9-]*)-result(-latest|-\d[^/]*)?\.json$")
README_RE = re.compile(r"^readme(\..+)?$", re.IGNORECASE)
NEUTRAL_ROOT_FILES = frozenset({".gitkeep", ".gitignore", ".gitattributes", ".DS_Store",
                                "Thumbs.db", "desktop.ini"})
SKF_FIXED_ENTRIES = {
    "skills": ("_batch", ".export-manifest.json"),
    "forge": ("_campaign", "improvement-queue"),
}
SKF_ROOT_RESULT_STEMS = {"skills": ("export-skill", "drop-skill"), "forge": ()}
# Keep identical to SKF_GENERATORS in skf-skill-inventory.py
# (test/test-skf-skill-inventory.py pins the copies).
SKF_GENERATORS = frozenset({"quick-skill", "create-skill", "create-stack-skill"})
FORGE_ROOT_PREFIXES = (
    "analyze-source-",
    "feasibility-report-",
    "verify-stack-result-",
    "ra-state-",
    "refine-architecture-result-",
    "refined-architecture-",
)
# Keep identical to FORGE_GROUP_DIRS in skf-skill-inventory.py
# (test/test-skf-skill-inventory.py pins the copies).
FORGE_GROUP_DIRS = frozenset({"_campaign", "improvement-queue"})
# Keep identical to FORGE_VERSION_ANCHORS in skf-skill-inventory.py
# (test/test-skf-skill-inventory.py pins the copies).
FORGE_VERSION_ANCHORS = frozenset({"provenance-map.json", "evidence-report.md", "extraction-rules.yaml"})
FOLDER_KEYS = (("skills_output_folder", "skills"), ("forge_data_folder", "forge"))
# Glob characters written as one-character classes in per-entry patterns,
# as ccc's glob library escapes them; its backslash escaping is off on Windows.
CCC_CLASS_ESCAPES = frozenset("*?[]{}")

SETTINGS_DIR = ".cocoindex_code"
SETTINGS_NAME = "settings.yml"
BACKUP_NAME = "settings.yml.skf-repair"
FIX_HINT = "fix the value in {project-root}/_bmad/skf/config.yaml"

# Clone mode: the build and dependency folders create-skill keeps out of the
# index of a workspace clone. They are generic artifact patterns, not SKF
# paths, in the `**/name` form (ccc matches it at any depth; a trailing-slash
# form such as `build/` matches nothing).
CLONE_EXCLUDES = (
    "**/node_modules",
    "**/dist",
    "**/build",
    "**/.git",
    "**/vendor",
    "**/__pycache__",
    "**/.cache",
    "**/.next",
    "**/.nuxt",
    "**/target",
    "**/out",
    "**/.venv",
    "**/.tox",
)
# An extension --include-ext takes: letters, digits, `_`, `+` and `-` only,
# so `**/*.<ext>` is never a wider glob than one file type.
EXTENSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_+-]*$")
# A nested file with a given extension, matched against include_patterns.
INCLUDE_PROBE = "skf-probe/skf-probe.{ext}"
# A bare `- *...` list item: YAML reads the value as an alias. The value ends
# before trailing blanks or a comment (a `#` after a blank), which stay after it.
BARE_GLOB_ITEM_RE = re.compile(r"^([ \t]*-[ \t]+)(\*[^'\"\n]*?)((?:[ \t]+#[^\n]*)?|[ \t]*)$", re.MULTILINE)


class HelperError(Exception):
    """A handled failure that ends the run with a JSON error and exit `code`."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _payload_safe(text) -> str:
    """Make text safe for a single-quoted `echo '...'` payload.

    `'` becomes a backtick, a backslash becomes `/`, and control characters
    and lone surrogates become `?`: dash's `echo` rewrites backslash
    escapes, and a surrogate cannot be encoded.
    """
    return "".join(
        "`" if ch == "'" else "/" if ch == "\\" else
        "?" if ord(ch) < 0x20 or ord(ch) == 0x7F or 0xD800 <= ord(ch) <= 0xDFFF else ch
        for ch in str(text))


def _die(code: int, message: str) -> None:
    print(json.dumps({"status": "error", "message": _payload_safe(message)}), file=sys.stderr)
    sys.exit(code)


def _child_env() -> dict:
    """os.environ without the git location variables, plus PYTHONUTF8=1.

    A git hook (for example `git commit -a` running the test suite) exports
    an absolute GIT_INDEX_FILE; inherited by `git -C <other repo>`, it would
    make git read the hook's index instead of the project's.
    """
    env = {k: v for k, v in os.environ.items() if k not in GIT_LOCATION_VARS}
    env["PYTHONUTF8"] = "1"
    return env


def _resolve_outside_cwd(command: str) -> str | None:
    """shutil.which with a CWD-shim guard. Returns the resolved path or None.

    shutil.which on Windows searches the current directory ahead of PATH,
    and CWD here is the repo under analysis — a bare-name lookup resolving
    into CWD would execute a repo-planted shim (e.g. ccc.cmd). Such a
    resolution is treated as not-found. Explicit paths supplied by callers
    (containing a separator) are honored as-is. Keep identical to the
    sibling guards in skf-detect-tools.py,
    skf-qmd-classify-collections.py, skf-ccc-git-hygiene.py,
    skf-source-tree.py, skf-tessl-review.py and
    skf-verify-provenance-completeness.py.
    """
    resolved = shutil.which(command)
    if resolved is None:
        return None
    if os.sep in command or (os.altsep and os.altsep in command):
        return resolved
    resolved_dir = os.path.dirname(resolved)
    if resolved_dir:
        cwd = os.path.normcase(os.path.abspath(os.getcwd()))
        if os.path.normcase(os.path.abspath(resolved_dir)) == cwd:
            return None
    return resolved


def _atomic_write(target: Path, content: str, unique: bool = False) -> None:
    """Crash-safe write via temp + fsync + rename. Mirrors skf-atomic-write.py.

    With `unique`, the temp file is one of this call's own (clone mode,
    where two runs can write the same file at once), else `<name>.skf-tmp`.
    Raises HelperError(2) on any OS failure; the temp file is removed.
    """
    tmp = target.with_name(target.name + ".skf-tmp")
    if unique:
        tmp = target.with_name(f"{target.name}.{os.getpid()}.{os.urandom(4).hex()}.skf-tmp")
    # O_BINARY (Windows only; 0 elsewhere) suppresses the text-mode \n -> \r\n
    # translation that would otherwise corrupt verbatim writes on Windows.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(tmp, flags, 0o644)
        try:
            os.write(fd, content.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, target)
    except OSError as e:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise HelperError(2, f"atomic write failed for {target}: {e}")


# ─── External commands (git, ccc) ───────────────────────────────────────────


def _git(root: Path, *args: str, literal: bool = False) -> tuple[int, bytes, str] | None:
    """Run `git -C root <args>`. Return (returncode, stdout bytes, stderr text).

    Returns None when git cannot be resolved or fails to start, and
    (-1, b"", "") on timeout. `literal=True` adds `--literal-pathspecs` so a
    folder value such as `:odd` is never read as pathspec magic — only for
    `ls-files`: `check-ignore` rejects that flag. git runs with LC_ALL=C so
    its "not a git repository" message can be recognised in any locale.
    """
    exe = _resolve_outside_cwd("git")
    if exe is None:
        return None
    argv = [exe, *(["--literal-pathspecs"] if literal else []), "-C", str(root), *args]
    env = _child_env()
    env["LC_ALL"] = "C"
    try:
        result = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env=env,
            timeout=GIT_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return -1, b"", ""
    except (OSError, ValueError):
        return None
    return result.returncode, result.stdout, result.stderr.decode("utf-8", errors="replace")


def run_ccc_init(root: Path) -> tuple[bool, str]:
    """Run `ccc init -f` in root. Return (exit code was 0, condensed output).

    The caller judges success by whether settings.yml exists afterwards,
    not by the exit code. Output is stdout plus stderr, decoded as UTF-8,
    whitespace-collapsed and cut to 300 characters.
    """
    exe = _resolve_outside_cwd("ccc")
    if exe is None:
        return False, "ccc was not found on PATH"
    try:
        result = subprocess.run(
            [exe, "init", "-f"],
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env=_child_env(),
            timeout=CCC_INIT_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return False, f"ccc init timed out after {CCC_INIT_TIMEOUT_SEC}s"
    except (OSError, ValueError) as e:
        return False, f"ccc init could not start: {e}"
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    return result.returncode == 0, " ".join(output.split())[:300]


# ─── Config-value normalization and validation ─────────────────────────────


def resolve_repo_relative(raw_value, project_root: Path) -> str:
    """Normalize a config value like '{project-root}/skills/' to 'skills'.

    Strips whitespace, turns `\\` into `/`, drops a leading
    `{project-root}/` (`{project-root}` alone gives ""), and collapses
    `./`, `//` and a trailing `/`. Absolute paths and `..` segments are
    kept so validate_config_value can refuse them.
    """
    if raw_value is None:
        return ""
    value = str(raw_value).strip().replace("\\", "/")
    if value.startswith("{project-root}/"):
        value = value[len("{project-root}/"):]
    elif value == "{project-root}":
        value = ""
    return PurePosixPath(value).as_posix() if value else ""


def validate_config_value(key: str, raw_value) -> tuple[str | None, str | None]:
    """Validate a folder value used as a root-anchored ccc exclusion.

    Returns (cleaned_value, warning_or_None). When cleaned_value is None
    the value was rejected and the caller must not add the pattern. The
    first failing rule wins.
    """
    if raw_value is None or str(raw_value).strip() in ("", "."):
        return None, (
            f"{key} is empty or whitespace-only; refused for ccc exclusion because "
            f"an empty pattern would exclude the entire repository from indexing; "
            f"{FIX_HINT}"
        )

    value = str(raw_value).strip()

    if value.startswith(("/", "~", "./")) or re.match(r"^[A-Za-z]:", value) or value.endswith("/"):
        return None, (
            f"{key} is an absolute or anchored path; refused for ccc exclusion "
            f"because SKF exclusions are relative to the project root; "
            f"{FIX_HINT} to a repo-relative path"
        )

    if ".." in PurePosixPath(value).parts:
        return None, (
            f"{key} contains a .. segment; refused for ccc exclusion because the "
            f"folder must sit inside the project; {FIX_HINT}"
        )

    if value.startswith("!"):
        return None, (
            f"{key} starts with !, which ccc reads as a negation; refused for ccc "
            f"exclusion; {FIX_HINT}"
        )

    if any(ch in GLOB_META_CHARS for ch in value):
        return None, (
            f"{key} contains a glob meta-character (*, ?, [, ] or a backslash); "
            f"refused for ccc exclusion because ccc would read it as pattern "
            f"syntax; {FIX_HINT}"
        )

    if any(ch in PLACEHOLDER_CHARS for ch in value):
        return None, (
            f"{key} contains an unresolved template placeholder ({{ or }}); "
            f"refused for ccc exclusion because the step is supposed to forward "
            f"the raw config value and let this script resolve the project-root placeholder"
        )

    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        return None, (
            f"{key} contains a control character; refused for ccc exclusion "
            f"because it does not survive a quoted shell payload; {FIX_HINT}"
        )

    if "'" in value:
        return None, (
            f"{key} contains a single quote, which breaks a single-quoted shell payload; "
            f"refused for ccc exclusion; {FIX_HINT}"
        )

    return value, None


# ─── Pattern assembly ───────────────────────────────────────────────────────


def assemble_patterns(skills_output_folder: str, forge_data_folder: str
                      ) -> tuple[list[str], list[str]]:
    """Return (patterns, warnings) without touching the filesystem.

    Patterns are the 4 unconditional ones plus each folder value that
    passed validation, anchored as-is (a value shared by both folders
    appears once). The merge itself also runs the collision check, which
    this pure helper does not.
    """
    patterns = list(ALWAYS_INCLUDE)
    warnings: list[str] = []
    for (key, _kind), raw in zip(FOLDER_KEYS, (skills_output_folder, forge_data_folder)):
        cleaned, warn = validate_config_value(key, raw)
        if cleaned is None:
            warnings.append(warn)
        elif cleaned not in patterns:
            patterns.append(cleaned)
    return patterns, warnings


# ─── Folder check ───────────────────────────────────────────────────────────


# Only `.gitignore` files: ccc reads no other ignore file, so an entry that
# `.git/info/exclude` or a global excludes file hides is still indexed.
_LS_FILES_ARGS = ("ls-files", "-z", "--cached", "--others",
                  "--exclude-per-directory=.gitignore")


def _ls_files(cwd: Path, *pathspec: str) -> tuple[list[str] | None, str | None]:
    """Run `git ls-files` in cwd. Return (records, problem).

    records None means the listing is unavailable. problem is None for a
    silent skip (git missing, not a git repository) and otherwise a short
    description for a warning (timeout, any other git failure such as a
    repository git refuses as unsafe).
    """
    res = _git(cwd, *_LS_FILES_ARGS, *(("--", *pathspec) if pathspec else ()), literal=True)
    if res is None:
        return None, None
    returncode, stdout, stderr = res
    if returncode == -1:
        return None, "git ls-files timed out"
    if returncode != 0:
        if "not a git repository" in stderr.lower():
            return None, None
        detail = next((line.strip() for line in stderr.splitlines() if line.strip()),
                      f"exit code {returncode}")
        return None, f"git ls-files failed ({detail[:200]})"
    # surrogateescape keeps an undecodable name equal to the name
    # os.listdir returns, so the existence check and the disk match still
    # find it; _unwritable then refuses it a pattern.
    return [r.decode("utf-8", errors="surrogateescape") for r in stdout.split(b"\0") if r], None


def list_folder_paths(root: Path, folder: str) -> tuple[list[tuple[str, ...]] | None, str | None]:
    """Return (paths relative to folder, problem).

    Lists tracked files plus untracked files no `.gitignore` excludes (the
    only ignore files ccc reads); a tracked file deleted from the worktree
    is dropped, since ccc cannot see it. A missing folder gives ([], None).
    None paths mean the check is skipped; problem (see _ls_files) says
    whether that deserves a warning. When git reports the folder itself as
    one entry — a submodule or a nested repository, which ccc indexes like
    any other folder — its own files are listed from inside it. A nested
    repository deeper down comes back as a single directory entry, which
    the classifier treats as a group.
    """
    if not (root / folder).is_dir():
        return [], None
    records, problem = _ls_files(root, folder)
    if records is None:
        return None, problem
    depth = len(PurePosixPath(folder).parts)
    cwd = root
    if any(len(PurePosixPath(r).parts) <= depth for r in records):
        records, problem = _ls_files(root / folder)
        if records is None:
            return None, problem
        depth = 0
        cwd = root / folder
    found: set[tuple[str, ...]] = set()
    for record in records:
        if not os.path.lexists(cwd / record):
            continue
        parts = PurePosixPath(record).parts[depth:]
        if parts:
            found.add(parts)
    return sorted(found), None


# Keep identical to _has_skf_metadata in skf-skill-inventory.py
# (test/test-skf-skill-inventory.py pins the copies).
def _has_skf_metadata(path: Path) -> bool:
    """True when a flat skill's metadata.json carries an SKF marker."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    generated_by = data.get("generated_by")
    if isinstance(generated_by, str) and generated_by in SKF_GENERATORS:
        return True
    tool_versions = data.get("tool_versions")
    if isinstance(tool_versions, dict) and "skf" in tool_versions:
        return True
    return (data.get("skill_type") in ("single", "individual", "stack")
            and ("forge_tier" in data or "confidence_tier" in data))


# Keep identical to _is_link_or_junction in skf-atomic-write.py
# (test/test-skf-skill-inventory.py pins the copies).
def _is_link_or_junction(p: Path) -> bool:
    """True for POSIX symlinks AND Windows junctions/symlinks.

    `Path.is_symlink()` is False for Windows junctions; os.readlink succeeds
    for both symlinks and junctions (since CPython 3.8 on Windows). A regular
    directory raises OSError on readlink, which is the signal we want to
    refuse replacement. On Windows, any other reparse point (a cloud-sync
    placeholder, a deduplicated file, an app execution alias) raises
    ValueError: it does not redirect to another path, so it is not a link.
    """
    if p.is_symlink():
        return True
    if not p.exists() and not p.is_symlink():
        return False
    try:
        os.readlink(p)
        return True
    except (OSError, ValueError):
        return False


# Keep identical to _is_marked_version in skf-skill-inventory.py
# (test/test-skf-skill-inventory.py pins the copies).
def _is_marked_version(version_dir: Path, name: str) -> bool:
    """True when `version_dir/name/metadata.json` carries an SKF marker.

    SKF never links a version folder or the package inside one: a linked
    one is not its output, whatever the metadata behind the link says.
    """
    package = version_dir / name
    return (not _is_link_or_junction(version_dir) and not _is_link_or_junction(package)
            and _has_skf_metadata(package / "metadata.json"))


# Keep identical to _has_skf_evidence in skf-skill-inventory.py
# (test/test-skf-skill-inventory.py pins the copies).
def _has_skf_evidence(group_dir: Path, name: str) -> bool:
    """True when skill group `group_dir` holds evidence that SKF generated it.

    Evidence is the `_batch` name, `.skf-` in the name, a marked root
    `metadata.json`, or a marked version folder (`.skf-` staging folders
    aside). The versioned layout, an `active` link, a manifest key or a
    result file are not evidence on their own, and a linked group holds none.
    """
    if _is_link_or_junction(group_dir):
        return False
    if name == "_batch" or ".skf-" in name:
        return True
    if _has_skf_metadata(group_dir / "metadata.json"):
        return True
    try:
        children = list(group_dir.iterdir())
    except OSError:
        return False
    return any(".skf-" not in child.name and child.is_dir() and _is_marked_version(child, name)
               for child in children)


# Keep identical to _has_forge_evidence in skf-skill-inventory.py
# (test/test-skf-skill-inventory.py pins the copies).
def _has_forge_evidence(group_dir: Path, name: str) -> bool:
    """True when forge group `group_dir` holds evidence that SKF generated it.

    Evidence is `.skf-` in the name, SKF's own `_campaign` or
    `improvement-queue` folder, a skill brief (`skill-brief.yaml*` or
    `.brief-draft.json`) or a `*-result*.json` file directly in the group, or
    a provenance map, evidence report, extraction rules or `*-result*.json`
    file directly in a folder of the group (`.skf-` staging folders aside).
    A linked group, folder or file is never evidence.
    """
    if _is_link_or_junction(group_dir):
        return False
    if ".skf-" in name or name in FORGE_GROUP_DIRS:
        return True
    try:
        children = list(group_dir.iterdir())
    except OSError:
        return False
    for child in children:
        entry = child.name
        if _is_link_or_junction(child):
            continue
        if child.is_file():
            if (entry.startswith("skill-brief.yaml") or entry == ".brief-draft.json"
                    or RESULT_JSON_RE.match(entry)):
                return True
        elif child.is_dir() and ".skf-" not in entry:
            try:
                inner = list(child.iterdir())
            except OSError:
                continue
            if any((f.name in FORGE_VERSION_ANCHORS or RESULT_JSON_RE.match(f.name))
                   and not _is_link_or_junction(f) and f.is_file() for f in inner):
                return True
    return False


def _skf_group(base: Path, kind: str, group: str) -> bool:
    """True when first-level entry `group` under the folder is SKF output of `kind`.

    Both kinds follow the rule the workflows use before they write into,
    move or delete a skill's folders (skf-skill-inventory.py), read from the
    group on disk, so ccc excludes exactly the groups the workflows treat as
    SKF output.
    """
    if kind == "skills":
        return _has_skf_evidence(base / group, group)
    return _has_forge_evidence(base / group, group)


def _skf_root_file(kind: str, name: str) -> bool:
    """True when a file directly under the folder is SKF output."""
    return bool(
        ".skf-" in name
        or RESULT_JSON_RE.match(name)
        or (kind == "skills" and name == ".export-manifest.json")
        or (kind == "forge" and name.startswith(FORGE_ROOT_PREFIXES))
    )


def _holds_other_folder(folder: str, group: str, other_folders) -> bool:
    """True when folder/group is, or contains, another configured SKF folder."""
    group_parts = PurePosixPath(folder, group).parts
    return any(PurePosixPath(other).parts[:len(group_parts)] == group_parts
               for other in other_folders)


class FolderScan(NamedTuple):
    """What classify_folder found in one configured folder."""

    foreign: list[str]       # the entries SKF did not generate that decide the verdict
    owned_groups: list[str]  # first-level directories SKF generated
    owned_files: list[str]   # root files SKF generated
    has_output: bool         # any SKF output, a group holding the other folder included
    listed: frozenset        # every first-level name git listed


def classify_folder(root: Path, folder: str, kind, paths, other_folders=(),
                    hidden_neutral: bool = False) -> FolderScan:
    """Classify the first-level entries of a configured folder.

    `kind` is "skills" or "forge", or a collection of both when the two
    folder values are the same folder; an entry is SKF output when any of
    the kinds accepts it. `paths` comes from list_folder_paths. A group
    that is, or contains, another configured SKF folder (`other_folders`)
    is SKF output but gets no pattern of its own: that folder is reconciled
    separately. A single-segment entry that is a directory on disk (a
    nested repository or submodule) is a group, not a root file.
    `foreign`: any foreign group gives the foreign groups, as `name/`, then
    the other root files; otherwise other root files count only when the
    folder holds no SKF output at all. Neutral entries never count; with
    `hidden_neutral` (ccc's `**/.*` default is active) neither does any
    other dot-named entry that is not SKF output.
    """
    kinds = {kind} if isinstance(kind, str) else set(kind)
    base = root / folder
    groups: dict[str, list[tuple[str, ...]]] = {}
    other_root: list[str] = []
    owned_files: list[str] = []
    for rel in paths:
        if len(rel) == 1 and not (base / rel[0]).is_dir():
            name = rel[0]
            if any(_skf_root_file(k, name) for k in kinds):
                owned_files.append(name)
            elif not (name in NEUTRAL_ROOT_FILES or README_RE.match(name)
                      or (hidden_neutral and name.startswith("."))):
                other_root.append(name)
            continue
        members = groups.setdefault(rel[0], [])
        if len(rel) > 1:
            members.append(rel)
    foreign_groups: list[str] = []
    owned_groups: list[str] = []
    holds_other = False
    for group in sorted(groups):
        if _holds_other_folder(folder, group, other_folders):
            holds_other = True
        elif any(_skf_group(base, k, group) for k in kinds):
            owned_groups.append(group)
        elif hidden_neutral and group.startswith("."):
            continue
        else:
            foreign_groups.append(group + "/")
    has_output = bool(owned_files or owned_groups or holds_other)
    if foreign_groups:
        foreign = foreign_groups + other_root
    elif other_root and not has_output:
        foreign = other_root
    else:
        foreign = []
    listed = frozenset(groups) | frozenset(owned_files) | frozenset(other_root) | frozenset(
        rel[0] for rel in paths if len(rel) == 1)
    return FolderScan(foreign, owned_groups, sorted(owned_files), has_output, listed)


def ccc_literal(name: str) -> str:
    """Return `name` as a ccc glob that matches only itself.

    Each glob character becomes a one-character class, as the escape
    function of ccc's glob library (globset) does. Backslash escapes are
    never used: globset turns them off on Windows and reads a backslash
    there as `/`.
    """
    return "".join(f"[{ch}]" if ch in CCC_CLASS_ESCAPES else ch for ch in name)


def _unwritable(name: str) -> bool:
    """True when a name cannot go into a pattern.

    A `'` breaks a single-quoted shell payload, a backslash or a control
    character does not survive `echo` in dash, a replacement character
    stands for a name that could not be decoded, and a surrogate (bytes on
    disk that are not UTF-8) makes ccc fail on the whole pattern list.
    """
    return any(ch in "'\\\ufffd" or ord(ch) < 0x20 or ord(ch) == 0x7F
               or 0xD800 <= ord(ch) <= 0xDFFF for ch in name)


def _norm(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def _on_disk(name: str, disk: list[str] | None, listed=frozenset()) -> list[str]:
    """The names ccc sees for `name`: itself when listed on disk, else the
    entries equal to it up to Unicode normalization and case (macOS,
    Windows), else none (the entry is gone). No listing: `name` itself."""
    if disk is None or name in disk:
        return [name]
    key = _norm(name)
    return [d for d in disk if d not in listed and _norm(d) == key]


def entry_patterns(folder: str, kind, owned_groups, owned_files, disk, listed=frozenset()
                   ) -> tuple[list[str], list[str]]:
    """Return (patterns, skipped names) that exclude the SKF entries one by one.

    Each pattern is `{folder}/` plus one entry name as it is on disk (`disk`,
    from os.listdir; None when unreadable), glob characters written as
    classes. The fixed entries and result stems of each kind, and every
    forge report prefix, are always included, so output SKF writes before
    the next setup run is covered. Timestamped root results share one
    `{folder}/{stem}-result*.json` and forge reports one `{folder}/{prefix}*`.
    Never a `!` negation: ccc applies it to every pattern, its own defaults
    included. Skipped names are SKF entries `_unwritable` refuses.
    """
    kinds = {kind} if isinstance(kind, str) else set(kind)
    patterns: set[str] = set()
    skipped: set[str] = set()
    exact = list(owned_groups)
    for kind_ in kinds:
        exact.extend(SKF_FIXED_ENTRIES[kind_])
        for stem in SKF_ROOT_RESULT_STEMS[kind_]:
            patterns.add(f"{folder}/{stem}-result*.json")
        if kind_ == "forge":
            patterns.update(f"{folder}/{prefix}*" for prefix in FORGE_ROOT_PREFIXES)
    for name in owned_files:
        prefix = next((p for p in FORGE_ROOT_PREFIXES if name.startswith(p)), None)
        if "forge" in kinds and prefix:
            patterns.add(f"{folder}/{prefix}*")
            continue
        m = RESULT_JSON_RE.match(name)
        if m:
            patterns.add(f"{folder}/{m.group(1)}-result*.json")
            continue
        exact.append(name)
    fixed = {n for k in kinds for n in SKF_FIXED_ENTRIES[k]}
    for name in dict.fromkeys(exact):
        if name in fixed and (disk is None or name not in disk):
            patterns.add(f"{folder}/{ccc_literal(name)}")
            continue
        if _unwritable(name):
            skipped.add(name)
            continue
        for real in _on_disk(name, disk, listed):
            if _unwritable(real):
                skipped.add(real)
            else:
                patterns.add(f"{folder}/{ccc_literal(real)}")
    return sorted(patterns), sorted(skipped)


# ─── settings.yml and the ownership record ─────────────────────────────────


def load_settings(path: Path) -> dict:
    """Parse settings.yml. An empty file gives {}.

    Raises HelperError(1) when the file cannot be read or parsed, is not a
    mapping, or has an exclude_patterns that is neither a list nor null.
    """
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, ValueError) as e:
        raise HelperError(1, f"failed to parse {path}: {e}")
    except OSError as e:
        raise HelperError(1, f"failed to read {path}: {e}")
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise HelperError(1, f"expected mapping at top of {path}, got {type(data).__name__}")
    excludes = data.get("exclude_patterns")
    if excludes is not None and not isinstance(excludes, list):
        raise HelperError(1, f"exclude_patterns in {path} is not a list "
                             f"(got {type(excludes).__name__})")
    return data


def needs_rebuild(data: dict) -> bool:
    """True when the file lacks the ccc defaults and must be rebuilt.

    Every file ccc writes has both `exclude_patterns` (including
    `**/.cocoindex_code`) and `include_patterns`.
    """
    if "exclude_patterns" not in data:
        return True
    excludes = [str(p) for p in (data.get("exclude_patterns") or [])]
    return "include_patterns" not in data and CCC_SELF_EXCLUDE not in excludes


def read_owned_record(path, warnings: list[str]) -> list[str]:
    """Return `ccc_index.exclude_patterns` from forge-tier.yaml, or [].

    A missing path or file, or a non-list value, gives [] silently; an
    unreadable or unparseable file gives [] plus a warning.
    """
    if path is None:
        return []
    path = Path(path)
    if not path.is_file():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError):
        warnings.append("could not read the SKF exclusion record in forge-tier.yaml; "
                        "treated it as empty")
        return []
    ccc = data.get("ccc_index") if isinstance(data, dict) else None
    record = ccc.get("exclude_patterns") if isinstance(ccc, dict) else None
    return [str(p) for p in record] if isinstance(record, list) else []


def plan_exclusions(existing: list[str], produced: list[str], owned_prior, prune_allowed: bool
                    ) -> tuple[list[str], list[str], list[str]]:
    """Return (merged, added, removed).

    Removes the entries of `existing` that SKF owned and no longer produces
    (only when `prune_allowed`), keeps every other entry in order, and
    appends the produced patterns not already kept.
    """
    removable = (set(owned_prior) - set(produced)) if prune_allowed else set()
    kept = [e for e in existing if e not in removable]
    removed: list[str] = []
    for e in existing:
        if e in removable and e not in removed:
            removed.append(e)
    added: list[str] = []
    for p in produced:
        if p not in kept and p not in added:
            added.append(p)
    return kept + added, added, removed


def decide_index_action(ready: bool, skip_index: bool, written: bool, index_fresh: bool,
                        usable: bool = True) -> str:
    """Return one of INDEX_ACTIONS for the step to act on.

    `usable` is False when settings.yml exists but still lacks the ccc
    defaults (a failed rebuild): a fresh index is kept, but no new index is
    built from that file.
    """
    if not ready:
        return "fail"
    if skip_index:
        return "skip"
    if not usable:
        return "keep" if index_fresh else "fail"
    if written or not index_fresh:
        return "index"
    return "keep"


# ─── Merge ──────────────────────────────────────────────────────────────────


def _read_bytes_or_none(path: Path) -> bytes | None:
    try:
        return path.read_bytes() if path.is_file() else None
    except OSError:
        return None


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _output_hint(output: str) -> str:
    return output or "no output"


def _prepare_settings(root: Path, target: Path, backup: Path, allow_ccc_init: bool,
                      state: dict, warnings: list[str]) -> dict | None:
    """Bring settings.yml to a reconcilable state.

    Returns the parsed data to reconcile, or None when this run must not
    touch the SKF patterns (not ready, rebuild skipped or failed, or ccc
    wrote no exclude_patterns list).
    """
    if not state["existed"]:
        if not allow_ccc_init:
            state.update(ready=False,
                         reason="settings.yml is missing and --no-ccc-init was given")
            return None
        _ok, output = run_ccc_init(root)
        if not target.is_file():
            state.update(ready=False, ccc_init="failed",
                         reason=("ccc init did not create .cocoindex_code/settings.yml "
                                 f"({_output_hint(output)})"))
            return None
        state.update(ccc_init="created", written=True)
        data = load_settings(target)
        if not isinstance(data.get("exclude_patterns"), list):
            warnings.append("ccc init wrote no exclude_patterns list, so SKF left its "
                            "exclusions out rather than replace the ccc defaults")
            return None
        return data

    data = load_settings(target)
    if not needs_rebuild(data):
        return data
    if not allow_ccc_init:
        warnings.append("settings.yml lacks the ccc default exclusions; rebuild skipped "
                        "because --no-ccc-init was given")
        return None

    original = data
    try:
        os.replace(target, backup)
    except OSError as e:
        raise HelperError(2, f"could not move {target} aside to {backup.name}: {e}")
    _ok, output = run_ccc_init(root)
    fresh = None
    if target.is_file():
        try:
            fresh = load_settings(target)
        except HelperError:
            fresh = None
    if fresh is None or not isinstance(fresh.get("exclude_patterns"), list):
        try:
            os.replace(backup, target)
        except OSError as e:
            raise HelperError(2, f"could not restore {target} from {backup.name}: {e}")
        state["ccc_init"] = "failed"
        state["index_block"] = ("settings.yml lacks the ccc default exclusions and ccc init "
                                f"could not rebuild it ({_output_hint(output)})")
        warnings.append(
            "could not rebuild .cocoindex_code/settings.yml on the ccc defaults because "
            f"ccc init failed ({_output_hint(output)}); the file was left unchanged and "
            "SKF exclusions were not updated this run; fix ccc init in {project-root} "
            "and re-run /skf-setup"
        )
        return None

    fresh_excludes = [str(p) for p in fresh["exclude_patterns"]]
    original_excludes = [str(p) for p in (original.get("exclude_patterns") or [])]
    data = {**fresh, **{k: v for k, v in original.items() if k != "exclude_patterns"}}
    data["exclude_patterns"] = fresh_excludes + [
        e for e in original_excludes if e not in fresh_excludes
    ]
    state.update(ccc_init="rebuilt", written=True)
    warnings.append(
        "rebuilt .cocoindex_code/settings.yml on the ccc defaults: it lacked them, so "
        "ccc was also indexing hidden folders, node_modules and its own database; your "
        "own entries were kept"
    )
    return data


def _inside_always_excluded(value: str) -> bool:
    """True when an always-included `**/<name>` pattern already covers the folder."""
    return any(f"**/{part}" in ALWAYS_INCLUDE for part in PurePosixPath(value).parts)


def _printable(name: str) -> str:
    """A name safe to show in a warning: backslashes and control characters become `?`."""
    return "".join("?" if ch == "\\" or ord(ch) < 0x20 or ord(ch) == 0x7F
                   or 0xD800 <= ord(ch) <= 0xDFFF else ch for ch in name)


def _sample(names: list[str]) -> str:
    return ", ".join(_printable(n) for n in names[:SAMPLE_SIZE])


def _collision_warning(key: str, value: str, foreign: list[str], kinds) -> str:
    installed = (
        " If those are skills installed from elsewhere, keep the folder: once SKF has "
        "written its own output there, re-run /skf-setup and SKF excludes only its own "
        "entries."
    ) if "skills" in kinds else ""
    return (
        f"{key} {value} already holds {_plural(len(foreign), 'entry', 'entries')} SKF did "
        f"not generate and no SKF output (for example {_sample(foreign)}), so SKF left it "
        f"out of the ccc exclusions and that content stays indexed. If that is source you "
        f"work on, set {key} in {{project-root}}/_bmad/skf/config.yaml to a folder only SKF "
        f"uses and re-run /skf-setup.{installed} To exclude it anyway, add {value} to "
        f"exclude_patterns in .cocoindex_code/settings.yml yourself; SKF never removes "
        f"entries it did not add"
    )


def _shared_folder_note(key: str, value: str, foreign: list[str], kinds) -> str:
    later = (
        "A skill SKF creates there later stays indexed, twice through its version folder "
        "and its active link, until you re-run /skf-setup."
    ) if "skills" in kinds else (
        "Output SKF writes there later stays indexed until you re-run /skf-setup."
    )
    return (
        f"{key} {value} also holds {_plural(len(foreign), 'entry', 'entries')} SKF did not "
        f"generate (for example {_sample(foreign)}), so SKF excluded only its own entries "
        f"there and those stay indexed. {later} To exclude the other entries too, add each "
        f"as {value}/<name> to exclude_patterns in .cocoindex_code/settings.yml yourself; "
        f"SKF never removes entries it did not add"
    )


def _unowned_entry_warning(key: str, value: str, foreign: list[str]) -> str:
    return (
        f"{key} {value} is in exclude_patterns in .cocoindex_code/settings.yml but SKF has "
        f"no record of adding it, so SKF left it in place; it also excludes "
        f"{_plural(len(foreign), 'entry', 'entries')} SKF did not generate (for example "
        f"{_sample(foreign)}). If those should stay searchable, remove {value} from "
        f"exclude_patterns and re-run /skf-setup; SKF then excludes only its own output there"
    )


def _unwritable_warning(key: str, value: str, skipped: list[str]) -> str:
    return (
        f"{key} {value} holds {_plural(len(skipped), 'SKF entry', 'SKF entries')} whose "
        f"name SKF cannot write as a ccc pattern (a quote, a backslash, a control character "
        f"or bytes that are not UTF-8; for example {_sample(skipped)}), so they stay indexed; "
        f"rename them, or add them to exclude_patterns in .cocoindex_code/settings.yml "
        f"yourself"
    )


# ─── a user `!` entry that cancels an SKF pattern ──────────────────────────

# The child name ccc's matcher probes an excluded directory with when it
# checks whether a `!` entry applies below it.
CCC_DIR_PROBE = "__probe__"
# Brace alternatives of one `!` entry checked at most, and `{` in one entry
# expanded at most (guards, not limits any real entry reaches).
MAX_BRACE_ALTERNATIVES = 256
MAX_BRACE_GROUPS = 64
# ccc reads settings.yml on the machine this helper runs on, and its glob
# library reads a backslash as `/` on Windows and as an escape elsewhere.
CCC_BACKSLASH_IS_SLASH = os.name == "nt"


def _brace_alternatives(pattern: str) -> list[str]:
    """Expand the `{a,b}` groups of a glob as ccc does before its prefix check.

    Nested groups recurse, braces and commas inside `[...]` are literal, and
    an unbalanced group leaves the pattern as it is. A pattern with more
    than MAX_BRACE_GROUPS `{` is left as it is too, so the recursion stays
    shallow whatever the entry holds.
    """
    if pattern.count("{") > MAX_BRACE_GROUPS:
        return [pattern]
    in_class = False
    for i, ch in enumerate(pattern):
        if ch == "[":
            in_class = True
        elif ch == "]":
            in_class = False
        elif ch == "{" and not in_class:
            depth, inner_class, start, alternatives, j = 1, False, i + 1, [], i + 1
            while j < len(pattern) and depth:
                c = pattern[j]
                if c == "[":
                    inner_class = True
                elif c == "]":
                    inner_class = False
                elif c == "{" and not inner_class:
                    depth += 1
                elif c == "}" and not inner_class:
                    depth -= 1
                    if depth == 0:
                        alternatives.append(pattern[start:j])
                elif c == "," and not inner_class and depth == 1:
                    alternatives.append(pattern[start:j])
                    start = j + 1
                j += 1
            if depth:
                return [pattern]
            out: list[str] = []
            for alternative in alternatives:
                out.extend(_brace_alternatives(pattern[:i] + alternative + pattern[j:]))
                if len(out) >= MAX_BRACE_ALTERNATIVES:
                    return out[:MAX_BRACE_ALTERNATIVES]
            return out
    return [pattern]


def _ccc_glob_regex(glob: str, backslash_escape: bool):
    """A regex for one brace-free glob as ccc's glob library reads it, or None.

    `*` and `?` also match `/`; `**/` at the start, `/**/` inside and `/**`
    at the end span whole directories; `[...]` and `[!...]` or `[^...]` are
    classes. A backslash escapes the next character when `backslash_escape`
    is set (POSIX); otherwise the caller has already turned it into `/`
    (Windows).
    """
    collapsed = None
    while collapsed != glob:  # `**/**` spans what one `**` spans
        collapsed = glob
        glob = glob.replace("/**/**", "/**")
        if glob.startswith("**/**"):
            glob = glob[3:]
    if glob in ("**", "**/"):
        return re.compile(".*", re.S)
    out, i, n = [], 0, len(glob)
    if glob.startswith("**/"):
        out.append("(?:.*/)?")
        i = 3
    while i < n:
        ch = glob[i]
        if glob.startswith("/**/", i):
            out.append("(?:/|/.*/)")
            i += 4
        elif glob.startswith("/**", i) and i + 3 == n:
            out.append("/.*")
            i += 3
        elif ch == "*":
            while i < n and glob[i] == "*":
                i += 1
            out.append(".*")
        elif ch == "?":
            out.append(".")
            i += 1
        elif ch == "[":
            j = i + 1
            negate = j < n and glob[j] in "!^"
            if negate:
                j += 1
            k = j + 1 if j < n and glob[j] == "]" else j
            while k < n and glob[k] != "]":
                k += 1
            if k >= n:
                return None
            body = "".join("\\" + c if c in "\\^[]" else c for c in glob[j:k])
            out.append(f"[{'^' if negate else ''}{body}]")
            i = k + 1
        elif ch == "\\" and backslash_escape:
            if i + 1 >= n:
                return None
            out.append(re.escape(glob[i + 1]))
            i += 2
        else:
            out.append(re.escape(ch))
            i += 1
    try:
        return re.compile("".join(out), re.S)
    except re.error:
        return None


def _ccc_glob(glob: str, backslash_is_slash: bool):
    """`_ccc_glob_regex` for one brace-free glob, its backslashes read as ccc
    reads them on Windows (`/`) or elsewhere (an escape)."""
    if backslash_is_slash:
        return _ccc_glob_regex(glob.replace("\\", "/"), False)
    return _ccc_glob_regex(glob, True)


@functools.lru_cache(maxsize=512)
def _negation_forms(body: str, backslash_is_slash: bool) -> tuple[tuple[str, ...], tuple]:
    """The brace alternatives of a `!` entry's body, and their regexes."""
    alternatives = tuple(_brace_alternatives(body))
    globs = (_ccc_glob(alt, backslash_is_slash) for alt in alternatives)
    return alternatives, tuple(rx for rx in globs if rx is not None)


def _negation_reopens(entry: str, target: str, backslash_is_slash: bool | None = None) -> bool:
    """True when the `!` entry makes ccc walk into or index `target` again.

    ccc keeps an excluded path when a `!` entry matches it, or matches the
    child it probes the path with (`target/__probe__`, so in practice a
    wildcard child), or when one of the entry's brace alternatives starts
    with `target/`: a directory on the way to a re-included path is walked.
    The glob is read as ccc's glob library reads it on this machine
    (CCC_BACKSLASH_IS_SLASH unless `backslash_is_slash` is given).
    """
    if backslash_is_slash is None:
        backslash_is_slash = CCC_BACKSLASH_IS_SLASH
    alternatives, regexes = _negation_forms(entry[1:], backslash_is_slash)
    if any(alt.startswith(target + "/") for alt in alternatives):
        return True
    probe = f"{target}/{CCC_DIR_PROBE}"
    return any(rx.fullmatch(target) or rx.fullmatch(probe) for rx in regexes)


def _pattern_path(pattern: str) -> str | None:
    """The path a pattern SKF wrote names, or None for a real glob.

    Undoes ccc_literal's one-character classes; a `*` left over marks a
    result or report family, which a `!` entry cannot re-open as a folder.
    """
    out, i = [], 0
    while i < len(pattern):
        ch = pattern[i]
        if (ch == "[" and i + 2 < len(pattern) and pattern[i + 2] == "]"
                and pattern[i + 1] in CCC_CLASS_ESCAPES):
            out.append(pattern[i + 1])
            i += 3
            continue
        if ch in CCC_CLASS_ESCAPES:
            return None
        out.append(ch)
        i += 1
    return "".join(out)


def _negation_warning(key: str, value: str, entries: list[str], whole: bool, kinds,
                      everything: bool = True) -> str:
    shown = _sample(entries) + (
        f" and {len(entries) - SAMPLE_SIZE} more" if len(entries) > SAMPLE_SIZE else "")
    it = "that entry" if len(entries) == 1 else "those entries"
    if whole:
        twice = (", twice for each skill through its version folder and its active link"
                 if "skills" in kinds else "")
        always = next((part for part in PurePosixPath(value).parts
                       if f"**/{part}" in ALWAYS_INCLUDE), None)
        own = (
            f"SKF always keeps {always} out of ccc, so keep content you want searchable "
            f"outside it"
        ) if always else (
            f"To keep content of your own in {value} searchable, put it in a folder of its "
            f"own there and re-run /skf-setup; SKF then excludes its entries one by one and "
            f"leaves yours indexed"
        )
        amount = "all" if everything else "some"
        return (
            f"{key} {value} is excluded from ccc as one folder, but exclude_patterns in "
            f".cocoindex_code/settings.yml also lists {shown}: ccc applies a ! entry against "
            f"every exclusion, so {amount} SKF output in {value} is indexed again{twice}. "
            f"Remove {it}; SKF output never needs one. {own}"
        )
    return (
        f"{key} {value} is excluded from ccc one SKF entry at a time, but exclude_patterns "
        f"in .cocoindex_code/settings.yml also lists {shown}: ccc applies a ! entry against "
        f"every exclusion, so some SKF output there is indexed again. Remove {it}; your own "
        f"content in {value} stays indexed without it"
    )


def _negation_warnings(root: Path, merged: list[str], by_value: dict, verdicts: dict,
                       value_patterns: dict, listings: dict) -> list[str]:
    """One warning per folder a user `!` entry brings SKF output back into ccc for.

    Only bare and per-entry verdicts are checked, against `merged` (the
    exclude_patterns this run writes). A pattern counts when ccc walks down
    to a file of SKF output below it that git lists (`listings` holds the
    verdict loop's (paths, scan) per folder; a folder inside an
    always-excluded one is listed here), or, with no such file, into the
    child it probes the pattern with, as output SKF writes there later
    would be. The `!` entries that re-open a pattern that counts are named;
    the bare value's warning says all SKF output is back only when every
    SKF entry there is reached.
    """
    negations = [e for e in merged if e.startswith("!")]
    if not negations:
        return []
    slash = CCC_BACKSLASH_IS_SLASH
    # A pattern with no glob character left (SKF's own, mostly) matches one path.
    literal = {path for path in (_pattern_path(p) for p in merged
                                 if not p.startswith("!") and "\\" not in p) if path}
    globs = [_ccc_glob(alt, slash) for p in merged
             if not p.startswith("!") and ("\\" in p or _pattern_path(p) is None)
             for alt in _brace_alternatives(p)]
    excludes = [rx for rx in globs if rx is not None]
    kept: dict[str, bool] = {}

    def walked(path: str) -> bool:
        """True when ccc walks every directory down to `path`, and `path` itself:
        each is matched by no exclude pattern, or re-opened by a `!` entry."""
        parts = PurePosixPath(path).parts
        for depth in range(1, len(parts) + 1):
            step = "/".join(parts[:depth])
            if step not in kept:
                kept[step] = ((step not in literal
                               and not any(rx.fullmatch(step) for rx in excludes))
                              or any(_negation_reopens(n, step, slash) for n in negations))
            if not kept[step]:
                return False
        return True

    out = []
    for value, entries in by_value.items():
        bare = verdicts[value] == "bare"
        if not bare and verdicts[value] != "entries":
            continue
        kinds = {kind for _, kind in entries}
        if value in listings:
            paths, scan = listings[value]
        else:
            paths = list_folder_paths(root, value)[0]
            others = [v for v in by_value if v != value]
            scan = classify_folder(root, value, kinds, paths, others) if paths else None
        owned = set(scan.owned_groups) | set(scan.owned_files) if scan else set()
        files: dict[str, list[str]] = {}  # the listed files under each first-level entry
        for rel in paths or []:
            if not bare or rel[0] in owned:
                files.setdefault(rel[0], []).append("/".join((value, *rel)))
        reached, everything = [], True
        for target in filter(None, map(_pattern_path, value_patterns[value])):
            if target == value:
                hits = [any(map(walked, below)) for below in files.values()]
            else:  # `{value}/<entry>`
                below = files.get(target[len(value) + 1:], [])
                hits = [any(map(walked, below))] if below else []
            if not hits:
                hits = [walked(f"{target}/{CCC_DIR_PROBE}")]
            everything = everything and all(hits)
            if any(hits):
                reached.append(target)
        cancelling = [e for e in negations
                      if any(_negation_reopens(e, t, slash) for t in reached)]
        if cancelling:
            out.append(_negation_warning(" and ".join(k for k, _ in entries), value,
                                         cancelling, bare, kinds, everything))
    return out


def _list_dir(path: Path) -> list[str] | None:
    """The names in `path` as the OS reports them (what ccc matches), or None."""
    try:
        return os.listdir(path)
    except OSError:
        return None


def _contains(outer: str, inner: str) -> bool:
    """True when folder `inner` sits below folder `outer`."""
    o, i = PurePosixPath(outer).parts, PurePosixPath(inner).parts
    return i[:len(o)] == o and len(i) > len(o)


def _stale_bare_values(existing: list[str], record: list[str], folders: list[str]) -> set[str]:
    """Bare folder values SKF wrote after its record was last saved.

    Setup writes settings.yml before it saves the record, so a run stopped in
    between leaves a bare value the record does not hold. When the record
    holds `{value}/...` per-entry patterns for a folder and none of them is
    still in settings.yml, SKF swapped them for the bare value itself: that
    value is SKF's, not the user's. Patterns of another configured folder
    inside this one do not count.
    """
    stale: set[str] = set()
    for value in folders:
        if value not in existing or value in record:
            continue
        inner = [v for v in folders if _contains(value, v)]
        entries = [r for r in record if r.startswith(value + "/")
                   and not any(r == v or r.startswith(v + "/") for v in inner)]
        if entries and not set(entries) & set(existing):
            stale.add(value)
    return stale


def _reconcile(root: Path, target: Path, backup: Path, data: dict,
               values: dict[str, tuple[str, str]], record: list[str], prior_exists: bool,
               prune_allowed: bool, state: dict, warnings: list[str]) -> None:
    """Give each folder a verdict, merge and prune; write settings.yml when it changed.

    Verdicts and record trust follow the module docstring. Folders are
    checked deepest first, so a folder holding another configured folder
    knows that folder's verdict: when it is `entries` or `left_out`, the
    outer folder uses per-entry patterns so its bare value never covers
    content left indexed on purpose.
    """
    existing = [str(p) for p in (data.get("exclude_patterns") or [])]
    # Legacy: a folder-free record (at most the always-included patterns)
    # that is empty or sits next to a `**/<value>` form predates the
    # anchored forms, so those forms count as owned and migrate. A
    # folder-free record without them comes from a run whose folders were
    # all user-excluded or left out, and is trusted like any other.
    folder_free = prior_exists and not (set(record) - set(ALWAYS_INCLUDE))
    legacy_forms = {f"**/{v}" for v, _k in values.values()} & set(existing)
    legacy = folder_free and (not record or bool(legacy_forms))
    owned_prior = set(record) | (legacy_forms if legacy else set())
    trusted = prior_exists and not legacy
    owned_prior |= _stale_bare_values(existing, record, [v for v, _k in values.values()])
    state["legacy"] = legacy
    hidden_neutral = "**/.*" in existing and not any(e.startswith("!") for e in existing)
    by_value: dict[str, list[tuple[str, str]]] = {}
    for key, (value, kind) in values.items():
        by_value.setdefault(value, []).append((key, kind))
    verdicts: dict[str, str] = {}
    value_patterns: dict[str, list[str]] = {}
    listings: dict[str, tuple] = {}
    for value in sorted(by_value, key=lambda v: -len(PurePosixPath(v).parts)):
        entries = by_value[value]
        keys = " and ".join(key for key, _kind in entries)
        if trusted and value in existing and value not in owned_prior:
            verdicts[value], value_patterns[value] = "user", []
            continue
        if _inside_always_excluded(value):
            verdicts[value], value_patterns[value] = "bare", [value]
            continue
        paths, problem = list_folder_paths(root, value)
        if problem:
            warnings.append(f"{problem} for {keys}; collision check skipped")
        others = [v for v in by_value if v != value]
        kinds = {kind for _key, kind in entries}
        scan = (classify_folder(root, value, kinds, paths, others, hidden_neutral)
                if paths else None)
        listings[value] = paths, scan
        deferred = any(_contains(value, v) and verdicts.get(v) in ("entries", "left_out")
                       for v in others)
        if (scan is not None and (scan.foreign or deferred)
                and value in existing and value not in owned_prior):
            # No trusted record says who added the bare value: keep it, and
            # tell the user once (the next run has a trusted record).
            if scan.foreign:
                warnings.append(_unowned_entry_warning(keys, value, scan.foreign))
            verdicts[value], value_patterns[value] = "user", []
            continue
        if scan is not None and scan.foreign and not scan.has_output:
            warnings.append(_collision_warning(keys, value, scan.foreign, kinds))
            verdicts[value], value_patterns[value] = "left_out", []
            continue
        if scan is not None and (scan.foreign or deferred):
            patterns, skipped = entry_patterns(value, kinds, scan.owned_groups,
                                               scan.owned_files, _list_dir(root / value),
                                               scan.listed)
            verdicts[value], value_patterns[value] = "entries", patterns
            if scan.foreign:
                warnings.append(_shared_folder_note(keys, value, scan.foreign, kinds))
            if skipped:
                warnings.append(_unwritable_warning(keys, value, skipped))
            continue
        verdicts[value], value_patterns[value] = "bare", [value]
    produced = list(ALWAYS_INCLUDE)
    for value in by_value:
        for p in value_patterns[value]:
            if p not in produced:
                produced.append(p)

    merged, added, removed = plan_exclusions(existing, produced, owned_prior, prune_allowed)
    warnings.extend(_negation_warnings(root, merged, by_value, verdicts, value_patterns,
                                       listings))
    blocked = [] if prune_allowed else sorted((owned_prior - set(produced)) & set(existing))
    if blocked:
        shown = ", ".join(blocked[:SAMPLE_SIZE]) + (
            f" and {len(blocked) - SAMPLE_SIZE} more" if len(blocked) > SAMPLE_SIZE else "")
        warnings.append(
            "kept previously recorded SKF exclusions (" + shown + ") because a "
            "folder value was refused; fix it and re-run /skf-setup to remove patterns SKF "
            "no longer needs"
        )

    if merged != existing or state["written"]:
        data["exclude_patterns"] = merged
        # ASCII-only output (non-ASCII escaped), as ccc writes it: ccc reads
        # settings.yml with the platform default encoding.
        _atomic_write(target, yaml.safe_dump(data, default_flow_style=False, sort_keys=False))
        state["written"] = True
    if backup.is_file():
        try:
            backup.unlink()
        except OSError as e:
            raise HelperError(2, f"could not remove {backup}: {e}")
    state.update(added=added, removed=removed,
                 present=len(produced) - len(added),
                 effective=sorted(set(produced) | set(blocked)))


def run_merge(project_root, skills_output_folder, forge_data_folder, prior_state_from=None,
              index_fresh: bool = False, skip_index: bool = False,
              allow_ccc_init: bool = True) -> dict:
    """Prepare settings.yml, reconcile the SKF patterns, decide the index action.

    Returns the v2 payload documented in the module docstring. Raises
    HelperError for the exit-1 and exit-2 cases.
    """
    root = Path(project_root)
    target = root / SETTINGS_DIR / SETTINGS_NAME
    backup = target.with_name(BACKUP_NAME)
    gitignore = root / ".gitignore"
    warnings: list[str] = []
    gitignore_before = _read_bytes_or_none(gitignore)

    # Crash recovery: a leftover backup is the pre-repair original.
    if backup.is_file():
        try:
            os.replace(backup, target)
        except OSError as e:
            raise HelperError(2, f"could not restore {target} from {backup.name}: {e}")
        warnings.append("restored .cocoindex_code/settings.yml from an interrupted SKF repair")

    values: dict[str, tuple[str, str]] = {}
    prune_allowed = True
    for (key, kind), raw in zip(FOLDER_KEYS, (skills_output_folder, forge_data_folder)):
        value, warn = validate_config_value(key, resolve_repo_relative(raw, root))
        if value is None:
            prune_allowed = False
            warnings.append(warn)
        else:
            values[key] = (value, kind)

    record = read_owned_record(prior_state_from, warnings)
    # With no forge-tier.yaml at all, SKF never finished a setup here and
    # owns nothing yet; _reconcile decides whether the record is legacy.
    prior_exists = prior_state_from is not None and Path(prior_state_from).is_file()

    state = {
        "existed": target.is_file(),
        "ccc_init": "not_needed",
        "ready": True,
        "reason": None,
        "written": False,
        "added": [],
        "removed": [],
        "present": 0,
        "effective": None,
        "index_block": None,
        "legacy": False,
    }

    data = _prepare_settings(root, target, backup, allow_ccc_init, state, warnings)
    if data is not None:
        _reconcile(root, target, backup, data, values, record, prior_exists, prune_allowed,
                   state, warnings)
        if state["legacy"] and not prune_allowed:
            # Keep the folder-free record so the next valid run can still
            # migrate the legacy `**/<value>` forms of the refused value.
            state["effective"] = None

    if state["ready"] and target.is_file():
        res = _git(root, "check-ignore", "-q", "--no-index", "--",
                   ".cocoindex_code/target_sqlite.db")
        if res is not None and res[0] == 1:
            warnings.append(
                "/.cocoindex_code/ is not gitignored here, so git lists the ccc index "
                "database (tens of MB) as untracked; add /.cocoindex_code/ to "
                "{project-root}/.gitignore"
            )

    action = decide_index_action(state["ready"], skip_index, state["written"], index_fresh,
                                 usable=state["index_block"] is None)
    reason = state["reason"] or (state["index_block"] if action == "fail" else None)
    if action == "skip" and state["written"]:
        warnings.append(
            f"--ccc-skip-index: settings.yml exclusions changed (+{len(state['added'])}, "
            f"-{len(state['removed'])}) but the index was not rebuilt; run ccc index in "
            "{project-root} or re-run /skf-setup without --ccc-skip-index"
        )

    return {
        "status": "ok",
        "version": "v2",
        "settings_yml_path": str(target),
        "settings_yml_existed": state["existed"],
        "ccc_init": state["ccc_init"],
        "settings_ready": state["ready"],
        "not_ready_reason": _payload_safe(reason) if reason else None,
        "patterns_added": len(state["added"]),
        "patterns_added_list": state["added"],
        "patterns_removed": len(state["removed"]),
        "patterns_removed_list": state["removed"],
        "patterns_already_present": state["present"],
        "effective_patterns": state["effective"],
        "written": state["written"],
        "gitignore_updated": _read_bytes_or_none(gitignore) != gitignore_before,
        "index_action": action,
        "warnings": [_payload_safe(w) for w in warnings],
    }


# ─── Clone mode ─────────────────────────────────────────────────────────────


def quote_bare_glob_items(text: str) -> tuple[str, int]:
    """Single-quote each bare `- *...` list item; return (text, items quoted).

    YAML reads a plain scalar that starts with `*` as an alias, so a
    `- **/build` item an earlier hand edit wrote stops ccc from loading the
    file. ccc writes these items quoted, as yaml.safe_dump does. A trailing
    comment stays a comment, after the closing quote.
    """
    return BARE_GLOB_ITEM_RE.subn(lambda m: f"{m.group(1)}'{m.group(2)}'{m.group(3)}", text)


def _load_clone_settings(path: Path, warnings: list[str]) -> tuple[dict, bool]:
    """Parse a clone's settings.yml: (data, repaired).

    A file YAML cannot read is read again with its bare glob items quoted,
    and `repaired` is then True so the caller writes it back. Raises
    HelperError(1) when it still cannot be read, is not a mapping, or holds
    an exclude_patterns or include_patterns that is neither a list nor null.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise HelperError(1, f"failed to read {path}: {e}")
    repaired = False
    try:
        data = yaml.safe_load(text)
    except (yaml.YAMLError, ValueError) as e:
        fixed, count = quote_bare_glob_items(text)
        try:
            data = yaml.safe_load(fixed) if count else None
        except (yaml.YAMLError, ValueError):
            count = 0
        if not count:
            raise HelperError(1, f"failed to parse {path}: {e}")
        repaired = True
        warnings.append(f"quoted {_plural(count, 'list item', 'list items')} of settings.yml that YAML "
                        "read as an alias, so ccc can load the file again")
    if data is None:
        return {}, repaired
    if not isinstance(data, dict):
        raise HelperError(1, f"expected mapping at top of {path}, got {type(data).__name__}")
    for key in ("exclude_patterns", "include_patterns"):
        value = data.get(key)
        if value is not None and not isinstance(value, list):
            raise HelperError(1, f"{key} in {path} is not a list (got {type(value).__name__})")
    return data, repaired


def include_covers(pattern, ext: str) -> bool:
    """True when an include_patterns entry matches a nested `*.<ext>` file as ccc reads it."""
    if not isinstance(pattern, str):
        return False
    probe = INCLUDE_PROBE.format(ext=ext)
    for alternative in _brace_alternatives(pattern):
        rx = _ccc_glob(alternative, CCC_BACKSLASH_IS_SLASH)
        if rx is not None and rx.fullmatch(probe):
            return True
    return False


# ─── Index build (--build-index) ────────────────────────────────────────────


def _run_ccc(root: Path, args: tuple[str, ...], timeout: int) -> tuple[bool, str]:
    """Run `ccc <args>` in root. Return (exit code was 0, stdout plus stderr).

    A ccc that cannot be found, started or finished in time returns False
    with the reason as its output.
    """
    exe = _resolve_outside_cwd("ccc")
    if exe is None:
        return False, "ccc was not found on PATH"
    try:
        result = subprocess.run(
            [exe, *args],
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env=_child_env(),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"ccc {args[0]} timed out after {timeout}s"
    except (OSError, ValueError) as e:
        return False, f"ccc {args[0]} could not start: {e}"
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    if result.returncode != 0:
        return False, f"ccc {args[0]} exited {result.returncode}: {' '.join(output.split())[:300]}"
    return True, output


def parse_status_file_count(output: str) -> int | None:
    """The `Files:` count of `ccc status`, or None when it shows none (no index yet)."""
    match = CCC_FILES_RE.search(output)
    return int(match.group(1)) if match else None


def _prior_index(prior_state_from) -> dict:
    """`ccc_index` of the prior forge-tier.yaml, {} when there is none to read."""
    if prior_state_from is None or not Path(prior_state_from).is_file():
        return {}
    try:
        data = yaml.safe_load(Path(prior_state_from).read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError):
        return {}
    ccc = data.get("ccc_index") if isinstance(data, dict) else None
    return ccc if isinstance(ccc, dict) else {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_index(root: Path, indexed_path: str, action: str, not_ready_reason,
                prior_state_from, warnings: list[str]) -> dict:
    """The index state a setup run ends with, after acting on `action`.

    See "Index build" in the module docstring. `warnings` gains a note when
    a pass is still running after the reruns.
    """
    unset = {"indexed_path": None, "last_indexed": None, "file_count": None, "failed_reason": None}
    if action == "skip":
        return {"status": "skipped", **unset}
    if action == "fail":
        return {"status": "failed", **unset,
                "failed_reason": not_ready_reason or "no usable .cocoindex_code/settings.yml"}
    if action == "keep":
        prior = _prior_index(prior_state_from)
        last = prior.get("last_indexed")
        count = prior.get("file_count")
        return {"status": "fresh", **unset, "indexed_path": indexed_path,
                "last_indexed": last.isoformat() if isinstance(last, datetime) else last,
                "file_count": count if isinstance(count, int) and not isinstance(count, bool) else None}

    def failed(reason: str) -> dict:
        return {"status": "failed", **unset, "failed_reason": _payload_safe(reason)}

    ok, output = _run_ccc(root, ("index",), CCC_INDEX_TIMEOUT_SEC)
    if not ok:
        return failed(output)
    reruns = 0
    while True:
        ok, status = _run_ccc(root, ("status",), CCC_STATUS_TIMEOUT_SEC)
        if not ok:
            return failed(status)
        if CCC_IN_PROGRESS not in status or reruns == CCC_INDEX_RERUNS:
            break
        reruns += 1
        ok, output = _run_ccc(root, ("index",), CCC_INDEX_TIMEOUT_SEC)
        if not ok:
            return failed(output)
    if CCC_IN_PROGRESS in status:
        warnings.append(f"ccc still reports an indexing pass in progress after {CCC_INDEX_RERUNS} reruns "
                        "of ccc index; the file count may grow")
    count = parse_status_file_count(status)
    if count is None:
        return failed("ccc index finished, but ccc status shows no index")
    if count == 0:
        return failed("ccc index finished, but ccc status counts no indexed file")
    return {"status": "created", **unset, "indexed_path": indexed_path, "last_indexed": _utc_now(),
            "file_count": count}


def read_config_folders(path: Path) -> tuple[str, str]:
    """The raw skills_output_folder and forge_data_folder values of config.yaml."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HelperError(1, f"--config does not exist: {path}")
    except (OSError, ValueError, yaml.YAMLError) as e:
        raise HelperError(1, f"--config cannot be read as YAML: {path}: {e}")
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise HelperError(1, f"--config is not a YAML mapping: {path}")
    values = (data.get("skills_output_folder"), data.get("forge_data_folder"))
    return tuple("" if v is None else str(v) for v in values)


def run_clone_merge(clone_root, include_exts=(), allow_ccc_init: bool = True) -> dict:
    """Clone mode: prepare a workspace clone's settings.yml and merge into it.

    Returns the clone-mode payload documented in the module docstring.
    Raises HelperError for the exit-1 and exit-2 cases.
    """
    root = Path(clone_root)
    target = root / SETTINGS_DIR / SETTINGS_NAME
    warnings: list[str] = []
    existed = target.is_file()
    ccc_init, ready, reason, written = "not_needed", True, None, False
    added: list[str] = []
    includes_added: list[str] = []
    covered: list[str] = []
    present = 0

    if not existed:
        if not allow_ccc_init:
            ready, reason = False, "settings.yml is missing and --no-ccc-init was given"
        else:
            _ok, output = run_ccc_init(root)
            if target.is_file():
                ccc_init, written = "created", True
            else:
                ccc_init, ready = "failed", False
                reason = ("ccc init did not create .cocoindex_code/settings.yml "
                          f"({_output_hint(output)})")

    if ready:
        data, repaired = _load_clone_settings(target, warnings)
        excludes = data.get("exclude_patterns")
        if isinstance(excludes, list):
            existing = [str(p) for p in excludes]
            added = [p for p in CLONE_EXCLUDES if p not in existing]
            present = len(CLONE_EXCLUDES) - len(added)
            if added:
                data["exclude_patterns"] = [*excludes, *added]
        else:
            warnings.append("settings.yml has no exclude_patterns list, so SKF added no exclusion: "
                            "a list written from scratch replaces the ccc default exclusions")
        includes = data.get("include_patterns")
        if include_exts and isinstance(includes, list):
            current = list(includes)
            for ext in dict.fromkeys(include_exts):
                if any(include_covers(p, ext) for p in current):
                    covered.append(ext)
                else:
                    current.append(f"**/*.{ext}")
                    includes_added.append(f"**/*.{ext}")
            if includes_added:
                data["include_patterns"] = current
        elif include_exts:
            warnings.append("settings.yml has no include_patterns list, so SKF added no file type: "
                            "a list written from scratch replaces the ccc default file types")
        if added or includes_added or repaired:
            # ASCII-only output (non-ASCII escaped), as ccc writes it.
            _atomic_write(target, yaml.safe_dump(data, default_flow_style=False, sort_keys=False),
                          unique=True)
            written = True

    return {
        "status": "ok",
        "version": "v2",
        "settings_yml_path": str(target),
        "settings_yml_existed": existed,
        "ccc_init": ccc_init,
        "settings_ready": ready,
        "not_ready_reason": _payload_safe(reason) if reason else None,
        "patterns_added": len(added),
        "patterns_added_list": added,
        "patterns_already_present": present,
        "includes_added_list": includes_added,
        "includes_covered_list": covered,
        "written": written,
        "warnings": [_payload_safe(w) for w in warnings],
    }


def _ext_arg(value: str) -> str:
    """argparse type for --include-ext: a plain file extension, a leading `.` dropped."""
    ext = str(value).strip()
    ext = ext[1:] if ext.startswith(".") else ext
    if not EXTENSION_RE.match(ext):
        raise argparse.ArgumentTypeError(f"expected a file extension such as ex or .ex, got {value}")
    return ext


def _bool_arg(value: str) -> bool:
    """argparse type for true|false (case-insensitive); anything else is a usage error."""
    normalized = str(value).strip().lower()
    if normalized in ("true", "false"):
        return normalized == "true"
    raise argparse.ArgumentTypeError(f"expected true or false, got {value}")


class _JsonErrorParser(argparse.ArgumentParser):
    """Report usage errors as the same sanitized stderr JSON as every other exit.

    A caller that reads stderr JSON may forward the message into a
    single-quoted payload; argparse's own text quotes the bad value.
    """

    def error(self, message: str) -> None:
        _die(2, f"usage error: {message}")


def main() -> None:
    parser = _JsonErrorParser(
        description="Prepare .cocoindex_code/settings.yml (running ccc init when needed), "
                    "reconcile the SKF exclusion patterns in it, and decide whether the "
                    "ccc index must be built.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    roots = parser.add_mutually_exclusive_group(required=True)
    roots.add_argument(
        "--project-root",
        help="Absolute path to the project root. The script reads and writes "
             "{project-root}/.cocoindex_code/settings.yml and runs ccc init there. "
             "--build-index records the value as given as the index's indexed_path.",
    )
    roots.add_argument(
        "--clone-root", type=Path,
        help="Clone mode: absolute path to an SKF workspace clone. The script runs ccc init -f "
             "there when .cocoindex_code/settings.yml is missing, and merges the standard build "
             "and dependency exclusions (and the --include-ext file types) into it.",
    )
    parser.add_argument(
        "--skills-output-folder", default=None,
        help="Raw value of skills_output_folder from {project-root}/_bmad/skf/config.yaml, "
             "forwarded verbatim. Normalized, validated and checked, then excluded as a "
             "root-anchored pattern, or entry by entry when the folder also holds content "
             "SKF did not generate. Refused values produce a warning.",
    )
    parser.add_argument(
        "--forge-data-folder", default=None,
        help="Raw value of forge_data_folder from {project-root}/_bmad/skf/config.yaml. "
             "Same handling as --skills-output-folder.",
    )
    parser.add_argument(
        "--config", type=Path, default=None,
        help="Setup mode, instead of the two folder flags: the _bmad/skf/config.yaml "
             "to read the raw skills_output_folder and forge_data_folder values from.",
    )
    parser.add_argument(
        "--prior-state-from", type=Path, default=None,
        help="Path to forge-tier.yaml. Its ccc_index.exclude_patterns is the record of "
             "the patterns SKF owns, per-entry patterns included; recorded patterns the "
             "current config no longer produces are removed, and with this record a "
             "folder already in exclude_patterns that it does not hold is left to the "
             "user. Missing file: empty record.",
    )
    parser.add_argument(
        "--index-fresh", type=_bool_arg, default=None, metavar="true|false",
        help="Whether the prior ccc index is still fresh. With true and an unchanged "
             "settings.yml, index_action is keep. Default false.",
    )
    parser.add_argument(
        "--skip-index", type=_bool_arg, default=None, metavar="true|false",
        help="Whether the setup run opted out of indexing (--ccc-skip-index). With true, "
             "a ready settings.yml gives index_action skip. Default false.",
    )
    parser.add_argument(
        "--no-ccc-init", action="store_true",
        help="Never run ccc init (tests and diagnostics). A missing settings.yml is "
             "reported as not ready; a rebuild is skipped with a warning.",
    )
    parser.add_argument(
        "--build-index", action="store_true",
        help="Setup mode: act on index_action (run ccc index when it is index) and add "
             "the index result, stamped by this script, to the output.",
    )
    parser.add_argument(
        "--result-to", type=Path, default=None,
        help="Also write the JSON result, or the JSON error of a run that fails, to this file.",
    )
    parser.add_argument(
        "--include-ext", type=_ext_arg, action="append", default=[], metavar="EXT",
        help="Clone mode only, repeatable: a file extension (ex, or .ex) whose files ccc must "
             "index. Unless an include_patterns entry already matches it, **/*.EXT is appended "
             "to include_patterns.",
    )
    args = parser.parse_args()

    def fail(code: int, message: str) -> None:
        if args.result_to is not None:
            _write_result(args.result_to, {"status": "error", "message": _payload_safe(message)})
        _die(code, message)

    def done(payload: dict) -> None:
        if args.result_to is not None:
            _write_result(args.result_to, payload)
        print(json.dumps(payload))

    if args.clone_root is not None:
        # A setup flag is refused whatever its value: `--skip-index false` or an empty folder too.
        setup_flags = [flag for flag, value in (
            ("--skills-output-folder", args.skills_output_folder),
            ("--forge-data-folder", args.forge_data_folder),
            ("--config", args.config),
            ("--prior-state-from", args.prior_state_from),
            ("--index-fresh", args.index_fresh),
            ("--skip-index", args.skip_index),
            ("--build-index", args.build_index or None),
        ) if value is not None]
        if setup_flags:
            _die(2, f"usage error: --clone-root takes no setup flag ({', '.join(setup_flags)})")
        if not args.clone_root.is_dir():
            fail(1, f"--clone-root is not a directory: {args.clone_root}")
        try:
            payload = run_clone_merge(args.clone_root, args.include_ext,
                                      allow_ccc_init=not args.no_ccc_init)
        except HelperError as e:
            fail(e.code, str(e))
        except Exception as e:  # noqa: BLE001 (every failure must stay stderr JSON)
            fail(2, f"unexpected error: {type(e).__name__}: {e}")
        done(payload)
        return
    if args.include_ext:
        _die(2, "usage error: --include-ext needs --clone-root")
    if args.config is not None and (args.skills_output_folder is not None or args.forge_data_folder is not None):
        _die(2, "usage error: --config replaces --skills-output-folder and --forge-data-folder")

    root = Path(args.project_root)
    if not root.is_dir():
        fail(1, f"--project-root is not a directory: {args.project_root}")
    try:
        skills_output_folder, forge_data_folder = (
            read_config_folders(args.config) if args.config is not None
            else (args.skills_output_folder or "", args.forge_data_folder or ""))
        payload = run_merge(
            root,
            skills_output_folder,
            forge_data_folder,
            prior_state_from=args.prior_state_from,
            index_fresh=bool(args.index_fresh),
            skip_index=bool(args.skip_index),
            allow_ccc_init=not args.no_ccc_init,
        )
        if args.build_index:
            if args.result_to is not None and payload["index_action"] == "index":
                # settings.yml is already rewritten, and `ccc index` can run for
                # an hour: a host that stops the call must still find this run's
                # exclusion record, with an index that did not finish.
                _write_result(args.result_to, {**payload, "index": {
                    "status": "failed", "indexed_path": None, "last_indexed": None,
                    "file_count": None, "failed_reason": INDEX_UNFINISHED}})
            warnings: list[str] = []
            payload["index"] = build_index(root, args.project_root, payload["index_action"],
                                           payload["not_ready_reason"], args.prior_state_from, warnings)
            payload["warnings"] += [_payload_safe(w) for w in warnings]
    except HelperError as e:
        fail(e.code, str(e))
    except Exception as e:  # noqa: BLE001 — every failure must stay stderr JSON
        fail(2, f"unexpected error: {type(e).__name__}: {e}")
    done(payload)


def _write_result(path: Path, value: dict) -> None:
    """Write --result-to; a file that cannot be written is one more stderr error."""
    try:
        _atomic_write(path, json.dumps(value) + "\n")
    except HelperError as e:
        print(json.dumps({"status": "error", "message": _payload_safe(str(e))}), file=sys.stderr)
        sys.exit(e.code)


if __name__ == "__main__":
    main()
