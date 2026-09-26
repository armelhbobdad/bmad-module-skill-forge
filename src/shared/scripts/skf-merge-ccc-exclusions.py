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
  3. leave out a folder that already holds files SKF did not generate;
  4. merge the SKF patterns and prune the SKF-owned patterns the current
     config no longer produces;
  5. warn when `/.cocoindex_code/` is not gitignored;
  6. return one `index_action` telling the step whether to run `ccc index`.

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

Flags:

  --project-root          required; the directory holding .cocoindex_code/
  --skills-output-folder  raw skills_output_folder config value, forwarded
                          verbatim (`{project-root}/...` is resolved here)
  --forge-data-folder     raw forge_data_folder config value, same handling
  --prior-state-from      forge-tier.yaml; its ccc_index.exclude_patterns is
                          the record of the patterns SKF owns
  --index-fresh           true|false (case-insensitive); the prior index is
                          still fresh, so an unchanged settings.yml keeps it
  --skip-index            true|false; the setup run opted out of indexing
  --no-ccc-init           never run ccc init (tests and diagnostics)

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
  - carrying `'`                     (breaks the setup shell payloads)

A refused value is left out; the four `**/` patterns still merge.

Collision rule: for each accepted folder that exists, the script lists
what ccc would see there — `git --literal-pathspecs ls-files -z --cached
--others --exclude-standard -- <folder>`, i.e. tracked files plus
untracked files git does not ignore — and groups the paths by first-level
entry. A group is SKF output when its name contains `.skf-`, or:

  skills  it is `_batch`, a key of `exports` in `.export-manifest.json`,
          it holds the versioned `<n>/<v>/<n>/` layout, an `active`
          pointer or a `*-result*.json`, or its `metadata.json` carries an
          SKF marker (generated_by, tool_versions.skf, or skill_type with
          forge_tier / confidence_tier)
  forge   it is `_campaign` or `improvement-queue`, holds a
          `skill-brief.yaml*` or `.brief-draft.json`, any `*-result*.json`,
          or a versioned provenance map, evidence report or extraction
          rules file

Root files named `*-result*.json`, `.export-manifest.json` (skills) or
with an SKF report prefix (forge) are SKF output; `.gitkeep`,
`.gitignore`, `.gitattributes` and README files are neutral. The folder
is a collision when any group is foreign, or when it holds other root
files and no SKF output at all — loose notes beside real SKF output are
tolerated. A group that is, or contains, the other configured SKF folder
is SKF output; when both settings name the same folder, an entry either
kind accepts is SKF output. A submodule or nested repository is
classified too: when the folder itself is one, its own files are listed
from inside it, and one deeper down is a group of its own. A colliding
folder is left out of the produced patterns with a warning naming the
setting to change. The check is skipped silently when git is missing, the
project is not a git repository, the folder does not exist, or an
always-included `**/` pattern already covers the folder; it is skipped
with a warning when git times out or fails in any other way (for example
a repository git refuses as unsafe). Every git and ccc child runs with
the git location variables (GIT_DIR, GIT_INDEX_FILE, ...) removed from
its environment, so a git hook's index never leaks into the check; git
also runs with LC_ALL=C so its messages are recognised in any locale.

Ownership record and pruning: `ccc_index.exclude_patterns` in the
forge-tier.yaml passed through --prior-state-from is the set of patterns
SKF owned after its last reconcile. A recorded pattern the current run
does not produce is removed from settings.yml; entries SKF never recorded
— user entries and the ccc defaults — are never removed, and the four
`**/` patterns are always produced so are never pruned. When forge-tier.yaml
exists but its record names no folder pattern (empty, or only the four
`**/` patterns), the legacy `**/{value}` forms of the accepted folder
values also count as owned, so installs migrate to the anchored forms; a
`**/skills` added by the user after a folder pattern is recorded
survives, and with no forge-tier.yaml at all SKF owns nothing yet. When a
folder value is refused, pruning is blocked for the whole run and the
recorded patterns that would have been removed stay (warning): a config
typo must not silently un-exclude real output. If that run also used the
legacy fallback, effective_patterns is null so the record stays
folder-free and the next valid run can still migrate.

