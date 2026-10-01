# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""SKF GitHub Fetch: stage files of a GitHub repository at one ref in a folder.

quick-skill reads a repository it never clones: its README, its manifest,
its entry-point files, and a skills module's SKILL.md files and
module-help.csv. This helper writes each file byte for byte under --dest,
laid out as in the repository, so the helper that reads it next
(skf-extract-public-api.py --manifest-file and --entry-file,
skf-skills-module.py extract) gets the file itself: no file text passes
through the model, a shell string or a rendered web page, and a quote or an
apostrophe in it arrives as written.

CLI:
  uv run skf-github-fetch.py --repo <repo> --ref <ref> --tree-file <file> \\
      --dest <folder> [--limit <n>] [--exclude <glob>]... \\
      [--patterns-file <file>] [--timeout <seconds>] [<pattern>...]

--repo takes a github.com repository as skf-github-probe.py does
(`owner/repo` or a URL). --ref takes a branch, tag or commit; an empty,
`null`, `none` or `head` value (any letter case) is HEAD, the default
branch.

Which files. --tree-file is the repository's file listing at --ref:
skf-github-probe.py tree output, or any listing skf-detect-language.py's
--tree-file reads (a listing that reports a failure is refused). Each
pattern is a repo-relative path or a glob, read by
skf-resolve-authoritative-files.py's rules: `**` spans any number of path
segments, none included, and `*` and `?` stay inside one. A pattern takes
the listed files it matches, in path order, at most --limit of them (0,
the default, for all), leaving out the files an --exclude glob matches. A
pattern that matches no listed file is reported in `unmatched` and costs
no request: an optional file the repository does not have (one more
entry-point candidate, a module-help.csv) is a normal answer, not an
error. A listing GitHub cut short (`truncated`) may lack a file the
repository has, so on one a pattern with no `*` or `?` that matches no
listed file is read anyway, one request: it is `fetched` when it is read,
and stays in `unmatched` when it cannot be. --patterns-file adds one
pattern per line (blank lines skipped), such as the list
skf-skills-module.py sniff writes with --fetch-list. A file two patterns
match is fetched once.

How. Each file is read from
https://raw.githubusercontent.com/<owner>/<repo>/<ref>/<path> without
credentials, which needs neither gh nor the API's rate limit. When that
fails (a private repository answers 404 there too), `gh api -H "Accept:
application/vnd.github.raw" repos/<owner>/<repo>/contents/<path>?ref=<ref>`
reads it with the user's GitHub login; once gh has read a file the raw URL
could not, the files left go to gh first. gh runs as skf-github-probe.py
runs it (through skf-source-tree.py's runner, never a gh in the current
folder). A path the listing holds that leads outside --dest (an absolute
path, a `..` segment) is never written.

The whole call finishes within about --timeout seconds (120 by default);
one request gets at most 20 of them.

Output (one ASCII JSON line on stdout):
  status     "ok": every file a pattern matched was written (no pattern
             matching anything is ok too); "partial": some could not be;
             "unavailable": none could be
  message    one line naming what failed, else null
  repo       "owner/repo"
  ref        the ref read ("HEAD" for the default branch)
  dest       the folder written to, absolute, with `/`
  via        "raw" | "gh" | "raw+gh" | null: what read the files written
  fetched    the repo-relative paths written under --dest, in pattern order
  unmatched  the patterns that matched no listed file (and, on a
             truncated listing, a path that could not be read either)
  failed     [{"path", "detail"}]: files that could not be read or written
  truncated  the listing was cut short, so a glob may miss a file

Exit codes:
  0  status ok
  3  status partial or unavailable (JSON on stdout; the caller decides)
  1  unexpected error: {"status": "error", "message": ...} on stderr
  2  usage error: argparse, an invalid --repo or --ref, or a --tree-file
     or --patterns-file that cannot be read ({"status": "error", ...} on
     stderr)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAW_ROOT = "https://raw.githubusercontent.com"
DEFAULT_TIMEOUT_SEC = 120.0
REQUEST_TIMEOUT_SEC = 20.0

_SIBLINGS: dict[str, object] = {}


