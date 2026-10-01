# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Fetch Temporal: a GitHub repository's issues, pull requests, release
notes and changelog, written as create-skill's temporal feeder.

create-skill step 3b (references/sub/fetch-temporal.md) keeps what it fetched
from GitHub in the skill's `.skf-temporal/` folder under forge_data_folder:
step 4 searches it through a QMD collection, and step 5c's doc-rot scan reads
it. The same upstream data must give the same files on every run, so this
helper owns the fetches, the release loop and the markdown each file holds.
The step keeps the eligibility checks and what it tells the user.

CLI:
  uv run skf-fetch-temporal.py repo --source-repo <repo or local path>
  uv run skf-fetch-temporal.py fetch --repo <owner/repo> --feeder <folder> \\
      [--exports <file>] [--timeout <seconds>]

repo
----
Which GitHub repository a brief's source_repo names: an https, ssh or git
URL, `git@github.com:owner/repo` or the `owner/repo` shorthand, read by
skf-source-tree.py's parse_remote (the sibling in this folder), or a local
path whose git repository has a GitHub `origin` remote. When it names one,
the helper also asks whether gh is installed and logged in (`gh auth
status`, 10 seconds at most).

  {
    "repo": "owner/repo" | null,
    "via": "url" | "origin" | null,
    "gh": "ok" | "missing" | "unauthenticated" | "failed" | "not-run",
    "skip_reason": null | "not-github" | "not-a-git-repo" | "no-origin"
                   | "gh-missing" | "gh-unauthenticated" | "gh-failed"
  }

skip_reason is null when the repository can be fetched: a GitHub
repository, and a gh that answers.

fetch
-----
Fetches into a fresh folder beside the feeder, `<feeder>.new` (one an
interrupted fetch left behind is removed first), which holds a `.gitignore`
of `*` so the feeder keeps itself out of git:

  issues.md          the last ISSUE_LIMIT issues, open and closed
                     (`gh issue list`)
  prs.md             the last PR_LIMIT merged pull requests (`gh pr list`)
  releases.md        the notes of the last RELEASE_LIMIT releases, one
                     `gh release view` per tag, run one after another; a
                     tag whose fetch fails gets a one-line placeholder, and
                     a rate limit stops the loop with the releases so far
  changelog.md       CHANGELOG.md, else RELEASES.md, at the repository
                     root, in any letter case
  targeted-issues.md up to ISSUE_SEARCH_LIMIT issues for each of the first
                     TARGETED_NAMES --exports names (`gh search issues`,
                     SEARCH_WORKERS at a time); a name keeps only
                     [A-Za-z0-9_], and one with nothing left is skipped

The four list fetches run at the same time, then the release loop, then
the searches. A file is written only when its fetch returned something: a
placeholder is not, so releases.md needs the notes of one release at
least, and targeted-issues.md an issue one search found. When at least one
file was written, the fetch folder replaces the feeder; otherwise it is
removed and the feeder, if any, stays as the last good fetch left it.
--feeder must be a folder named `.skf-temporal`: the helper deletes it and
`.skf-temporal.new` beside it, and nothing else.

Each file but changelog.md (the file as the repository holds it) is
markdown with one `##` section per item, items in a fixed order (issues
and pull requests by number, newest first; releases as GitHub lists them;
search names by name), with no timestamp of the run: the same upstream data
gives byte-identical files. Bodies keep their text, with line endings made
`\\n`.

--exports names the extraction inventory's top_exports: a JSON list of
names, or an object with a `top_exports` list, in a file or on stdin (`-`).
Without it, or with an empty list, no search runs and no
targeted-issues.md is written. --timeout caps each gh call (default
DEFAULT_TIMEOUT_SEC seconds).

  {
    "status": "replaced" | "kept",
    "repo": "owner/repo",
    "feeder": "<folder>",
    "files": ["<name>.md", ...],     # the feeder's .md files after the run
    "fetches": {
      "issues":    {"status": "ok" | "empty" | "failed", "count": N,
                    "detail": null | "..."},
      "prs":       {...same...},
      "releases":  {"status": "ok" | "empty" | "failed" | "stopped",
                    "count": N, "fetched": N, "failed": N,
                    "stopped_at": null | N, "detail": null | "..."},
      "changelog": {"status": "ok" | "none" | "failed",
                    "file": "<name>" | null, "detail": null | "..."},
      "targeted":  {"status": "ok" | "none" | "unsupported" | "failed"
                              | "stopped",
                    "names": N, "searched": N, "failed": N,
                    "skipped": ["<name>", ...], "stopped_at": null | N,
                    "detail": null | "..."}
    },
    "warnings": ["..."]
  }

