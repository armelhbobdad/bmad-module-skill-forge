# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Resolve Package: read a quick-skill target, and resolve a package
name to its GitHub repository.

`parse-target` splits what the user typed into its parts. `resolve` walks
the canonical fallback chain documented in
`src/skf-quick-skill/references/registry-resolution.md`:

  1. npm registry        (JavaScript/TypeScript)
  2. PyPI registry       (Python)
  3. crates.io registry  (Rust)

Per-call timeout (default 10s); a timeout is treated as a soft failure
and the resolver falls through to the next entry. Web-search fallback
is intentionally NOT in this helper: registries are deterministic;
web search is judgment, and stays in the LLM step.

CLI:

  uv run skf-resolve-package.py parse-target [--target <text>]
  uv run skf-resolve-package.py resolve <package_name> \\
      [--registry npm|pypi|crates] [--language <hint>] [--timeout 10]

parse-target reads the target from stdin when --target is not given, so a
target holding quotes or `$` reaches it unchanged. The form earlier SKF
versions called, `skf-resolve-package.py <package_name> [--timeout 10]`,
still runs resolve.

parse-target output (stdout JSON; every key is always present, null when
the kind has none):

  kind:            "github" | "package" | "registry-page" | "other-host" |
                   "local-path" | "unparsed" (KINDS)
  input:           the target as read, without surrounding whitespace or
                   one pair of quotes, backticks or angle brackets
  target_version:  the version a trailing `@<version>` or `==<version>`
                   pins, or a registry page's version
  dist_tag:        package: the npm dist-tag a trailing `@<tag>` names
                   (`latest`, `canary`); it pins no version
  owner, repo:     github: the repository
  url:             github: https://github.com/<owner>/<repo>;
                   other-host: the URL as given
  ref, subdir:     github: the ref and the folder of a
                   `/tree/<ref>/<folder>` URL (the ref is one path part)
  package_name:    package, registry-page: the name to resolve
  registry:        "npm" | "pypi" | "crates" | null: the one registry
                   that can hold the name: a registry page's, PyPI for a
                   `==` pin, npm for a scoped `@scope/name`
  skill_name:      github, package, registry-page: the name the skill is
                   written under: the package name, else the last part
                   of a `/tree/` folder, else the repository name, in
                   lower case with each run of other characters turned
                   into one hyphen (`@babel/core` is `babel-core`,
                   `vercel/next.js` is `next-js`)
  host:            other-host: the host name, in lower case
  path:            local-path: the path as given

  Shapes, in the order they are tried:
    local-path     starts with `.`, `/`, `\\`, `~`, a drive letter or
                   `file://`
    package        `<name>==<version>` (PyPI, extras dropped)
    github         an https, http, git, ssh or git+ URL of github.com
                   (www. included, `:` or a port after the host),
                   `github.com/<owner>/<repo>`,
                   `git@github.com:<owner>/<repo>`,
                   `github:<owner>/<repo>` or `<owner>/<repo>`; `.git`, a
                   trailing slash, a query, a fragment and any other path
                   after the repository are dropped
    registry-page  https://www.npmjs.com/package/<name>[/v/<version>],
                   https://pypi.org/project/<name>[/<version>] (or
                   pypi.python.org/pypi/...),
                   https://crates.io/crates/<name>[/<version>]; a page
                   tail that is no version (crates.io's `/versions`) is
                   dropped
    other-host     any other URL, `gitlab:` or `bitbucket:` shortcuts, or
                   `<host>/<path>` whose first part is a host name
    package        an npm, PyPI or crates.io name, `@scope/name` included
    unparsed       anything else: prose, an empty target

  Every shape but local-path may end in `@<version>`: the text after the
  last `@` (not the one that opens a scope) is the version when it is one
  word of letters, digits, `.`, `_`, `+` and `-` that starts with a digit,
  or with `v` and a digit (`0.5.0`, `v2.1.0-beta`). `==<version>` takes
  the same word. After a package name, a word that starts with a letter
  instead is an npm dist-tag.

resolve output (stdout JSON):

  status:            "ok" | "ambiguous" | "fallthrough" (STATUSES)
  package_name:      "<input>"
  resolved_url:      "https://github.com/<owner>/<repo>"  (ok, ambiguous)
  repo_owner:        "<owner>"                            (ok, ambiguous)
  repo_name:         "<repo>"                             (ok, ambiguous)
  skill_name:        the package's skill name, as parse-target
                     writes it                            (ok, ambiguous)
  registry_used:     "npm" | "pypi" | "crates"            (ok, ambiguous)
  source_subdir:     the package's folder in the repository, else null
                     (ok, ambiguous): npm's repository.directory, or the
                     folder of a `/tree/<ref>/<folder>` repository URL
  name_found_in:     the registries that answered for the name with
                     anything other than a 404 or a timeout (outcome ok,
                     no-github-link or error), in chain order
  registries_tried:  ["npm", ...]
  registry_outcomes: {"npm": "ok|404|timeout|error|no-github-link", ...}

  ok:           the first registry that answered for the name resolved it.
  ambiguous:    a registry resolved the name after an earlier one in the
                chain answered for it (name_found_in holds both), so the
                name may belong to two projects. The fields name the later
                registry's repository; the caller decides.
  fallthrough:  no registry gave a GitHub URL; the LLM step falls back to
                web search.

  An error (a registry that could not be read: an HTTP error other than
  404, a refused connection, an unreadable answer) counts as an answer,
  since that registry may still hold the name: while npm cannot be read,
  a name PyPI resolves is ambiguous. A timeout does not count (#582's
  rule, accepted): when an earlier registry times out, a later one's
  resolution is ok, and registry_outcomes shows the timeout.

  --registry queries that registry alone. --language picks the registry
  of a language hint (LANGUAGE_REGISTRIES, any letter case: javascript,
  typescript, js and ts are npm, python and py PyPI, rust crates.io);
  any other hint leaves the chain whole, and --registry wins over it. A
  result from one registry is never ambiguous.

Exit codes:

  0  parse-target printed its result; resolve: status == "ok"
  1  status == "fallthrough"
  2  usage error (argparse)
  3  status == "ambiguous"
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import string
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

REGISTRY_TIMEOUT_SECONDS = 10.0
USER_AGENT = "skf-resolve-package/1.0 (+https://github.com/armelhbobdad/bmad-module-skill-forge)"

KINDS = ("github", "package", "registry-page", "other-host", "local-path", "unparsed")
REGISTRIES = ("npm", "pypi", "crates")
STATUSES = ("ok", "ambiguous", "fallthrough")
EXIT_CODES = {"ok": 0, "fallthrough": 1, "ambiguous": 3}
COMMANDS = ("parse-target", "resolve")
LANGUAGE_REGISTRIES = {"javascript": "npm", "typescript": "npm", "js": "npm", "ts": "npm",
                       "python": "pypi", "py": "pypi", "rust": "crates"}
# PyPI project_urls labels that name the repository, in the order they are
# read, as PEP 753 normalizes them; the homepage comes last.
PYPI_SOURCE_LABELS = ("source", "sourcecode", "repository", "github")

# skf-github-probe.py loads this file to read --repo with github_target:
# keep that name and what it takes and returns.

# A github.com URL: scheme URLs (userinfo, and a port or the scp-like `:`
# after the host, allowed), the scp-like ssh form and a URL without a
# scheme. The path is split by _github_location.
_GITHUB_URL_RE = re.compile(
    r"^(?:(?:https?|git|ssh)://(?:[^@/\s]+@)?(?:www\.)?github\.com(?::\d+)?[/:]"
    r"|git@github\.com:"
    r"|(?:www\.)?github\.com/)"
    r"(?P<path>\S*)$",
    re.IGNORECASE,
)
# A GitHub owner or repository name: letters, digits, `-`, `_` and `.`,
# with at least one letter or digit.
_NAME_RE = re.compile(r"^(?=.*[A-Za-z0-9])[A-Za-z0-9_.-]+$")
# `<owner>/<repo>`: a GitHub owner has no dot, so `<host>/<path>` never matches.
_SHORTHAND_RE = re.compile(r"^(?P<owner>[A-Za-z0-9][A-Za-z0-9_-]*)/(?P<repo>[A-Za-z0-9_.-]+)$")
# A version starts with a digit, or with `v` and a digit; npm's dist-tags
# (`latest`, `canary`) start with a letter.
_VERSION_RE = re.compile(r"^[vV]?[0-9][A-Za-z0-9._+-]*$")
_DIST_TAG_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")
_PACKAGE_RE = re.compile(r"^(?:@(?P<scope>[A-Za-z0-9][A-Za-z0-9._-]*)/)?[A-Za-z0-9][A-Za-z0-9._-]*$")
_PYPI_PIN_RE = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?==(?P<version>.*)$")
_SCHEME_RE = re.compile(r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*)://")
_SCP_RE = re.compile(r"^[^@/\s:]+@(?P<host>[^:/\s]+):")
_HOST_RE = re.compile(r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,}(?::\d+)?$")
_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")

_SHORTCUT_HOSTS = {"gitlab:": "gitlab.com", "bitbucket:": "bitbucket.org"}
_PAIRS = {'"': '"', "'": "'", "`": "`", "<": ">"}
_NPM_HOSTS = frozenset({"npmjs.com", "www.npmjs.com", "npmjs.org", "www.npmjs.org"})
_PYPI_HOSTS = frozenset({"pypi.org", "www.pypi.org"})
_CRATES_HOSTS = frozenset({"crates.io", "www.crates.io"})
_REGISTRY_HOSTS = _NPM_HOSTS | _PYPI_HOSTS | _CRATES_HOSTS | {"pypi.python.org"}


# --------------------------------------------------------------------------
# GitHub URLs
# --------------------------------------------------------------------------


def _clean_subdir(value) -> Optional[str]:
    """A repository-relative folder as `a/b`, or None when empty or leaving the repository."""
    if not isinstance(value, str):
        return None
    parts = [p for p in value.replace("\\", "/").split("/") if p and p != "."]
    if not parts or ".." in parts:
        return None
    return "/".join(parts)


def _github_location(text: str) -> Optional[dict]:
    """owner, repo, ref and subdir of a github.com repository URL, else None.

    ref and subdir come from a `/tree/<ref>/<folder>` tail; any other tail,
    a query and a fragment are dropped.
    """
    if not text or not isinstance(text, str):
        return None
    s = text.strip()
    if s[:7].lower() == "github:":  # npm's shortcut: github:<owner>/<repo>
        s = "github.com/" + s[7:]
    if s[:4].lower() == "git+":
        s = s[4:]
    m = _GITHUB_URL_RE.match(s)
    if not m:
        return None
    path = re.split(r"[?#]", m.group("path"), maxsplit=1)[0]
    parts = [urllib.parse.unquote(p) for p in path.split("/") if p]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    if repo.lower().endswith(".git"):
        repo = repo[: -len(".git")]
    if not all(_NAME_RE.fullmatch(p) for p in (owner, repo)) or owner.startswith("-"):
        return None
    ref = subdir = None
    tail = parts[2:]
    if len(tail) >= 2 and tail[0] == "tree":
        ref, subdir = tail[1], _clean_subdir("/".join(tail[2:]))
    return {"owner": owner, "repo": repo, "ref": ref, "subdir": subdir}


def github_target(text: str) -> Optional[dict]:
    """_github_location of a github.com URL or of `<owner>/<repo>`, else None."""
    loc = _github_location(text)
    if loc is None and isinstance(text, str) and _SHORTHAND_RE.fullmatch(text.strip()):
        loc = _github_location(f"github.com/{text.strip()}")
    return loc


def parse_github_url(url: str) -> Optional[tuple[str, str, str]]:
    """Parse a GitHub URL/string into (canonical_url, owner, repo).

    Handles the variants registries actually emit, dotted repository names
    (`vercel/next.js`) included:
      - https://github.com/owner/repo
      - http://github.com/owner/repo
      - github.com/owner/repo
      - git+https://github.com/owner/repo.git
      - git://github.com/owner/repo.git, ssh://git@github.com/owner/repo.git
      - git@github.com:owner/repo.git, ssh://git@github.com:owner/repo.git
      - github:owner/repo (npm shortcut)
      - any of these with a `/tree/<ref>/<folder>` or other path, a query
        or a fragment after the repository
    """
    loc = _github_location(url)
    if loc is None:
        return None
    owner, repo = loc["owner"], loc["repo"]
    return f"https://github.com/{owner}/{repo}", owner, repo


def _github_found(url: str, directory=None) -> Optional[tuple[str, str, str, Optional[str]]]:
    """(canonical_url, owner, repo, source_subdir) of a registry's repository URL, else None."""
    loc = _github_location(url)
    if loc is None:
        return None
    owner, repo = loc["owner"], loc["repo"]
    return f"https://github.com/{owner}/{repo}", owner, repo, _clean_subdir(directory) or loc["subdir"]


# --------------------------------------------------------------------------
# Targets
# --------------------------------------------------------------------------


# Keep identical to _kebab in skf-skill-inventory.py (test/test-skf-resolve-package.py
# pins the copy): the inventory derives a skill's name with it.
def _kebab(segment) -> str:
    """Kebab-case, lowercase a single name segment (the skill-name rule).

    Lowercase, drop a trailing ``.git``, collapse every run of non-alphanumeric
    characters to a single hyphen, and strip leading / trailing hyphens.
    """
    s = str(segment).strip().lower()
    if s.endswith(".git"):
        s = s[:-4]
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _split_at(text: str, word_re: re.Pattern) -> tuple[str, Optional[str]]:
    """(before, after) the last `@` (not a leading one) when word_re matches what follows it, else (text, None)."""
    at = text.rfind("@")
    if at > 0 and word_re.fullmatch(text[at + 1:]):
        return text[:at], text[at + 1:]
    return text, None


def _is_local_path(text: str) -> bool:
    return (text.startswith((".", "/", "\\", "~")) or bool(_DRIVE_RE.match(text))
            or text[:7].lower() == "file://")


def _url_host(text: str) -> Optional[tuple[str, str]]:
    """(host, path) of a URL-like target, else None."""
    m = _SCHEME_RE.match(text)
    if m:
        authority, _, path = text[m.end():].partition("/")
        host = authority.rpartition("@")[2].split(":")[0]
        return (host.lower(), path) if host else None
    m = _SCP_RE.match(text)
    if m:
        return m.group("host").lower(), text[m.end():]
    first, sep, path = text.partition("/")
    if sep and _HOST_RE.fullmatch(first):
        return first.split(":")[0].lower(), path
    return None


def _registry_page(host: str, path: str) -> Optional[tuple[str, str, Optional[str]]]:
    """(registry, package_name, version) of an npm, PyPI or crates.io package page, else None."""
    parts = [urllib.parse.unquote(p) for p in re.split(r"[?#]", path, maxsplit=1)[0].split("/") if p]
    if host in _NPM_HOSTS and len(parts) >= 2 and parts[0] == "package":
        take = 3 if parts[1].startswith("@") else 2
        name, rest = "/".join(parts[1:take]), parts[take:]
        version = rest[1] if len(rest) >= 2 and rest[0] == "v" else None
        registry = "npm"
    elif len(parts) >= 2 and ((host in _PYPI_HOSTS and parts[0] == "project")
                              or (host == "pypi.python.org" and parts[0] == "pypi")):
        name, version, registry = parts[1], (parts[2] if len(parts) >= 3 else None), "pypi"
    elif host in _CRATES_HOSTS and len(parts) >= 2 and parts[0] == "crates":
        name, version, registry = parts[1], (parts[2] if len(parts) >= 3 else None), "crates"
    else:
        return None
    m = _PACKAGE_RE.fullmatch(name)
    if not m or (m.group("scope") and registry != "npm"):
        return None
    if version is not None and not _VERSION_RE.fullmatch(version):
        version = None
    return registry, name, version


def parse_target(text: str) -> dict:
    """Split a quick-skill target into its kind and parts (see the module docstring)."""
    raw = (text or "").strip()
    if len(raw) >= 2 and raw[0] in _PAIRS and raw[-1] == _PAIRS[raw[0]]:
        raw = raw[1:-1].strip()
    out = {"kind": "unparsed", "input": raw, "target_version": None, "dist_tag": None, "owner": None,
           "repo": None, "url": None, "ref": None, "subdir": None, "package_name": None, "registry": None,
           "skill_name": None, "host": None, "path": None}
    if not raw or any(ch.isspace() for ch in raw):
        return out
    if _is_local_path(raw):
        out.update(kind="local-path", path=raw[7:] if raw[:7].lower() == "file://" else raw)
        return out

    pin = _PYPI_PIN_RE.fullmatch(raw)
    if pin:
        if _VERSION_RE.fullmatch(pin.group("version")):
            out.update(kind="package", package_name=pin.group("name"), registry="pypi",
                       target_version=pin.group("version"), skill_name=_kebab(pin.group("name")))
        return out

    body, version = _split_at(raw, _VERSION_RE)
    loc = github_target(body)
    if loc is not None:
        folder = (loc["subdir"] or "").rpartition("/")[2]
        out.update(kind="github", owner=loc["owner"], repo=loc["repo"], ref=loc["ref"], subdir=loc["subdir"],
                   url=f"https://github.com/{loc['owner']}/{loc['repo']}", target_version=version,
                   skill_name=_kebab(folder) or _kebab(loc["repo"]))
        return out

    for prefix, host in _SHORTCUT_HOSTS.items():
        if body[:len(prefix)].lower() == prefix:
            out.update(kind="other-host", host=host, url=body, target_version=version)
            return out
    located = _url_host(body)
    if located is not None:
        host, path = located
        if host in ("github.com", "www.github.com"):
            return out  # a github.com URL that names no repository
        page = _registry_page(host, path)
        if page is not None:
            registry, name, page_version = page
            out.update(kind="registry-page", registry=registry, package_name=name,
                       target_version=version or page_version, skill_name=_kebab(name))
        elif host not in _REGISTRY_HOSTS:  # a registry page that names no package stays unparsed
            out.update(kind="other-host", host=host, url=body, target_version=version)
        return out

    dist_tag = None
    if version is None:  # `next@canary`: an npm dist-tag, which pins no version
        body, dist_tag = _split_at(body, _DIST_TAG_RE)
    m = _PACKAGE_RE.fullmatch(body)
    if m:
        out.update(kind="package", package_name=body, registry="npm" if m.group("scope") else None,
                   target_version=version, dist_tag=dist_tag, skill_name=_kebab(body))
    return out


# --------------------------------------------------------------------------
# Registries
# --------------------------------------------------------------------------


def _http_get_json(url: str, timeout: float) -> tuple[Optional[dict], str]:
    """Fetch JSON. Returns (payload_or_None, outcome).

    Outcome values:
      "ok"       valid JSON object returned
      "404"      HTTP 404 (package does not exist on this registry)
      "timeout"  socket / urlopen timed out
      "error"    any other transport / parse error
    """
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            if isinstance(payload, dict):
                return payload, "ok"
            return None, "error"
    except urllib.error.HTTPError as e:
        return None, "404" if e.code == 404 else "error"
    except urllib.error.URLError as e:
        if isinstance(getattr(e, "reason", None), (socket.timeout, TimeoutError)):
            return None, "timeout"
        return None, "error"
    except (TimeoutError, socket.timeout):
        return None, "timeout"
    except (ValueError, json.JSONDecodeError):
        return None, "error"


# Each try_* returns ((canonical_url, owner, repo, source_subdir) or None, outcome).
# A folder comes only from a repository field, never from a homepage.


def try_npm(package_name: str, timeout: float) -> tuple[Optional[tuple[str, str, str, Optional[str]]], str]:
    """Try the npm registry. Returns (found_or_None, outcome)."""
    encoded = urllib.parse.quote(package_name, safe="@")
    url = f"https://registry.npmjs.org/{encoded}"
    payload, outcome = _http_get_json(url, timeout)
    if payload is None:
        return None, outcome
    candidates: list[tuple[str, Optional[str], bool]] = []  # (url, directory, repository field)
    repo = payload.get("repository")
    if isinstance(repo, dict) and isinstance(repo.get("url"), str):
        candidates.append((repo["url"], repo.get("directory"), True))
    elif isinstance(repo, str):
        candidates.append((repo, None, True))
    homepage = payload.get("homepage")
    if isinstance(homepage, str):
        candidates.append((homepage, None, False))
    for c, directory, is_repository in candidates:
        found = _github_found(c, directory)
        if found:
            return (found if is_repository else (*found[:3], None)), "ok"
    return None, "no-github-link"


def _pypi_label(key: str) -> str:
    """A project_urls label as PEP 753 normalizes it: punctuation and whitespace removed, lower case."""
    return "".join(ch for ch in key if ch not in string.punctuation and not ch.isspace()).lower()


def try_pypi(package_name: str, timeout: float) -> tuple[Optional[tuple[str, str, str, Optional[str]]], str]:
    """Try the PyPI registry. Returns (found_or_None, outcome)."""
    encoded = urllib.parse.quote(package_name, safe="")
    url = f"https://pypi.org/pypi/{encoded}/json"
    payload, outcome = _http_get_json(url, timeout)
    if payload is None:
        return None, outcome
    info = payload.get("info") or {}
    candidates: list[tuple[str, bool]] = []  # (url, repository field)
    project_urls = info.get("project_urls") or {}
    labels: dict[str, str] = {}  # normalized label -> the first URL under it
    if isinstance(project_urls, dict):
        for key, v in project_urls.items():
            if isinstance(key, str) and isinstance(v, str):
                labels.setdefault(_pypi_label(key), v)
    for label in (*PYPI_SOURCE_LABELS, "homepage"):
        if label in labels:
            candidates.append((labels[label], label != "homepage"))
    home_page = info.get("home_page")
    if isinstance(home_page, str):
        candidates.append((home_page, False))
    for c, is_repository in candidates:
        found = _github_found(c)
        if found:
            return (found if is_repository else (*found[:3], None)), "ok"
    return None, "no-github-link"


def try_crates(package_name: str, timeout: float) -> tuple[Optional[tuple[str, str, str, Optional[str]]], str]:
    """Try the crates.io registry. Returns (found_or_None, outcome)."""
    encoded = urllib.parse.quote(package_name, safe="")
    url = f"https://crates.io/api/v1/crates/{encoded}"
    payload, outcome = _http_get_json(url, timeout)
    if payload is None:
        return None, outcome
    crate = payload.get("crate") or {}
    for key in ("repository", "homepage"):
        v = crate.get(key)
        if isinstance(v, str):
            found = _github_found(v)
            if found:
                return (found if key == "repository" else (*found[:3], None)), "ok"
    return None, "no-github-link"


_RESOLVER_NAMES: tuple[tuple[str, str], ...] = (
    ("npm", "try_npm"),
    ("pypi", "try_pypi"),
    ("crates", "try_crates"),
)


def resolve_package(package_name: str, timeout: float = REGISTRY_TIMEOUT_SECONDS,
                    registry: Optional[str] = None, language: Optional[str] = None) -> dict:
    """Walk the registry chain, or only `registry` or the language's registry (see the module docstring)."""
    registry = registry or LANGUAGE_REGISTRIES.get((language or "").strip().lower())
    registries_tried: list[str] = []
    outcomes: dict[str, str] = {}

    def found_in() -> list[str]:
        return [n for n in registries_tried if outcomes[n] not in ("404", "timeout")]

    # Dynamic lookup so test code can monkeypatch try_npm / try_pypi / try_crates
    # without re-binding entries in a module-level tuple of function refs.
    for name, fn_name in _RESOLVER_NAMES:
        if registry is not None and name != registry:
            continue
        registries_tried.append(name)
        fn = globals()[fn_name]
        result, outcome = fn(package_name, timeout)
        outcomes[name] = outcome
        if result is not None:
            url, owner, repo, subdir = result
            return {
                "status": "ambiguous" if len(found_in()) > 1 else "ok",
                "package_name": package_name,
                "resolved_url": url,
                "repo_owner": owner,
                "repo_name": repo,
                "skill_name": _kebab(package_name),
                "registry_used": name,
                "source_subdir": subdir,
                "name_found_in": found_in(),
                "registries_tried": registries_tried,
                "registry_outcomes": outcomes,
            }

    return {
        "status": "fallthrough",
        "package_name": package_name,
        "name_found_in": found_in(),
        "registries_tried": registries_tried,
        "registry_outcomes": outcomes,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _read_stdin() -> str:
    """stdin as UTF-8, whatever the locale's code page (cp1252 on Windows)."""
    stream = getattr(sys.stdin, "buffer", None)
    if stream is not None:
        return stream.read().decode("utf-8", errors="replace")
    return sys.stdin.read()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-resolve-package",
        description="Read a quick-skill target, or resolve a package name to a GitHub repository "
                    "via npm/PyPI/crates.io.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_parse = sub.add_parser("parse-target", help="split a target into its kind, name, version and repository")
    p_parse.add_argument("--target", help="the target as typed (default: read from stdin)")
    p_resolve = sub.add_parser("resolve", help="resolve a package name to its GitHub repository")
    p_resolve.add_argument(
        "package_name",
        help="Package name to resolve (e.g., lodash, @tanstack/react-query, requests, serde).",
    )
    p_resolve.add_argument("--registry", choices=REGISTRIES, help="query only this registry")
    p_resolve.add_argument("--language",
                           help="a language hint: javascript, typescript, python or rust queries only its "
                                "registry (--registry wins); any other language queries them all")
    p_resolve.add_argument(
        "--timeout",
        type=float,
        default=REGISTRY_TIMEOUT_SECONDS,
        help=f"Per-registry timeout in seconds (default: {REGISTRY_TIMEOUT_SECONDS}).",
    )
    return parser


def main(argv: list[str]) -> int:
    if argv and argv[0] not in COMMANDS and not argv[0].startswith("-"):
        argv = ["resolve", *argv]  # the form before the subcommands: <package_name> [--timeout N]
    args = _build_parser().parse_args(argv)
    if args.cmd == "parse-target":
        text = args.target if args.target is not None else _read_stdin()
        print(json.dumps(parse_target(text), indent=2))
        return 0
    result = resolve_package(args.package_name, timeout=args.timeout, registry=args.registry,
                             language=args.language)
    print(json.dumps(result, indent=2))
    return EXIT_CODES[result["status"]]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