def _load(filename: str):
    """A script of this folder, loaded once."""
    if filename not in _SIBLINGS:
        path = Path(__file__).resolve().parent / filename
        spec = importlib.util.spec_from_file_location(filename[:-3].replace("-", "_"), path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SIBLINGS[filename] = module
    return _SIBLINGS[filename]


def _probe():
    """skf-github-probe.py: its repository grammar, ref rule, user agent and gh error reading."""
    return _load("skf-github-probe.py")


class UsageError(ValueError):
    """An input the call cannot run with: exit 2."""


# --------------------------------------------------------------------------
# Which files
# --------------------------------------------------------------------------


def select(listing: list[str], patterns: list[str], limit: int = 0,
           excludes: list[str] | None = None, truncated: bool = False) -> tuple[list[str], list[str]]:
    """(the listed paths the patterns take, in pattern order and each once;
    the patterns that matched no listed file). On a truncated listing a
    pattern with no `*` or `?` that matched nothing is in both: the
    repository may hold it all the same."""
    glob_match = _load("skf-resolve-authoritative-files.py").glob_match
    excludes = excludes or []
    files = sorted(p for p in dict.fromkeys(listing) if not any(glob_match(p, x) for x in excludes))
    chosen: list[str] = []
    unmatched: list[str] = []
    for pattern in patterns:
        pattern = pattern.strip().removeprefix("./")
        matched = [p for p in files if glob_match(p, pattern)]
        if limit > 0:
            matched = matched[:limit]
        if not matched:
            unmatched.append(pattern)
            if truncated and pattern and not any(c in pattern for c in "*?") \
                    and not any(glob_match(pattern, x) for x in excludes):
                matched = [pattern]
        chosen.extend(p for p in matched if p not in chosen)
    return chosen, unmatched


def _target(dest: Path, path: str) -> Path | None:
    """Where `path` is written under `dest`, or None when it would land outside it."""
    parts = path.split("/")
    if path.startswith("/") or "\\" in path or any(part in ("", ".", "..") for part in parts):
        return None
    target = dest.joinpath(*parts)
    try:
        target.resolve().relative_to(dest.resolve())
    except ValueError:
        return None
    return target


# --------------------------------------------------------------------------
# Reading a file
# --------------------------------------------------------------------------


_deadline: float | None = None


def _start_clock(seconds: float | None) -> None:
    global _deadline
    _deadline = None if seconds is None else time.monotonic() + max(0.0, seconds)


def _budget() -> float | None:
    """Seconds the next request may take, or None when no time is left."""
    if _deadline is None:
        return REQUEST_TIMEOUT_SEC
    left = _deadline - time.monotonic()
    return min(REQUEST_TIMEOUT_SEC, left) if left > 0.5 else None


def _raw(owner: str, repo: str, ref: str, path: str) -> tuple[bytes | None, str]:
    """The file from raw.githubusercontent.com, without credentials: (bytes or None, detail)."""
    timeout = _budget()
    if timeout is None:
        return None, "no time was left to read it"
    url = f"{RAW_ROOT}/{owner}/{repo}/{urllib.parse.quote(ref, safe='/')}/{urllib.parse.quote(path, safe='/')}"
    req = urllib.request.Request(url, headers={"User-Agent": _probe().USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(), ""
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code} from {RAW_ROOT}"
    except (TimeoutError, socket.timeout):
        return None, f"{RAW_ROOT} did not answer within {timeout:g} seconds"
    except (urllib.error.URLError, OSError, ValueError) as e:
        return None, f"{RAW_ROOT}: {getattr(e, 'reason', e)}"


def _gh_raw(owner: str, repo: str, ref: str, path: str) -> tuple[bytes | None, str]:
    """The file through `gh api` with the raw media type: (bytes or None, detail)."""
    tree = _probe()._sibling()
    exe = tree._resolve_outside_cwd("gh")
    if exe is None:
        return None, "gh is not installed"
    timeout = _budget()
    if timeout is None:
        return None, "no time was left to run gh"
    api_path = (f"repos/{owner}/{repo}/contents/{urllib.parse.quote(path, safe='/')}"
                f"?ref={urllib.parse.quote(ref, safe='')}")
    try:
        rc, out, err, _killed = tree._run([exe, "api", "--hostname", "github.com", "-H",
                                           "Accept: application/vnd.github.raw", api_path], timeout)
    except (OSError, ValueError) as e:
        return None, f"gh could not run: {e}"
    if rc is None:
        return None, f"gh did not answer within {timeout:g} seconds"
    if rc == 0:
        return out, ""
    if rc == 4:
        return None, "gh is not logged in"
    return None, _probe()._last_line(err.decode("utf-8", errors="replace")) or f"gh exited {rc}"


def fetch(owner: str, repo: str, ref: str, paths: list[str], dest: Path) -> dict:
    """Write each path under dest; the output's fetched, failed and via keys."""
    fetched: list[str] = []
    failed: list[dict] = []
    used: list[str] = []
    gh_first = False
    for path in paths:
        target = _target(dest, path)
        if target is None:
            failed.append({"path": path, "detail": "the path leads outside the destination folder"})
            continue
        readers = (("gh", _gh_raw), ("raw", _raw)) if gh_first else (("raw", _raw), ("gh", _gh_raw))
        body, details, reader = None, [], None
        for name, read in readers:
            body, detail = read(owner, repo, ref, path)
            if body is not None:
                reader = name
                break
            details.append(f"{name}: {detail}")
        if body is None:
            failed.append({"path": path, "detail": "; ".join(details)})
            continue
        if reader == "gh" and not gh_first:
            gh_first = True
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        except OSError as e:
            failed.append({"path": path, "detail": f"cannot write {target.as_posix()}: {e.strerror or e}"})
            continue
        fetched.append(path)
        if reader not in used:
            used.append(reader)
    via = "+".join(name for name in ("raw", "gh") if name in used) or None
    return {"fetched": fetched, "failed": failed, "via": via}


def run(repo_arg: str, ref_arg: str | None, tree_file: str, dest_arg: str, patterns: list[str],
        limit: int = 0, excludes: list[str] | None = None) -> dict:
    probe = _probe()
    parsed = probe.parse_repo(repo_arg)
    if parsed is None:
        raise UsageError(f"{repo_arg} is not a github.com repository (expected owner/repo or a URL).")
    owner, repo = parsed
    ref = probe._tree_ref(ref_arg)
    if ref != "HEAD" and not probe._sibling().REF_RE.fullmatch(ref):
        raise UsageError(f"{ref} is not a valid branch, tag or commit name.")
    try:
        listing, truncated = _load("skf-detect-language.py").read_tree_file(tree_file)
    except ValueError as e:
        raise UsageError(str(e)) from e
    dest = Path(dest_arg).absolute()
    chosen, unmatched = select(listing, patterns, limit, excludes, truncated)
    result = fetch(owner, repo, ref, chosen, dest)
    # A path the truncated listing lacks was a guess: read, it matched; unread, it stays unmatched.
    guessed = {p for p in chosen if p in unmatched}
    unmatched = [p for p in unmatched if p not in result["fetched"]]
    failed = [f for f in result["failed"] if f["path"] not in guessed]
    if not failed:
        status, message = "ok", None
    else:
        status = "partial" if result["fetched"] else "unavailable"
        names = ", ".join(f["path"] for f in failed[:3]) + (f" and {len(failed) - 3} more" if len(failed) > 3 else "")
        message = (f"Could not fetch {names} from {owner}/{repo} at {ref}: {failed[0]['detail']}. "
                   "Check the network, or log in with gh auth login for a private repository.")
    return {"status": status, "message": message, "repo": f"{owner}/{repo}", "ref": ref,
            "dest": dest.as_posix(), "via": result["via"], "fetched": result["fetched"],
            "unmatched": unmatched, "failed": failed, "truncated": truncated}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _patterns_file(value: str) -> list[str]:
    try:
        with open(value, encoding="utf-8-sig") as fh:
            return [line.strip() for line in fh if line.strip()]
    except (OSError, UnicodeDecodeError) as e:
        raise UsageError(f"cannot read --patterns-file {value}: {getattr(e, 'strerror', None) or e}") from e


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-github-fetch",
        description="Write files of a GitHub repository at one ref under a folder, picked from its file listing.",
    )
    parser.add_argument("patterns", nargs="*", metavar="pattern", help="a repo-relative path or glob")
    parser.add_argument("--repo", required=True, help="owner/repo or a github.com URL")
    parser.add_argument("--ref", default="HEAD", help="branch, tag or commit (default: the default branch)")
    parser.add_argument("--tree-file", required=True,
                        help="the repository's file listing at --ref (skf-github-probe.py tree output)")
    parser.add_argument("--dest", required=True, help="the folder the files are written under")
    parser.add_argument("--limit", type=int, default=0, help="files one pattern takes at most (0: all)")
    parser.add_argument("--exclude", action="append", default=[], help="a glob of listed files to leave out")
    parser.add_argument("--patterns-file", help="more patterns, one per line")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SEC,
                        help="seconds the whole call may take (default 120)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        _start_clock(args.timeout)
        patterns = list(args.patterns)
        if args.patterns_file:
            patterns.extend(_patterns_file(args.patterns_file))
        out = run(args.repo, args.ref, args.tree_file, args.dest, patterns, args.limit, args.exclude)
    except UsageError as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 - one JSON error line, never a traceback
        print(json.dumps({"status": "error", "message": f"{type(e).__name__}: {e}"}), file=sys.stderr)
        return 1
    print(json.dumps(out))
    return 0 if out["status"] == "ok" else 3


def _force_utf8(*streams) -> None:
    """Reconfigure the JSON streams to UTF-8 (a Windows console uses cp1252)."""
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


if __name__ == "__main__":
    _force_utf8(sys.stdout, sys.stderr)
    sys.exit(main())