gh and git run through skf-source-tree.py (the sibling in this folder): a
call the time limit stops is stopped with everything it started, and a gh
or git in the current folder is never run. Every gh call but the search
names github.com (HOST), the host `repo` checks the login for, whatever
GH_HOST says.

Exit codes:
  0  repo: JSON printed; fetch: the feeder now holds this fetch
  3  fetch: nothing was fetched, the feeder is as it was
  2  usage error: a malformed --repo, a --feeder not named .skf-temporal,
     an unreadable --exports
  1  unexpected error: {"status": "error", "message": ...} on stderr
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

HOST = "github.com"
FEEDER_NAME = ".skf-temporal"
FETCH_SUFFIX = ".new"
ISSUE_LIMIT = 100
PR_LIMIT = 100
RELEASE_LIMIT = 10
TARGETED_NAMES = 10
ISSUE_SEARCH_LIMIT = 5
SEARCH_WORKERS = 5
DEFAULT_TIMEOUT_SEC = 60.0
AUTH_TIMEOUT_SEC = 10.0
CHANGELOG_NAMES = ("CHANGELOG.md", "RELEASES.md")
FEEDER_FILES = ("issues.md", "prs.md", "releases.md", "changelog.md", "targeted-issues.md")

_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+$")
_HTTP_CODE_RE = re.compile(r"HTTP (\d{3})")
_SIBLING = None


class UsageError(Exception):
    """An input the helper cannot use (exit 2)."""


