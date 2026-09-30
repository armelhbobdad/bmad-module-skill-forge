# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF GitHub Probe: can this GitHub repository be read, and if not, why.

brief-skill checks a GitHub URL before the user spends time on a brief,
and quick-skill checks a version tag and lists the files it reads. One
`gh api` call cannot tell a missing gh, a logged-out gh, a repository that
does not exist and one the account may not read apart, and an
unauthenticated `curl` answers 404 for every private repository. This
helper runs the probes in order, stops at the first that reads the
repository, and otherwise names the cause.

CLI:
  uv run skf-github-probe.py repo --repo <repo> [--timeout <seconds>]
  uv run skf-github-probe.py tags --repo <repo> [--want <tag>]... \\
      [--limit <n>] [--timeout <seconds>]
  uv run skf-github-probe.py tree --repo <repo> [--ref <ref>] \\
      [--timeout <seconds>]

--repo takes `owner/repo`, `github.com/owner/repo`, an https, ssh or
`git@github.com:` URL, with or without `.git` and a `/tree/<ref>/...`
tail. Only github.com repositories are probed.

Probes, in order:
  repo  `gh api repos/{owner}/{repo}`; the unauthenticated REST API
        (https://api.github.com/repos/{owner}/{repo}), unless gh answered
        404 (a repository an account cannot see is not public either);
        `git ls-remote --symref
        https://github.com/{owner}/{repo} HEAD`, which uses the user's git
        credentials (never a prompt).
  tags  `gh api --paginate repos/{owner}/{repo}/tags`; `git ls-remote
        --tags https://github.com/{owner}/{repo}`.
  tree  `gh api repos/{owner}/{repo}/git/trees/{ref}?recursive=1`; the
        same path on the unauthenticated REST API, unless gh answered 404
        for the repository. When the tree is not found, the same client
        reads the repository, to tell a missing ref from a missing
        repository: GitHub answers 404 for both, so a tree's 404 alone
        never counts as a missing repository.
  When a probe finds nothing, the owner is looked up (`users/{owner}`), so
  a misspelled user or organization is reported as such.

Output (one ASCII JSON line; every key of the command is always present):
  every command:
    status   "ok" | "unavailable"
    cause    null | "repo-not-found" | "no-access" | "gh-missing" |
             "gh-unauthenticated" | "ref-not-found" | "unreachable" |
             "invalid-repo" (CAUSES)
    message  one line for the user naming the cause and the fix, else null
    repo     "owner/repo", or null for invalid-repo
    gh       "ok" | "missing" | "unauthenticated" | "failed" | "not-run"
             (GH_STATES): gh answered (an HTTP error is an answer), is not
             installed, is not logged in or its token is rejected, failed
             on the network or a time limit, or was not needed
    account  the login gh uses, when a message names it, else null
    via      "gh" | "api" | "git" | null: the probe that read the repository
    probes   [{"probe": "gh"|"api"|"git", "target": "repo"|"tags"|"tree"|
             "owner", "result": ..., "detail": ...}] in the order run;
             result is "ok" | "missing" | "unauthenticated" | "not-found" |
             "forbidden" | "auth-required" | "rate-limited" | "network" |
             "timeout" (PROBE_RESULTS)
  repo:  private (true | false | null), default_branch (name or null)
  tags:  tags (names, newest version first, then the others by name, at
         most --limit, 20 by default, 0 for all), count (every tag),
         match (the first --want tag that exists, else null), found
         ({tag: commit} for the --want tags that exist), missing (the
         --want tags the listing lacks). When the listing could not be
         read, found and missing are empty: only a listing says a tag is
         absent.
  tree:  ref (as given; "HEAD", the default branch, for an empty, `null`,
         `none` or `head` --ref in any letter case), tree (file paths:
         `echo` the JSON into skf-detect-language.py as it is), count,
         truncated (GitHub cut the list short)

cause:
  repo-not-found      an authenticated probe (gh, or git with the user's
                      credentials) found no such repository: it does not
                      exist, or it is private and the account cannot see
                      it (GitHub answers 404 then), or the owner does not
                      exist
  no-access           an authenticated probe was refused (HTTP 403: an
                      organization's SAML or IP rules, a token without the
                      scope)
  gh-missing          gh is not installed, and nothing else could read the
                      repository: it is private or does not exist
  gh-unauthenticated  gh is not logged in (or its token is rejected), and
                      nothing else could read the repository
  ref-not-found       tree: the repository was read, the ref was not found
  unreachable         the probes failed on the network, a time limit or
                      the API rate limit
  invalid-repo        --repo names no github.com repository

The whole call finishes within about --timeout seconds (60 by default);
one probe gets at most 20 of them, so a slow probe leaves time for the
next. gh and git run through skf-source-tree.py (the sibling in this
folder, which must sit beside this script): a call the limit stops is
stopped with everything it started, and a gh or git in the current
folder is never run. gh runs with `--hostname github.com`; git runs from
the system temp folder with LC_ALL=C, no hooks, no terminal or
credential-manager prompt and the git location variables removed.

Exit codes:
  0  status ok
  3  status unavailable (JSON on stdout; the caller decides what to do)
  1  unexpected error: {"status": "error", "message": ...} on stderr
  2  usage error (argparse)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import socket
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CAUSES = ("repo-not-found", "no-access", "gh-missing", "gh-unauthenticated", "ref-not-found", "unreachable",
          "invalid-repo")
GH_STATES = ("ok", "missing", "unauthenticated", "failed", "not-run")
PROBE_RESULTS = ("ok", "missing", "unauthenticated", "not-found", "forbidden", "auth-required", "rate-limited",
                 "network", "timeout")
API_ROOT = "https://api.github.com"
WEB_ROOT = "https://github.com"
USER_AGENT = "skf-github-probe/1.0 (+https://github.com/armelhbobdad/bmad-module-skill-forge)"
DEFAULT_TIMEOUT_SEC = 60.0
PROBE_TIMEOUT_SEC = 20.0
DEFAULT_TAG_LIMIT = 20
# A GitHub owner or repository name: letters, digits, `-`, `_` and `.`.
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_URL_RE = re.compile(r"^(?:(?:https?|ssh|git)://(?:[^@/]+@)?|git@)?(?:www\.)?github\.com[:/](?P<path>.+)$",
                     re.IGNORECASE)
_HTTP_CODE_RE = re.compile(r"\(HTTP (\d{3})\)")

_SOURCE_TREE = None


def _sibling():
    """skf-source-tree.py from this folder, loaded once: gh and git run
    through its runner (_run stops a call and all it started at the time
    limit; _resolve_outside_cwd never takes a gh or git planted in the
    current folder), tags sort with its split_version and refs are checked
    with its REF_RE."""
    global _SOURCE_TREE
    if _SOURCE_TREE is None:
        path = Path(__file__).resolve().parent / "skf-source-tree.py"
        spec = importlib.util.spec_from_file_location("skf_source_tree", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SOURCE_TREE = module
    return _SOURCE_TREE


# --------------------------------------------------------------------------
# Repository names
# --------------------------------------------------------------------------


def parse_repo(value: str | None) -> tuple[str, str] | None:
    """(owner, repo) of a github.com repository, else None."""
    text = (value or "").strip()
    m = _URL_RE.match(text)
    if m:
        path = re.split(r"[?#]", m.group("path"), maxsplit=1)[0]
    elif "://" in text or "@" in text or ":" in text:
        return None
    else:
        path = text
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2 or (not m and len(parts) != 2):
        return None
    owner, repo = parts[0], parts[1]
    if repo.lower().endswith(".git"):
        repo = repo[: -len(".git")]
    if not all(_NAME_RE.match(part) and part.strip(".") for part in (owner, repo)) or owner.startswith("-"):
        return None
    return owner, repo


# --------------------------------------------------------------------------
# Probes
# --------------------------------------------------------------------------


_deadline: float | None = None


def _start_clock(seconds: float | None) -> None:
    global _deadline
    _deadline = None if seconds is None else time.monotonic() + max(0.0, seconds)


def _budget() -> float | None:
    """Seconds the next probe may take: PROBE_TIMEOUT_SEC or what is left; None when nothing is."""
    if _deadline is None:
        return PROBE_TIMEOUT_SEC
    left = _deadline - time.monotonic()
    return min(PROBE_TIMEOUT_SEC, left) if left > 0.5 else None


def _last_line(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith(("fatal:", "error:", "gh:")):
            return line
    return lines[-1] if lines else ""


def _gh(*args: str) -> tuple[str, str, str]:
    """`gh api --hostname github.com <args>`: (result, stdout, detail)."""
    tree = _sibling()
    exe = tree._resolve_outside_cwd("gh")
    if exe is None:
        return "missing", "", "gh is not installed"
    timeout = _budget()
    if timeout is None:
        return "timeout", "", "no time was left to run gh"
    try:
        rc, out, err, _killed = tree._run([exe, "api", "--hostname", "github.com", *args], timeout)
    except (OSError, ValueError) as e:
        return "missing", "", f"gh could not run: {e}"
    if rc is None:
        return "timeout", "", f"gh did not answer within {timeout:g} seconds"
    stdout = out.decode("utf-8", errors="replace")
    detail = _last_line(err.decode("utf-8", errors="replace"))
    if rc == 0:
        return "ok", stdout, ""
    if rc == 4:  # gh: authentication required
        return "unauthenticated", "", "gh is not logged in"
    m = _HTTP_CODE_RE.search(detail)
    code = int(m.group(1)) if m else None
    if code == 401:
        return "unauthenticated", "", detail
    if code == 404:
        return "not-found", "", detail
    if code == 429 or (code == 403 and "rate limit" in (detail + stdout).lower()):
        return "rate-limited", "", detail
    if code == 403:
        return "forbidden", "", detail
    return "network", "", detail or f"gh exited {rc}"


def _api(path: str) -> tuple[str, str, str]:
    """GET {API_ROOT}/{path} without credentials: (result, body, detail)."""
    timeout = _budget()
    if timeout is None:
        return "timeout", "", "no time was left to call the GitHub API"
    req = urllib.request.Request(f"{API_ROOT}/{path}", headers={
        "Accept": "application/vnd.github+json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return "ok", resp.read().decode("utf-8", errors="replace"), ""
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except OSError:
            body = ""
        detail = f"HTTP {e.code} from {API_ROOT}/{path}"
        if e.code == 404:
            return "not-found", "", detail
        if e.code in (403, 429):
            limited = "rate limit" in body.lower() or e.headers.get("X-RateLimit-Remaining") == "0"
            return ("rate-limited" if limited or e.code == 429 else "forbidden"), "", detail
        if e.code == 451:
            return "forbidden", "", detail
        return "network", "", detail
    except (TimeoutError, socket.timeout):
        return "timeout", "", f"{API_ROOT} did not answer within {timeout:g} seconds"
    except (urllib.error.URLError, OSError, ValueError) as e:
        return "network", "", f"{API_ROOT}: {getattr(e, 'reason', e)}"


def _classify_git(stderr: str) -> str:
    """The probe result a failed `git ls-remote` of a github.com URL reports."""
    text = stderr.lower()
    if "returned error: 403" in text or "saml" in text or ("permission to" in text and "denied" in text):
        return "forbidden"
    if ("repository not found" in text or "returned error: 404" in text
            or ("repository '" in text and "not found" in text)):
        return "not-found"
    if any(sign in text for sign in ("could not read username", "could not read password",
                                     "terminal prompts disabled", "returned error: 401",
                                     "authentication failed", "invalid username or password")):
        return "auth-required"
    return "network"


def _git(*args: str) -> tuple[str, str, str]:
    """`git <args>` from the system temp folder: (result, stdout, detail)."""
    tree = _sibling()
    exe = tree._resolve_outside_cwd("git")
    if exe is None:
        return "missing", "", "git is not installed"
    timeout = _budget()
    if timeout is None:
        return "timeout", "", "no time was left to run git"
    try:
        rc, out, err, _killed = tree._run([exe, "-c", f"core.hooksPath={os.devnull}", "-C",
                                           tempfile.gettempdir(), *args], timeout)
    except (OSError, ValueError) as e:
        return "missing", "", f"git could not run: {e}"
    if rc is None:
        return "timeout", "", f"git did not answer within {timeout:g} seconds"
    if rc == 0:
        return "ok", out.decode("utf-8", errors="replace"), ""
    stderr = err.decode("utf-8", errors="replace")
    return _classify_git(stderr), "", _last_line(stderr) or f"git exited {rc}"


def _json(text: str):
    """A JSON document, or the items of several arrays `gh --paginate` printed one after another."""
    decoder = json.JSONDecoder()
    docs, i, text = [], 0, text.strip()
    while i < len(text):
        doc, end = decoder.raw_decode(text, i)
        docs.append(doc)
        i = end
        while i < len(text) and text[i].isspace():
            i += 1
    if len(docs) == 1:
        return docs[0]
    return [item for doc in docs if isinstance(doc, list) for item in doc]


# --------------------------------------------------------------------------
# Causes
# --------------------------------------------------------------------------


class Probe:
    """One command's probes, their records and the state of gh."""

    def __init__(self, owner: str, repo: str):
        self.owner, self.repo = owner, repo
        self.records: list[dict] = []
        self.gh = "not-run"

    def record(self, probe: str, target: str, result: str, detail: str) -> str:
        self.records.append({"probe": probe, "target": target, "result": result, "detail": detail or None})
        if probe == "gh":
            if result in ("missing", "unauthenticated"):
                self.gh = result
            elif result in ("ok", "not-found", "forbidden"):
                self.gh = "ok"
            elif self.gh == "not-run":
                self.gh = "failed"
        return result

    def gh_call(self, target: str, *args: str) -> tuple[str, str]:
        result, out, detail = _gh(*args)
        return self.record("gh", target, result, detail), out

    def api_call(self, target: str, path: str) -> tuple[str, str]:
        result, out, detail = _api(path)
        return self.record("api", target, result, detail), out

    def git_call(self, target: str, *args: str) -> tuple[str, str]:
        result, out, detail = _git(*args)
        return self.record("git", target, result, detail), out

    def results(self, probe: str) -> list[str]:
        """This probe's results, without the owner lookup and without a tree's 404: GitHub
        answers 404 for a missing ref as for a missing repository."""
        return [r["result"] for r in self.records if r["probe"] == probe and r["target"] != "owner"
                and not (r["target"] == "tree" and r["result"] == "not-found")]

    def owner_missing(self) -> bool:
        """Look the owner up with gh when it answers, else the API; True only on a 404."""
        if self.gh == "ok":
            result, _out = self.gh_call("owner", f"users/{self.owner}")
        else:
            result, _out = self.api_call("owner", f"users/{self.owner}")
        return result == "not-found"

    def cause(self) -> str:
        gh, git, api = self.results("gh"), self.results("git"), self.results("api")
        if "forbidden" in gh or "forbidden" in git:
            return "no-access"
        found_nothing = "not-found" in gh or "not-found" in git
        hidden = "not-found" in api or "auth-required" in git
        if (found_nothing or hidden) and self.owner_missing():
            return "repo-not-found"
        if found_nothing:
            return "repo-not-found"
        flaky = any(r in ("network", "timeout", "rate-limited") for r in api + git)
        if self.gh in ("missing", "unauthenticated") and (hidden or not flaky):
            return f"gh-{self.gh}"
        return "unreachable"

    def account(self) -> str | None:
        if self.gh != "ok":
            return None
        result, out, _detail = _gh("user")
        try:
            login = json.loads(out).get("login") if result == "ok" else None
        except (ValueError, AttributeError):
            login = None
        return login if isinstance(login, str) else None

    def message(self, cause: str, account: str | None) -> str:
        name = f"{self.owner}/{self.repo}"
        details = "; ".join(dict.fromkeys(r["detail"] for r in self.records
                                          if r["detail"] and r["result"] != "ok"))
        if cause == "repo-not-found":
            if any(r["target"] == "owner" and r["result"] == "not-found" for r in self.records):
                return f"GitHub has no user or organization named {self.owner}; check the URL."
            who = f"the GitHub account {account}" if account else "your GitHub credentials"
            return (f"{name} was not found with {who}: it does not exist, or it is private and that account "
                    "cannot see it. Check the URL, or log in with an account that can read it (gh auth login).")
        if cause == "no-access":
            return (f"GitHub refused access to {name} ({details}). Authorize your token for the organization "
                    "(gh auth refresh), or use an account that can read it.")
        if cause == "gh-missing":
            return (f"{name} is private or does not exist: nothing could read it without a GitHub login, and "
                    "the GitHub CLI (gh) is not installed. Install gh and run gh auth login, or check the URL.")
        if cause == "gh-unauthenticated":
            return (f"{name} is private or does not exist: nothing could read it without a GitHub login, and "
                    "the GitHub CLI (gh) is not logged in. Run gh auth login, or check the URL.")
        return f"Could not reach GitHub to read {name} ({details or 'no probe could run'}); try again later."

    def output(self, status: str, via: str | None, cause: str | None = None, message: str | None = None,
               account: str | None = None, **extra) -> dict:
        return {"status": status, "cause": cause, "message": message, "repo": f"{self.owner}/{self.repo}",
                "gh": self.gh, "account": account, "via": via, "probes": self.records, **extra}

    def unavailable(self, **extra) -> dict:
        cause = self.cause()
        owner_gone = any(r["target"] == "owner" and r["result"] == "not-found" for r in self.records)
        account = self.account() if cause == "repo-not-found" and not owner_gone else None
        return self.output("unavailable", None, cause, self.message(cause, account), account, **extra)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


# What each command reports besides the common keys when it read nothing;
# found and missing stay empty then, since no listing says a tag is absent.
_EMPTY = {
    "repo": {"private": None, "default_branch": None},
    "tags": {"tags": [], "count": 0, "match": None, "found": {}, "missing": []},
    "tree": {"ref": "HEAD", "tree": [], "count": 0, "truncated": False},
}


def probe_repo(owner: str, repo: str) -> dict:
    p = Probe(owner, repo)

    def read(body: str, via: str) -> dict | None:
        try:
            data = json.loads(body)
        except ValueError:
            return None
        if not isinstance(data, dict):
            return None
        private = data.get("private")
        branch = data.get("default_branch")
        return p.output("ok", via, private=private if isinstance(private, bool) else None,
                        default_branch=branch if isinstance(branch, str) else None)

    result, body = p.gh_call("repo", f"repos/{owner}/{repo}")
    if result == "ok" and (out := read(body, "gh")):
        return out
    if result != "not-found":
        result, body = p.api_call("repo", f"repos/{owner}/{repo}")
        if result == "ok" and (out := read(body, "api")):
            return out
    result, text = p.git_call("repo", "ls-remote", "--symref", "--", f"{WEB_ROOT}/{owner}/{repo}", "HEAD")
    if result == "ok":
        branch = None
        for line in text.splitlines():
            left, _, name = line.partition("\t")
            if left.startswith("ref: refs/heads/") and name.strip() == "HEAD":
                branch = left[len("ref: refs/heads/"):].strip()
        private = True if "not-found" in p.results("api") else None
        return p.output("ok", "git", private=private, default_branch=branch)
    return p.unavailable(**_EMPTY["repo"])


def _sorted_tags(names) -> list[str]:
    versioned, other = [], []
    for name in names:
        split = _sibling().split_version(name)
        (versioned if split else other).append((split[1] if split else None, name))
    versioned.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [name for _key, name in versioned] + sorted(name for _key, name in other)


def probe_tags(owner: str, repo: str, wants: list[str], limit: int) -> dict:
    p = Probe(owner, repo)
    tags: dict[str, str | None] | None = None
    via = None
    result, body = p.gh_call("tags", "--paginate", f"repos/{owner}/{repo}/tags?per_page=100")
    if result == "ok":
        try:
            items = _json(body)
            if isinstance(items, list):
                tags = {}
                for item in items:
                    if isinstance(item, dict) and isinstance(item.get("name"), str):
                        commit = item.get("commit")
                        sha = commit.get("sha") if isinstance(commit, dict) else None
                        tags[item["name"]] = sha if isinstance(sha, str) else None
                via = "gh"
        except ValueError:
            tags = None
    if tags is None:
        result, text = p.git_call("tags", "ls-remote", "--tags", "--", f"{WEB_ROOT}/{owner}/{repo}")
        if result == "ok":
            tags = {}
            for line in text.splitlines():
                sha, _, name = line.partition("\t")
                name = name.strip()
                if not name.startswith("refs/tags/"):
                    continue
                name = name[len("refs/tags/"):]
                if name.endswith("^{}"):
                    tags[name[:-3]] = sha.strip()
                else:
                    tags.setdefault(name, sha.strip())
            via = "git"
    if tags is None:
        return p.unavailable(**_EMPTY["tags"])
    ordered = _sorted_tags(tags)
    wanted = list(dict.fromkeys(wants))
    found = {name: tags[name] for name in wanted if name in tags}
    return p.output("ok", via, tags=ordered[:limit] if limit > 0 else ordered, count=len(ordered),
                    match=next((name for name in wanted if name in tags), None), found=found,
                    missing=[name for name in wanted if name not in tags])


def _tree_ref(value: str | None) -> str:
    """The ref tree reads: "HEAD" for an empty, `null`, `none` or `head` value (any letter case)."""
    ref = (value or "").strip()
    return "HEAD" if ref.lower() in ("", "null", "none", "head") else ref


def probe_tree(owner: str, repo: str, ref: str) -> dict:
    p = Probe(owner, repo)
    ref = _tree_ref(ref)
    empty = {**_EMPTY["tree"], "ref": ref}
    path = f"repos/{owner}/{repo}/git/trees/{urllib.parse.quote(ref, safe='')}?recursive=1"

    def read(body: str, via: str) -> dict | None:
        try:
            data = json.loads(body)
        except ValueError:
            return None
        if not isinstance(data, dict) or not isinstance(data.get("tree"), list):
            return None
        files = [e["path"] for e in data["tree"]
                 if isinstance(e, dict) and e.get("type") == "blob" and isinstance(e.get("path"), str)]
        return p.output("ok", via, ref=ref, tree=files, count=len(files),
                        truncated=data.get("truncated") is True)

    if ref != "HEAD" and not _sibling().REF_RE.fullmatch(ref):
        return p.output("unavailable", None, "ref-not-found",
                        f"{ref} is not a valid branch, tag or commit name.", **empty)
    result, body = p.gh_call("tree", path)
    if result == "ok" and (out := read(body, "gh")):
        return out
    repo_result = None
    if result == "not-found":
        repo_result, _body = p.gh_call("repo", f"repos/{owner}/{repo}")
        if repo_result == "ok":
            return p.output("unavailable", None, "ref-not-found",
                            f"{owner}/{repo} has no branch, tag or commit named {ref}.", **empty)
    # Only gh's 404 for the repository itself says the anonymous API cannot read it either.
    if repo_result != "not-found":
        result, body = p.api_call("tree", path)
        if result == "ok" and (out := read(body, "api")):
            return out
        if result == "not-found":
            repo_result, _body = p.api_call("repo", f"repos/{owner}/{repo}")
            if repo_result == "ok":
                return p.output("unavailable", None, "ref-not-found",
                                f"{owner}/{repo} has no branch, tag or commit named {ref}.", **empty)
    return p.unavailable(**empty)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-github-probe",
        description="Tell whether a GitHub repository can be read and why not; list its tags or files.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--repo", required=True, help="owner/repo or a github.com URL")
        p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SEC,
                       help="seconds the whole call may take (default 60)")

    common(sub.add_parser("repo", help="can the repository be read"))
    p_tags = sub.add_parser("tags", help="list the repository's tags")
    common(p_tags)
    p_tags.add_argument("--want", action="append", default=[], help="a tag to look for (repeatable)")
    p_tags.add_argument("--limit", type=int, default=DEFAULT_TAG_LIMIT,
                        help="tags to list, newest first (default 20; 0 for all)")
    p_tree = sub.add_parser("tree", help="list the repository's files at a ref")
    common(p_tree)
    p_tree.add_argument("--ref", default="HEAD", help="branch, tag or commit (default: the default branch)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        _start_clock(args.timeout)
        parsed = parse_repo(args.repo)
        if parsed is None:
            out = {"status": "unavailable", "cause": "invalid-repo",
                   "message": f"{args.repo} is not a github.com repository (expected owner/repo or a URL).",
                   "repo": None, "gh": "not-run", "account": None, "via": None, "probes": [],
                   **_EMPTY[args.cmd]}
            if args.cmd == "tree":
                out["ref"] = _tree_ref(args.ref)
        elif args.cmd == "repo":
            out = probe_repo(*parsed)
        elif args.cmd == "tags":
            out = probe_tags(*parsed, args.want, args.limit)
        else:
            out = probe_tree(*parsed, args.ref)
    except Exception as e:  # noqa: BLE001 - one JSON error line, never a traceback
        print(json.dumps({"status": "error", "message": f"{type(e).__name__}: {e}"}), file=sys.stderr)
        return 1
    print(json.dumps(out))
    return 0 if out["status"] == "ok" else 3


if __name__ == "__main__":
    raise SystemExit(main())