Index decision: "fail" when no settings.yml exists; otherwise "skip"
under --skip-index true (with a warning when settings.yml changed);
otherwise, after a failed rebuild, "keep" when the prior index is fresh
and "fail" when it is not; otherwise "index" when settings.yml changed or
the prior index is not fresh; otherwise "keep".

After a reconcile, `/.cocoindex_code/` coverage is checked with
`git check-ignore -q --no-index -- .cocoindex_code/target_sqlite.db`; an
uncovered path adds a warning. `gitignore_updated` compares the
`.gitignore` bytes before and after the run (only ccc init writes it).

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
                                         record; null when nothing was
                                         reconciled, or a legacy-record run
                                         with a refused value (keep the
                                         old record)
    "written":                   bool,   settings.yml changed this run
                                         (ccc init create, rebuild, or
                                         SKF edit)
    "gitignore_updated":         bool,
    "index_action":              "index" | "keep" | "skip" | "fail",
    "warnings":                  [str]
  }

No human-readable string this script emits contains a single quote:
every warning, `not_ready_reason` and error message has `'` replaced by
a backtick, and folder values containing `'` are refused, because the
setup steps embed these strings in single-quoted `echo '...'` payloads.
Data fields such as `settings_yml_path` are emitted as they are.

Writes to settings.yml use temp + fsync + rename (mirrors
skf-atomic-write.py), emit ASCII-only YAML (non-ASCII escaped, as ccc
writes it — ccc reads the file with the platform default encoding), and
drop YAML comments; ccc ignores them and keeps unknown top-level keys,
which are preserved. Concurrent writers must
coordinate via external `flock` (the typical pattern for shared-file
mutation in this module).

Exit codes:
  0 success, including "not ready" (warnings stay on the success path)
  1 --project-root is not a directory; settings.yml cannot be parsed, is
    not a mapping, or has an exclude_patterns that is neither a list nor
    null (JSON error on stderr)
  2 usage error (including a non-boolean --index-fresh / --skip-index),
    a write, move-aside or restore failure, or any unexpected internal
    error (always JSON on stderr, never a traceback)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

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
GIT_TIMEOUT_SEC = 10
SAMPLE_SIZE = 3
INDEX_ACTIONS = ("index", "keep", "skip", "fail")
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
RESULT_JSON_RE = re.compile(r"^[a-z0-9][a-z0-9-]*-result(-latest|-\d[^/]*)?\.json$")
README_RE = re.compile(r"^readme(\..+)?$", re.IGNORECASE)
NEUTRAL_ROOT_FILES = frozenset({".gitkeep", ".gitignore", ".gitattributes"})
SKF_GENERATORS = frozenset({"quick-skill", "create-skill", "create-stack-skill"})
FORGE_ROOT_PREFIXES = (
    "analyze-source-",
    "feasibility-report-",
    "verify-stack-result-",
    "ra-state-",
    "refine-architecture-result-",
    "refined-architecture-",
)
FORGE_GROUP_DIRS = frozenset({"_campaign", "improvement-queue"})
FORGE_VERSION_ANCHORS = frozenset({"provenance-map.json", "evidence-report.md", "extraction-rules.yaml"})
FOLDER_KEYS = (("skills_output_folder", "skills"), ("forge_data_folder", "forge"))

SETTINGS_DIR = ".cocoindex_code"
SETTINGS_NAME = "settings.yml"
BACKUP_NAME = "settings.yml.skf-repair"
FIX_HINT = "fix the value in {project-root}/_bmad/skf/config.yaml"