def _sibling():
    """skf-source-tree.py from this folder, loaded once: gh and git run
    through its runner (_run stops a call and all it started at the time
    limit; _resolve_outside_cwd never takes a gh or git planted in the
    current folder), and parse_remote reads a repository URL."""
    global _SIBLING
    if _SIBLING is None:
        path = Path(__file__).resolve().parent / "skf-source-tree.py"
        spec = importlib.util.spec_from_file_location("skf_source_tree", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SIBLING = module
    return _SIBLING


# --------------------------------------------------------------------------
# gh and git
# --------------------------------------------------------------------------


def _last_line(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _gh(args: list[str], timeout: float) -> tuple[str, str, str]:
    """`gh <args>`: (result, stdout, detail). result is ok, missing,
    unauthenticated, not-found, rate-limited, unsupported, timeout or failed."""
    tree = _sibling()
    exe = tree._resolve_outside_cwd("gh")
    if exe is None:
        return "missing", "", "gh is not installed"
    try:
        rc, out, err, _killed = tree._run([exe, *args], timeout)
    except (OSError, ValueError) as exc:
        return "missing", "", f"gh could not run: {exc}"
    if rc is None:
        return "timeout", "", f"gh did not answer within {timeout:g} seconds"
    stdout = out.decode("utf-8", errors="replace")
    stderr = err.decode("utf-8", errors="replace")
    if rc == 0:
        return "ok", stdout, ""
    detail = _last_line(stderr) or f"gh exited {rc}"
    text = (stderr + stdout).lower()
    m = _HTTP_CODE_RE.search(stderr)
    code = int(m.group(1)) if m else None
    if rc == 4:
        return "unauthenticated", "", "gh is not logged in"
    if code == 429 or "rate limit" in text:
        return "rate-limited", "", detail
    if code == 404:
        return "not-found", "", detail
    if "unknown command" in text or "unknown flag" in text:
        return "unsupported", "", detail
    return "failed", "", detail


def _git(cwd: str, *args: str) -> tuple[int | None, str]:
    """`git -C cwd <args>`: (returncode, stdout); returncode None when git cannot run."""
    tree = _sibling()
    exe = tree._resolve_outside_cwd("git")
    if exe is None:
        return None, ""
    try:
        rc, out, _err, _killed = tree._run([exe, "-c", f"core.hooksPath={os.devnull}", "-C", cwd, *args],
                                           AUTH_TIMEOUT_SEC)
    except (OSError, ValueError):
        return None, ""
    return rc, out.decode("utf-8", errors="replace").strip()


# --------------------------------------------------------------------------
# repo
# --------------------------------------------------------------------------


def github_repo(value: str | None) -> str | None:
    """`owner/repo` of the github.com repository a URL or shorthand names, else None."""
    parsed = _sibling().parse_remote(value)
    if parsed is None:
        return None
    host, owners, repo = parsed
    if host != "github.com" or len(owners) != 1:
        return None
    return f"{owners[0]}/{repo}"


def resolve_repo(source_repo: str) -> dict:
    """The repo result (see the repo section of the module docstring)."""
    result = {"repo": None, "via": None, "gh": "not-run", "skip_reason": None}
    value = (source_repo or "").strip()
    if _sibling().parse_remote(value) is not None:
        repo, via = github_repo(value), "url"
        if repo is None:
            result["skip_reason"] = "not-github"
            return result
    else:
        path = os.path.expanduser(value) if value else ""
        rc, inside = _git(path, "rev-parse", "--is-inside-work-tree") if path and os.path.isdir(path) else (1, "")
        if rc != 0 or inside != "true":
            result["skip_reason"] = "not-a-git-repo"
            return result
        rc, origin = _git(path, "remote", "get-url", "origin")
        if rc != 0 or not origin:
            result["skip_reason"] = "no-origin"
            return result
        repo, via = github_repo(origin), "origin"
        if repo is None:
            result["skip_reason"] = "not-github"
            return result
    result["repo"], result["via"] = repo, via
    status, _out, _detail = _gh(["auth", "status", "--hostname", HOST], AUTH_TIMEOUT_SEC)
    # gh auth status exits 1 when no account is logged in or its token is rejected.
    result["gh"] = {"ok": "ok", "missing": "missing", "unauthenticated": "unauthenticated",
                    "failed": "unauthenticated"}.get(status, "failed")
    if result["gh"] != "ok":
        result["skip_reason"] = f"gh-{result['gh']}"
    return result


# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------


def _text(value) -> str:
    """A body or title as the feeder holds it: `\\n` line endings, no trailing space."""
    text = value if isinstance(value, str) else ""
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _labels(item: dict) -> str:
    names = sorted(label.get("name", "") for label in item.get("labels") or [] if isinstance(label, dict))
    names = [name for name in names if name]
    return ", ".join(names) if names else "none"


def _by_number(items: list) -> list[dict]:
    items = [item for item in items if isinstance(item, dict)]
    return sorted(items, key=lambda item: -int(item.get("number") or 0))


def _document(title: str, sections: list[str]) -> str:
    return "\n\n".join([f"# {title}", *sections]) + "\n"


def render_issues(repo: str, issues: list) -> str:
    sections = []
    for item in _by_number(issues):
        lines = [f"## #{item.get('number')}: {_text(item.get('title'))}", "",
                 f"- State: {_text(item.get('state')).lower()}",
                 f"- Labels: {_labels(item)}",
                 f"- Created: {_text(item.get('createdAt'))}"]
        if item.get("closedAt"):
            lines.append(f"- Closed: {_text(item.get('closedAt'))}")
        body = _text(item.get("body"))
        sections.append("\n".join(lines) + (f"\n\n{body}" if body else ""))
    return _document(f"Issues: {repo}", sections)


def render_prs(repo: str, prs: list) -> str:
    sections = []
    for item in _by_number(prs):
        lines = [f"## #{item.get('number')}: {_text(item.get('title'))}", "",
                 f"- Merged: {_text(item.get('mergedAt'))}",
                 f"- Labels: {_labels(item)}"]
        body = _text(item.get("body"))
        sections.append("\n".join(lines) + (f"\n\n{body}" if body else ""))
    return _document(f"Merged pull requests: {repo}", sections)


def render_release(release: dict) -> str:
    tag = _text(release.get("tagName"))
    name = _text(release.get("name"))
    heading = f"## {tag}: {name}" if name and name != tag else f"## {tag}"
    lines = [heading, "", f"- Published: {_text(release.get('publishedAt'))}"]
    body = _text(release.get("body"))
    return "\n".join(lines) + (f"\n\n{body}" if body else "")


def render_releases(repo: str, sections: list[str]) -> str:
    return _document(f"Releases: {repo}", sections)


def render_targeted(repo: str, results: dict[str, list | None]) -> str:
    sections = []
    for name in sorted(results):
        found = results[name]
        if found is None:
            sections.append(f"## {name} (fetch failed)")
            continue
        if not found:
            sections.append(f"## {name} (no issues found)")
            continue
        parts = [f"## {name}"]
        for item in _by_number(found):
            heading = f"### #{item.get('number')}: {_text(item.get('title'))} ({_text(item.get('state')).lower()})"
            body = _text(item.get("body"))
            parts.append(heading + (f"\n\n{body}" if body else ""))
        sections.append("\n\n".join(parts))
    return _document(f"Issues naming exported functions: {repo}", sections)


def render_changelog(text: str) -> str:
    return _text(text) + "\n"


# --------------------------------------------------------------------------
# fetch
# --------------------------------------------------------------------------


def _json_list(stdout: str) -> list | None:
    try:
        data = json.loads(stdout or "[]")
    except ValueError:
        return None
    return data if isinstance(data, list) else None


def safe_names(names: list) -> tuple[list[str], list[str]]:
    """(the first TARGETED_NAMES search terms, the names before the last of
    them that nothing was left of)."""
    kept: list[str] = []
    skipped: list[str] = []
    for name in names:
        if len(kept) == TARGETED_NAMES:
            break
        if not isinstance(name, str):
            continue
        safe = re.sub(r"[^A-Za-z0-9_]", "", name)
        if not safe:
            skipped.append(name)
        elif safe not in kept:
            kept.append(safe)
    return kept, skipped


def _list_fetch(args: list[str], timeout: float) -> tuple[dict, list]:
    status, out, detail = _gh(args, timeout)
    if status != "ok":
        return {"status": "failed", "count": 0, "detail": detail or status}, []
    items = _json_list(out)
    if items is None:
        return {"status": "failed", "count": 0, "detail": "gh printed no JSON list"}, []
    return {"status": "ok" if items else "empty", "count": len(items), "detail": None}, items


def _changelog(repo: str, timeout: float) -> tuple[dict, str | None]:
    status, out, detail = _gh(["api", "--hostname", HOST, f"repos/{repo}/contents"], timeout)
    if status != "ok":
        return {"status": "failed", "file": None, "detail": detail or status}, None
    entries = _json_list(out) or []
    names = {e.get("name", "").lower(): e.get("name") for e in entries
             if isinstance(e, dict) and e.get("type") == "file" and isinstance(e.get("name"), str)}
    for wanted in CHANGELOG_NAMES:
        name = names.get(wanted.lower())
        if name is None:
            continue
        status, out, detail = _gh(["api", "--hostname", HOST, "-H", "Accept: application/vnd.github.raw",
                                   f"repos/{repo}/contents/{name}"], timeout)
        if status != "ok":
            return {"status": "failed", "file": name, "detail": detail or status}, None
        return {"status": "ok", "file": name, "detail": None}, out
    return {"status": "none", "file": None, "detail": None}, None


def _release_loop(repo: str, tags: list[dict], timeout: float, warnings: list[str]) -> tuple[dict, list[str]]:
    sections: list[str] = []
    record = {"status": "ok" if tags else "empty", "count": len(tags), "fetched": 0, "failed": 0,
              "stopped_at": None, "detail": None}
    for index, tag_item in enumerate(tags, start=1):
        tag = _text(tag_item.get("tagName")) if isinstance(tag_item, dict) else ""
        if not tag:
            continue
        status, out, detail = _gh(["release", "view", tag, "-R", f"{HOST}/{repo}", "--json",
                                   "tagName,name,publishedAt,body"], timeout)
        if status == "rate-limited":
            record["status"], record["stopped_at"] = "stopped", index
            break
        try:
            release = json.loads(out) if status == "ok" else None
        except ValueError:
            release = None
        if isinstance(release, dict):
            sections.append(render_release(release))
            record["fetched"] += 1
        else:
            sections.append(f"## {tag} (fetch failed: {detail or 'gh printed no JSON'})")
            record["failed"] += 1
    if record["stopped_at"] is not None:
        kept = "partial releases.md kept" if record["fetched"] else "no release notes fetched"
        warnings.append(f"Release fetch stopped at tag {record['stopped_at']}/{len(tags)} due to rate limiting: "
                        f"{kept}.")
    if not record["fetched"]:
        # Placeholders alone are no fetched content: they never make a releases.md.
        if record["failed"] and record["status"] == "ok":
            record["status"], record["detail"] = "failed", "every release fetch failed"
        sections = []
    return record, sections


def _searches(repo: str, names: list[str], timeout: float, warnings: list[str]) -> tuple[dict, dict]:
    record = {"status": "ok", "names": len(names), "searched": 0, "failed": 0, "skipped": [],
              "stopped_at": None, "detail": None}
    results: dict[str, list | None] = {}
    stop = False

    def search(name: str) -> tuple[str, str, str]:
        return _gh(["search", "issues", "--repo", repo, name, "--limit", str(ISSUE_SEARCH_LIMIT),
                    "--json", "number,title,state,body"], timeout)

    with concurrent.futures.ThreadPoolExecutor(max_workers=SEARCH_WORKERS) as pool:
        pending = {}
        queue = list(names)
        while (queue or pending) and not stop:
            while queue and len(pending) < SEARCH_WORKERS:
                name = queue.pop(0)
                pending[pool.submit(search, name)] = name
            done, _ = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in sorted(done, key=lambda f: names.index(pending[f])):
                name = pending.pop(future)
                status, out, detail = future.result()
                if status == "unsupported":
                    record["status"], record["detail"] = "unsupported", detail
                    stop = True
                elif status == "rate-limited":
                    if record["stopped_at"] is None:
                        record["status"], record["stopped_at"] = "stopped", names.index(name) + 1
                        warnings.append(f"Targeted search stopped at function {names.index(name) + 1}/{len(names)} "
                                        "due to rate limiting.")
                    stop = True
                else:
                    items = _json_list(out) if status == "ok" else None
                    results[name] = items
                    record["searched"] += 1
                    if items is None:
                        record["failed"] += 1
        for future, name in pending.items():  # finished or cancelled once a stop was seen
            future.cancel()
    if record["status"] == "unsupported":
        return record, {}
    if record["searched"] and record["failed"] == record["searched"] and record["status"] == "ok":
        record["status"], record["detail"] = "failed", "every search failed"
    if not any(results.values()):
        # Only an issue a search found is fetched content: "(fetch failed)" and
        # "(no issues found)" sections alone never make a targeted-issues.md.
        return record, {}
    return record, results


def _remove(path: Path) -> None:
    """Delete a folder the helper owns; a link or junction there is removed, never followed."""
    tree = _sibling()
    if tree._is_link_or_junction(path):
        if path.is_dir() and not path.is_symlink():
            path.rmdir()  # a Windows junction: rmdir drops the link, not its target
        else:
            path.unlink()
    elif path.is_dir():
        tree._rmtree(path)
    elif path.exists():
        path.unlink()


def fetch(repo: str, feeder: Path, exports: list | None, timeout: float) -> tuple[dict, int]:
    """Fetch into `<feeder>.new` and replace the feeder when a file was written: (result, exit code)."""
    staging = feeder.with_name(FEEDER_NAME + FETCH_SUFFIX)
    warnings: list[str] = []
    _remove(staging)
    staging.mkdir(parents=True)
    (staging / ".gitignore").write_bytes(b"*\n")

    lists = {
        "issues": ["issue", "list", "-R", f"{HOST}/{repo}", "--state", "all", "--limit", str(ISSUE_LIMIT),
                   "--json", "number,title,state,labels,createdAt,closedAt,body"],
        "prs": ["pr", "list", "-R", f"{HOST}/{repo}", "--state", "merged", "--limit", str(PR_LIMIT),
                "--json", "number,title,mergedAt,labels,body"],
        "releases": ["release", "list", "-R", f"{HOST}/{repo}", "--limit", str(RELEASE_LIMIT),
                     "--json", "tagName,name,publishedAt"],
    }
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        listed = {key: pool.submit(_list_fetch, args, timeout) for key, args in lists.items()}
        changelog_future = pool.submit(_changelog, repo, timeout)
        results = {key: future.result() for key, future in listed.items()}
        changelog_record, changelog_text = changelog_future.result()

    files: dict[str, str] = {}
    fetches: dict[str, dict] = {}
    for key, render in (("issues", render_issues), ("prs", render_prs)):
        record, items = results[key]
        fetches[key] = record
        if items:
            files[f"{key}.md"] = render(repo, items)

    tags_record, tags = results["releases"]
    if tags_record["status"] == "failed":
        fetches["releases"] = {**tags_record, "fetched": 0, "failed": 0, "stopped_at": None}
    else:
        fetches["releases"], sections = _release_loop(repo, tags, timeout, warnings)
        if sections:
            files["releases.md"] = render_releases(repo, sections)

    fetches["changelog"] = changelog_record
    if changelog_text is not None and _text(changelog_text):
        files["changelog.md"] = render_changelog(changelog_text)

    names, skipped = safe_names(exports or [])
    if names:
        fetches["targeted"], searched = _searches(repo, names, timeout, warnings)
        if searched:
            files["targeted-issues.md"] = render_targeted(repo, searched)
    else:
        fetches["targeted"] = {"status": "none", "names": 0, "searched": 0, "failed": 0, "skipped": [],
                               "stopped_at": None, "detail": None}
    fetches["targeted"]["skipped"] = skipped
    for name in skipped:
        warnings.append(f"Targeted search skipped {name!r}: no letter, digit or underscore to search for.")

    for name, text in files.items():
        (staging / name).write_bytes(text.encode("utf-8"))

    if files:
        _remove(feeder)
        os.replace(staging, feeder)
        status, code = "replaced", 0
    else:
        _remove(staging)
        warnings.append("No temporal context could be fetched: the feeder keeps what the last good fetch left.")
        status, code = "kept", 3
    present = sorted(p.name for p in feeder.glob("*.md")) if feeder.is_dir() else []
    return {"status": status, "repo": repo, "feeder": str(feeder), "files": present,
            "fetches": fetches, "warnings": warnings}, code


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def read_exports(source: str) -> list:
    """The --exports names: a JSON list, or an object with a top_exports list."""
    try:
        text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise UsageError(f"cannot read --exports {source}: {exc}") from exc
    try:
        data = json.loads(text) if text.strip() else []
    except ValueError as exc:
        raise UsageError(f"--exports {source} is not JSON: {exc}") from exc
    if isinstance(data, dict):
        data = data.get("top_exports") or []
    if not isinstance(data, list):
        raise UsageError(f"--exports {source} must be a JSON list of names or hold a top_exports list")
    return data


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-fetch-temporal.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    repo = sub.add_parser("repo", help="which GitHub repository a source names, and whether gh can read it")
    repo.add_argument("--source-repo", required=True, help="the brief's source_repo: a URL, owner/repo or a local path")
    fetch_cmd = sub.add_parser("fetch", help="fetch issues, pull requests, releases and the changelog")
    fetch_cmd.add_argument("--repo", required=True, help="owner/repo, as the repo command printed it")
    fetch_cmd.add_argument("--feeder", required=True, help="the feeder folder, named .skf-temporal")
    fetch_cmd.add_argument("--exports", metavar="FILE",
                           help="the top_exports names as JSON (a file, or - for stdin)")
    fetch_cmd.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SEC,
                           help=f"seconds each gh call may take (default {DEFAULT_TIMEOUT_SEC:g})")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "repo":
            result, code = resolve_repo(args.source_repo), 0
        else:
            if not _REPO_RE.match(args.repo or ""):
                raise UsageError(f"--repo must be owner/repo, got {args.repo!r}")
            feeder = Path(args.feeder)
            if feeder.name != FEEDER_NAME:
                raise UsageError(f"--feeder must be a folder named {FEEDER_NAME}, got {args.feeder!r}")
            if args.timeout <= 0:
                raise UsageError("--timeout must be more than 0")
            exports = read_exports(args.exports) if args.exports else None
            result, code = fetch(args.repo, feeder, exports, args.timeout)
    except UsageError as exc:
        sys.stderr.write(f"skf-fetch-temporal: {exc}\n")
        return 2
    except Exception as exc:  # never a traceback in place of the JSON the step reads
        sys.stderr.write(json.dumps({"status": "error", "message": f"{type(exc).__name__}: {exc}"}) + "\n")
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return code


def _force_utf8(*streams) -> None:
    """Reconfigure stdin, stdout and stderr to UTF-8, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which cannot carry every
    character of an issue title in the JSON, nor read UTF-8 export names
    piped to stdin (reconfigured here, before the first read).
    """
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


if __name__ == "__main__":
    _force_utf8(sys.stdin, sys.stdout, sys.stderr)
    sys.exit(main())