class HelperError(Exception):
    """A handled failure that ends the run with a JSON error and exit `code`."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _no_squote(text) -> str:
    """Replace `'` with a backtick — setup embeds these strings in `echo '...'`."""
    return str(text).replace("'", "`")


def _die(code: int, message: str) -> None:
    print(json.dumps({"status": "error", "message": _no_squote(message)}), file=sys.stderr)
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
    sibling guards in skf-detect-tools.py and
    skf-qmd-classify-collections.py.
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


def _atomic_write(target: Path, content: str) -> None:
    """Crash-safe write via temp + fsync + rename. Mirrors skf-atomic-write.py.

    Raises HelperError(2) on any OS failure; the temp file is removed.
    """
    tmp = target.with_name(target.name + ".skf-tmp")
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
            f"the raw config value and let this script resolve {{project-root}}"
        )

    if "'" in value:
        return None, (
            f"{key} contains a single quote, which breaks the setup payloads; "
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


# ─── Collision check ────────────────────────────────────────────────────────


_LS_FILES_ARGS = ("ls-files", "-z", "--cached", "--others", "--exclude-standard")


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
    return [r.decode("utf-8", errors="replace") for r in stdout.split(b"\0") if r], None


def list_folder_paths(root: Path, folder: str) -> tuple[list[tuple[str, ...]] | None, str | None]:
    """Return (paths relative to folder, problem).

    Lists tracked files plus untracked files git does not ignore — what
    ccc would index. A missing folder gives ([], None). None paths mean the
    check is skipped; problem (see _ls_files) says whether that deserves a
    warning. When git reports the folder itself as one entry — a submodule
    or a nested repository, which ccc indexes like any other folder — its
    own files are listed from inside it. A nested repository deeper down
    comes back as a single directory entry, which the classifier treats as
    a group.
    """
    if not (root / folder).is_dir():
        return [], None
    records, problem = _ls_files(root, folder)
    if records is None:
        return None, problem
    depth = len(PurePosixPath(folder).parts)
    if any(len(PurePosixPath(r).parts) <= depth for r in records):
        records, problem = _ls_files(root / folder)
        if records is None:
            return None, problem
        depth = 0
    found: set[tuple[str, ...]] = set()
    for record in records:
        parts = PurePosixPath(record).parts[depth:]
        if parts:
            found.add(parts)
    return sorted(found), None


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


def _manifest_exports(base: Path) -> set[str]:
    """Skill names under `exports` in base/.export-manifest.json (empty on any error)."""
    try:
        manifest = json.loads((base / ".export-manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    exports = manifest.get("exports") if isinstance(manifest, dict) else None
    return {str(k) for k in exports} if isinstance(exports, dict) else set()


def _skf_group(base: Path, kind: str, group: str, members: list[tuple[str, ...]],
               manifest: set[str]) -> bool:
    """True when first-level entry `group` under the folder is SKF output of `kind`."""
    if ".skf-" in group:
        return True
    if kind == "skills":
        return (
            group == "_batch"
            or group in manifest
            or any(len(m) >= 4 and m[2] == group for m in members)
            or any(len(m) == 2 and (m[1] == "active" or m[1].startswith("active.skf-")
                                    or RESULT_JSON_RE.match(m[1]))
                   for m in members)
            or _has_skf_metadata(base / group / "metadata.json")
        )
    return (
        group in FORGE_GROUP_DIRS
        or any(len(m) == 2 and (m[1].startswith("skill-brief.yaml") or m[1] == ".brief-draft.json")
               for m in members)
        or any(RESULT_JSON_RE.match(m[-1]) for m in members)
        or any(len(m) >= 3 and m[-1] in FORGE_VERSION_ANCHORS for m in members)
    )


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


def find_foreign_entries(root: Path, folder: str, kind, paths, other_folders=()) -> list[str]:
    """Return the entries SKF did not generate; [] means no collision.

    `kind` is "skills" or "forge", or a collection of both when the two
    folder values are the same folder; an entry is SKF output when any of
    the kinds accepts it. `paths` comes from list_folder_paths. A group
    that is, or contains, another configured SKF folder (`other_folders`)
    is SKF output too. A single-segment entry that is a directory on disk
    (a nested repository or submodule) is a group, not a root file.
    Verdict per first-level entry: any foreign group makes a collision
    (foreign groups, as `name/`, then the other root files); otherwise
    other root files are a collision only when the folder holds no SKF
    output at all. Neutral root files never count.
    """
    kinds = {kind} if isinstance(kind, str) else set(kind)
    base = root / folder
    manifest = _manifest_exports(base) if "skills" in kinds else set()
    groups: dict[str, list[tuple[str, ...]]] = {}
    other_root: list[str] = []
    owned = 0
    for rel in paths:
        if len(rel) == 1 and not (base / rel[0]).is_dir():
            name = rel[0]
            if any(_skf_root_file(k, name) for k in kinds):
                owned += 1
            elif name not in NEUTRAL_ROOT_FILES and not README_RE.match(name):
                other_root.append(name)
            continue
        members = groups.setdefault(rel[0], [])
        if len(rel) > 1:
            members.append(rel)
    foreign_groups: list[str] = []
    for group, members in sorted(groups.items()):
        if (_holds_other_folder(folder, group, other_folders)
                or any(_skf_group(base, k, group, members, manifest) for k in kinds)):
            owned += 1
        else:
            foreign_groups.append(group + "/")
    if foreign_groups:
        return foreign_groups + other_root
    if other_root and owned == 0:
        return other_root
    return []


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


def _collision_warning(key: str, value: str, foreign: list[str]) -> str:
    sample = ", ".join(foreign[:SAMPLE_SIZE])
    return (
        f"{key} {value} already holds {_plural(len(foreign), 'entry', 'entries')} SKF did "
        f"not generate (for example {sample}), so SKF left it out of the ccc exclusions "
        f"and that content stays indexed. SKF also writes its output there: set {key} in "
        f"{{project-root}}/_bmad/skf/config.yaml to a folder only SKF uses and re-run "
        f"/skf-setup. To exclude it anyway, add {value} to exclude_patterns in "
        f".cocoindex_code/settings.yml yourself; SKF never removes entries it did not add"
    )


def _reconcile(root: Path, target: Path, backup: Path, data: dict,
               values: dict[str, tuple[str, str]], owned_prior: set[str], prune_allowed: bool,
               state: dict, warnings: list[str]) -> None:
    """Collision check, merge and prune; write settings.yml when it changed."""
    existing = [str(p) for p in (data.get("exclude_patterns") or [])]
    produced = list(ALWAYS_INCLUDE)
    by_value: dict[str, list[tuple[str, str]]] = {}
    for key, (value, kind) in values.items():
        by_value.setdefault(value, []).append((key, kind))
    for value, entries in by_value.items():
        keys = " and ".join(key for key, _kind in entries)
        if not _inside_always_excluded(value):
            paths, problem = list_folder_paths(root, value)
            if problem:
                warnings.append(f"{problem} for {keys}; collision check skipped")
            others = [v for v in by_value if v != value]
            foreign = (find_foreign_entries(root, value, {kind for _key, kind in entries},
                                            paths, others)
                       if paths else [])
            if foreign:
                warnings.append(_collision_warning(keys, value, foreign))
                continue
        if value not in produced:
            produced.append(value)

    merged, added, removed = plan_exclusions(existing, produced, owned_prior, prune_allowed)
    blocked = [] if prune_allowed else sorted((owned_prior - set(produced)) & set(existing))
    if blocked:
        warnings.append(
            "kept previously recorded SKF exclusions (" + ", ".join(blocked) + ") because a "
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
    # Legacy fallback: a forge-tier.yaml whose record names no folder pattern
    # (empty, or only the always-included ones) predates the anchored forms,
    # so the `**/<value>` forms count as owned. With no forge-tier.yaml at
    # all, SKF never finished a setup here and owns nothing yet.
    prior_exists = prior_state_from is not None and Path(prior_state_from).is_file()
    legacy = prior_exists and not (set(record) - set(ALWAYS_INCLUDE))
    owned_prior = set(record)
    if legacy:
        owned_prior |= {f"**/{value}" for value, _kind in values.values()}

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
    }

    data = _prepare_settings(root, target, backup, allow_ccc_init, state, warnings)
    if data is not None:
        _reconcile(root, target, backup, data, values, owned_prior, prune_allowed,
                   state, warnings)
        if legacy and not prune_allowed:
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
        "not_ready_reason": _no_squote(reason) if reason else None,
        "patterns_added": len(state["added"]),
        "patterns_added_list": state["added"],
        "patterns_removed": len(state["removed"]),
        "patterns_removed_list": state["removed"],
        "patterns_already_present": state["present"],
        "effective_patterns": state["effective"],
        "written": state["written"],
        "gitignore_updated": _read_bytes_or_none(gitignore) != gitignore_before,
        "index_action": action,
        "warnings": [_no_squote(w) for w in warnings],
    }


def _bool_arg(value: str) -> bool:
    """argparse type for true|false (case-insensitive); anything else is a usage error."""
    normalized = str(value).strip().lower()
    if normalized in ("true", "false"):
        return normalized == "true"
    raise argparse.ArgumentTypeError(f"expected true or false, got {value}")


class _JsonErrorParser(argparse.ArgumentParser):
    """Report usage errors as the same sanitized stderr JSON as every other exit.

    The step's non-zero-exit branch parses stderr JSON and forwards the message
    into a single-quoted payload; argparse's own text quotes the bad value.
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
    parser.add_argument(
        "--project-root", type=Path, required=True,
        help="Absolute path to the project root. The script reads and writes "
             "{project-root}/.cocoindex_code/settings.yml and runs ccc init there.",
    )
    parser.add_argument(
        "--skills-output-folder", default="",
        help="Raw value of skills_output_folder from {project-root}/_bmad/skf/config.yaml, "
             "forwarded verbatim. Normalized, validated and collision-checked, then "
             "excluded as a root-anchored pattern. Refused values produce a warning.",
    )
    parser.add_argument(
        "--forge-data-folder", default="",
        help="Raw value of forge_data_folder from {project-root}/_bmad/skf/config.yaml. "
             "Same handling as --skills-output-folder.",
    )
    parser.add_argument(
        "--prior-state-from", type=Path, default=None,
        help="Path to forge-tier.yaml. Its ccc_index.exclude_patterns is the record of "
             "the patterns SKF owns; recorded patterns the current config no longer "
             "produces are removed. Missing file: empty record.",
    )
    parser.add_argument(
        "--index-fresh", type=_bool_arg, default=False, metavar="true|false",
        help="Whether the prior ccc index is still fresh. With true and an unchanged "
             "settings.yml, index_action is keep. Default false.",
    )
    parser.add_argument(
        "--skip-index", type=_bool_arg, default=False, metavar="true|false",
        help="Whether the setup run opted out of indexing (--ccc-skip-index). With true, "
             "a ready settings.yml gives index_action skip. Default false.",
    )
    parser.add_argument(
        "--no-ccc-init", action="store_true",
        help="Never run ccc init (tests and diagnostics). A missing settings.yml is "
             "reported as not ready; a rebuild is skipped with a warning.",
    )
    args = parser.parse_args()

    if not args.project_root.is_dir():
        _die(1, f"--project-root is not a directory: {args.project_root}")
    try:
        payload = run_merge(
            args.project_root,
            args.skills_output_folder,
            args.forge_data_folder,
            prior_state_from=args.prior_state_from,
            index_fresh=args.index_fresh,
            skip_index=args.skip_index,
            allow_ccc_init=not args.no_ccc_init,
        )
    except HelperError as e:
        _die(e.code, str(e))
    except Exception as e:  # noqa: BLE001 — every failure must stay stderr JSON
        _die(2, f"unexpected error: {type(e).__name__}: {e}")
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
