#!/usr/bin/env python3
"""Tests for skf-resolve-package.py.

Network is mocked at the _http_get_json layer so the tests stay offline
and deterministic. The script's own _http_get_json error-classification
is not exercised here (it is thin glue around urllib + json); tests
focus on the GitHub-URL parser, the target parser, registry-payload
parsers, and the overall resolve-package fallback behaviour.

Every case #582 reproduced has a regression test: the dotted repository
names of next.js, three.js and socket.io (which resolved to an unrelated
PyPI project or fell through), a /tree/main/pkg URL (named after its last
path part) and requests==2.31 (a pin no registry knew). So do the cases
review found: crates.io's /versions tab read as a version, npm dist-tags
read as versions, lower-case PyPI project_urls labels, and skill names
that the frontmatter validator refuses (next.js) or that two packages
share (@babel/core and @babel/parser both live in babel/babel).
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent.parent / "src" / "shared" / "scripts"
SCRIPT = SCRIPTS / "skf-resolve-package.py"
spec = importlib.util.spec_from_file_location("skf_resolve_package", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestParseGithubUrl:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("https://github.com/lodash/lodash", ("https://github.com/lodash/lodash", "lodash", "lodash")),
            ("http://github.com/lodash/lodash", ("https://github.com/lodash/lodash", "lodash", "lodash")),
            ("github.com/lodash/lodash", ("https://github.com/lodash/lodash", "lodash", "lodash")),
            (
                "git+https://github.com/lodash/lodash.git",
                ("https://github.com/lodash/lodash", "lodash", "lodash"),
            ),
            (
                "git@github.com:lodash/lodash.git",
                ("https://github.com/lodash/lodash", "lodash", "lodash"),
            ),
            ("github:lodash/lodash", ("https://github.com/lodash/lodash", "lodash", "lodash")),
            ("https://github.com/scope-name/pkg.git", ("https://github.com/scope-name/pkg", "scope-name", "pkg")),
            ("https://github.com/owner/repo/", ("https://github.com/owner/repo", "owner", "repo")),
            # #582: the repository segment keeps its dots.
            (
                "git+https://github.com/vercel/next.js.git",
                ("https://github.com/vercel/next.js", "vercel", "next.js"),
            ),
            ("https://github.com/mrdoob/three.js", ("https://github.com/mrdoob/three.js", "mrdoob", "three.js")),
            (
                "https://github.com/socketio/socket.io",
                ("https://github.com/socketio/socket.io", "socketio", "socket.io"),
            ),
            ("git@github.com:chartjs/Chart.js.git", ("https://github.com/chartjs/Chart.js", "chartjs", "Chart.js")),
            # #582: a /tree/<ref>/<folder> tail names the same repository.
            ("https://github.com/org/repo/tree/main/pkg", ("https://github.com/org/repo", "org", "repo")),
            ("https://github.com/org/repo/tree/v2.0.0", ("https://github.com/org/repo", "org", "repo")),
            # What registries also write: other schemes, a fragment, a query, www.
            ("git://github.com/substack/node-optimist.git",
             ("https://github.com/substack/node-optimist", "substack", "node-optimist")),
            ("git+ssh://git@github.com/owner/repo.git", ("https://github.com/owner/repo", "owner", "repo")),
            ("ssh://git@github.com:22/owner/repo.git", ("https://github.com/owner/repo", "owner", "repo")),
            # The scp-like `:` after a scheme, which skf-github-probe.py also reads.
            ("git+ssh://git@github.com:owner/repo.git", ("https://github.com/owner/repo", "owner", "repo")),
            ("ssh://git@github.com:owner/repo.git", ("https://github.com/owner/repo", "owner", "repo")),
            ("https://github.com/lodash/lodash#readme", ("https://github.com/lodash/lodash", "lodash", "lodash")),
            ("https://github.com/owner/repo?tab=readme", ("https://github.com/owner/repo", "owner", "repo")),
            ("https://www.github.com/owner/repo", ("https://github.com/owner/repo", "owner", "repo")),
        ],
    )
    def test_recognized_variants(self, raw, expected):
        assert mod.parse_github_url(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "not-a-url",
            "https://example.com/foo",
            "https://gitlab.com/owner/repo",
            "https://bitbucket.org/owner/repo",
            "ftp://github.com/owner/repo",  # only http/https, git and ssh
            "https://github.com/owner",  # an owner, no repository
            "https://github.com/",
            "https://github.com/-owner/repo",
            "https://github.com/owner/..",
            "https://github.com/owner/_",  # no letter or digit to name a skill after
            "https://github.com.evil.example/owner/repo",
        ],
    )
    def test_rejects_non_github(self, raw):
        assert mod.parse_github_url(raw) is None

    def test_handles_none_and_non_string(self):
        assert mod.parse_github_url(None) is None  # type: ignore[arg-type]
        assert mod.parse_github_url(42) is None  # type: ignore[arg-type]


NONE = dict.fromkeys(("target_version", "dist_tag", "owner", "repo", "url", "ref", "subdir", "package_name",
                      "registry", "skill_name", "host", "path"))


def _parsed(kind: str, **fields) -> dict:
    return {"kind": kind, **NONE, **fields}


def _package(name: str, skill: str, **fields) -> dict:
    return _parsed("package", package_name=name, skill_name=skill, **fields)


def _github(owner: str, repo: str, skill: str, **fields) -> dict:
    return _parsed("github", owner=owner, repo=repo, url=f"https://github.com/{owner}/{repo}", skill_name=skill,
                   **fields)


def _page(registry: str, name: str, skill: str, **fields) -> dict:
    return _parsed("registry-page", registry=registry, package_name=name, skill_name=skill, **fields)


class TestParseTarget:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            # The examples resolve-target.md and batch-mode.md list.
            ("cocoindex", _package("cocoindex", "cocoindex")),
            ("@tanstack/react-query", _package("@tanstack/react-query", "tanstack-react-query", registry="npm")),
            ("lodash", _package("lodash", "lodash")),
            ("@vercel/og", _package("@vercel/og", "vercel-og", registry="npm")),
            ("@scope/name", _package("@scope/name", "scope-name", registry="npm")),
            ("cognee@0.5.0", _package("cognee", "cognee", target_version="0.5.0")),
            ("requests==2.31", _package("requests", "requests", registry="pypi", target_version="2.31")),
            ("requests==2.31.0", _package("requests", "requests", registry="pypi", target_version="2.31.0")),
            ("https://github.com/tursodatabase/limbo", _github("tursodatabase", "limbo", "limbo")),
            ("https://github.com/lodash/lodash", _github("lodash", "lodash", "lodash")),
            ("https://github.com/foo/bar@2.1.0-beta", _github("foo", "bar", "bar", target_version="2.1.0-beta")),
            # Scoped names with a version, and PyPI extras.
            ("@scope/name@1.2.3", _package("@scope/name", "scope-name", registry="npm", target_version="1.2.3")),
            ("requests[socks]==2.31", _package("requests", "requests", registry="pypi", target_version="2.31")),
            ("socket.io", _package("socket.io", "socket-io")),
            ("zope.interface", _package("zope.interface", "zope-interface")),
            # npm dist-tags pin no version; `v` and a digit is a version.
            ("lodash@latest", _package("lodash", "lodash", dist_tag="latest")),
            ("next@canary", _package("next", "next", dist_tag="canary")),
            ("@scope/name@beta", _package("@scope/name", "scope-name", registry="npm", dist_tag="beta")),
            ("lodash@v2", _package("lodash", "lodash", target_version="v2")),
            # Dotted repositories, .git and /tree/ URLs.
            ("https://github.com/vercel/next.js", _github("vercel", "next.js", "next-js")),
            ("git+https://github.com/mrdoob/three.js.git", _github("mrdoob", "three.js", "three-js")),
            ("github.com/socketio/socket.io", _github("socketio", "socket.io", "socket-io")),
            ("https://github.com/org/repo/tree/main/pkg", _github("org", "repo", "pkg", ref="main", subdir="pkg")),
            ("https://github.com/org/repo/tree/v1.0.0/packages/core/",
             _github("org", "repo", "core", ref="v1.0.0", subdir="packages/core")),
            ("https://github.com/org/repo/tree/main", _github("org", "repo", "repo", ref="main")),
            ("https://github.com/org/repo/blob/main/README.md", _github("org", "repo", "repo")),
            ("git@github.com:vercel/next.js.git", _github("vercel", "next.js", "next-js")),
            ("git@github.com:vercel/next.js.git@14.2.3",
             _github("vercel", "next.js", "next-js", target_version="14.2.3")),
            ("github:owner/repo", _github("owner", "repo", "repo")),
            ("vercel/next.js", _github("vercel", "next.js", "next-js")),
            ("owner/repo@v2", _github("owner", "repo", "repo", target_version="v2")),
            ("https://github.com/microsoft/TypeScript", _github("microsoft", "TypeScript", "typescript")),
            ("https://github.com/run-llama/llama_index", _github("run-llama", "llama_index", "llama-index")),
            # Registry pages: that registry only.
            ("https://www.npmjs.com/package/lodash", _page("npm", "lodash", "lodash")),
            ("https://www.npmjs.com/package/@tanstack/react-query/v/5.59.0",
             _page("npm", "@tanstack/react-query", "tanstack-react-query", target_version="5.59.0")),
            ("npmjs.com/package/next", _page("npm", "next", "next")),
            ("https://pypi.org/project/requests/", _page("pypi", "requests", "requests")),
            ("https://pypi.org/project/requests/2.31.0/",
             _page("pypi", "requests", "requests", target_version="2.31.0")),
            ("https://pypi.python.org/pypi/Django", _page("pypi", "Django", "django")),
            ("https://crates.io/crates/serde", _page("crates", "serde", "serde")),
            ("https://crates.io/crates/tokio/1.40.0", _page("crates", "tokio", "tokio", target_version="1.40.0")),
            # A page tab is no version.
            ("https://crates.io/crates/serde/versions", _page("crates", "serde", "serde")),
            ("https://crates.io/crates/serde/reverse_dependencies", _page("crates", "serde", "serde")),
            # Other hosts.
            ("https://gitlab.com/owner/repo",
             _parsed("other-host", host="gitlab.com", url="https://gitlab.com/owner/repo")),
            ("gitlab.com/owner/repo", _parsed("other-host", host="gitlab.com", url="gitlab.com/owner/repo")),
            ("git@gitlab.com:owner/repo.git",
             _parsed("other-host", host="gitlab.com", url="git@gitlab.com:owner/repo.git")),
            ("https://bitbucket.org/owner/repo@1.0",
             _parsed("other-host", host="bitbucket.org", url="https://bitbucket.org/owner/repo", target_version="1.0")),
            ("bitbucket:owner/repo", _parsed("other-host", host="bitbucket.org", url="bitbucket:owner/repo")),
            ("https://codeberg.org/forgejo/forgejo",
             _parsed("other-host", host="codeberg.org", url="https://codeberg.org/forgejo/forgejo")),
            # Local paths.
            ("./packages/my-lib", _parsed("local-path", path="./packages/my-lib")),
            ("../lib", _parsed("local-path", path="../lib")),
            (".", _parsed("local-path", path=".")),
            ("/home/me/lib", _parsed("local-path", path="/home/me/lib")),
            ("~/src/lib", _parsed("local-path", path="~/src/lib")),
            ("C:\\src\\lib", _parsed("local-path", path="C:\\src\\lib")),
            ("D:/src/lib", _parsed("local-path", path="D:/src/lib")),
            ("\\\\server\\share\\lib", _parsed("local-path", path="\\\\server\\share\\lib")),
            ("file:///home/me/lib", _parsed("local-path", path="/home/me/lib")),
        ],
        ids=lambda value: value if isinstance(value, str) else None,
    )
    def test_shapes(self, raw, expected):
        assert mod.parse_target(raw) == {**expected, "input": raw}

    @pytest.mark.parametrize(
        "raw",
        [
            "I want a skill that helps with onboarding",
            "build me a brainstorming workflow",
            "",
            "   ",
            "lodash@^4.17.0",
            "requests>=2.31",
            "requests==",
            "requests==latest",
            "@scope",
            "@scope@beta",
            "owner/repo/extra",
            "owner/repo@main",
            "https://github.com",
            "https://github.com/owner",
            "https://github.com/owner/repo@main",
            "https://pypi.org/search/?q=requests",
            "https://www.npmjs.com/settings/me",
            "ftp://github.com/owner/repo",
        ],
    )
    def test_anything_else_is_unparsed(self, raw):
        assert mod.parse_target(raw) == _parsed("unparsed") | {"input": raw.strip()}

    @pytest.mark.parametrize(
        "raw, inner",
        [('"lodash"', "lodash"), ("'cognee@0.5.0'", "cognee@0.5.0"), ("`@vercel/og`", "@vercel/og"),
         ("<https://github.com/foo/bar>", "https://github.com/foo/bar"), ("  lodash\n", "lodash")],
    )
    def test_one_pair_of_quotes_or_brackets_is_dropped(self, raw, inner):
        assert mod.parse_target(raw) == {**mod.parse_target(inner), "input": inner}

    def test_every_key_is_always_present(self):
        keys = set(_parsed("unparsed")) | {"input"}
        for raw in ("lodash", "next@canary", "https://github.com/o/r", "./x", "https://gitlab.com/o/r",
                    "a sentence", ""):
            assert set(mod.parse_target(raw)) == keys
        assert set(mod.KINDS) == {"github", "package", "registry-page", "other-host", "local-path", "unparsed"}


class TestSkillName:
    """The name quick-skill writes a skill under must pass skf-validate-frontmatter.py
    (lower-case letters, digits and hyphens), and two packages of one repository
    must not share it."""

    def test_the_rule_is_the_inventorys(self):
        spec = importlib.util.spec_from_file_location("skf_skill_inventory_for_resolver",
                                                      SCRIPTS / "skf-skill-inventory.py")
        inventory = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(inventory)
        for name in ("next.js", "Chart.js", "@babel/core", "llama_index", "TypeScript", "repo.git", "--x--",
                     "socket.io", "zope.interface", "a..b", "_"):
            assert mod._kebab(name) == inventory._kebab(name), name

    @pytest.mark.parametrize("raw", [
        "next", "@babel/core", "https://github.com/vercel/next.js", "git@github.com:chartjs/Chart.js.git",
        "https://github.com/org/Repo/tree/main/packages/My_Pkg", "https://pypi.org/project/Flask-SQLAlchemy/",
        "zope.interface==6.0", "socket.io", "https://github.com/run-llama/llama_index",
        "https://github.com/org/repo/tree/main/_",
    ])
    def test_every_skill_name_passes_the_frontmatter_validator(self, raw):
        # Step 5 writes the skill folder under this name and validates frontmatter
        # `name` against it with skf-validate-frontmatter.py --skill-dir-name.
        spec = importlib.util.spec_from_file_location("skf_validate_frontmatter_for_resolver",
                                                      SCRIPTS / "skf-validate-frontmatter.py")
        validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validator)
        name = mod.parse_target(raw)["skill_name"]
        assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name), name
        assert validator._validate_name(name, name) == [], name

    def test_two_packages_of_one_repository_get_two_names(self, monkeypatch):
        _registries(monkeypatch)
        core, parser = mod.resolve_package("@babel/core"), mod.resolve_package("@babel/parser")
        assert core["resolved_url"] == parser["resolved_url"] == "https://github.com/babel/babel"
        assert core["repo_name"] == parser["repo_name"] == "babel"
        assert (core["skill_name"], parser["skill_name"]) == ("babel-core", "babel-parser")
        assert (core["source_subdir"], parser["source_subdir"]) == ("packages/babel-core", "packages/babel-parser")
        assert mod.parse_target("@babel/core")["skill_name"] == core["skill_name"]

    def test_a_package_is_named_after_itself_not_its_repository(self, monkeypatch):
        _registries(monkeypatch)
        result = mod.resolve_package("next")
        assert (result["repo_name"], result["skill_name"]) == ("next.js", "next")
        assert mod.parse_target("https://github.com/vercel/next.js")["skill_name"] == "next-js"


class TestRegistryPayloadParsers:
    """Each try_* function calls _http_get_json then extracts a GitHub URL.
    Tests monkeypatch the HTTP fetch and assert the correct candidate-field
    priority, the package folder and outcome reporting.
    """

    def _patch_http(self, monkeypatch, payload, outcome="ok"):
        monkeypatch.setattr(mod, "_http_get_json", lambda url, timeout: (payload, outcome))

    def test_npm_repository_object(self, monkeypatch):
        self._patch_http(monkeypatch, {"repository": {"url": "git+https://github.com/lodash/lodash.git"}})
        result, outcome = mod.try_npm("lodash", 5)
        assert result == ("https://github.com/lodash/lodash", "lodash", "lodash", None)
        assert outcome == "ok"

    def test_npm_repository_string_shortcut(self, monkeypatch):
        self._patch_http(monkeypatch, {"repository": "github:lodash/lodash"})
        result, outcome = mod.try_npm("lodash", 5)
        assert result == ("https://github.com/lodash/lodash", "lodash", "lodash", None)
        assert outcome == "ok"

    def test_npm_falls_back_to_homepage(self, monkeypatch):
        self._patch_http(
            monkeypatch,
            {"repository": "https://example.com/not-github", "homepage": "https://github.com/owner/repo"},
        )
        result, _ = mod.try_npm("foo", 5)
        assert result == ("https://github.com/owner/repo", "owner", "repo", None)

    def test_npm_no_github_link(self, monkeypatch):
        self._patch_http(monkeypatch, {"repository": "https://example.com/x", "homepage": "https://example.com/y"})
        result, outcome = mod.try_npm("foo", 5)
        assert result is None
        assert outcome == "no-github-link"

    def test_npm_404(self, monkeypatch):
        self._patch_http(monkeypatch, None, outcome="404")
        result, outcome = mod.try_npm("foo", 5)
        assert result is None
        assert outcome == "404"

    def test_npm_repository_directory_is_the_source_subdir(self, monkeypatch):
        self._patch_http(monkeypatch, {"repository": {
            "type": "git", "url": "git+https://github.com/TanStack/query.git", "directory": "packages/react-query"}})
        result, _ = mod.try_npm("@tanstack/react-query", 5)
        assert result == ("https://github.com/TanStack/query", "TanStack", "query", "packages/react-query")

    @pytest.mark.parametrize("directory, subdir", [
        ("./packages/core/", "packages/core"), ("packages\\core", "packages/core"), ("", None), (".", None),
        ("../outside", None), (42, None)])
    def test_npm_directory_is_cleaned(self, monkeypatch, directory, subdir):
        self._patch_http(monkeypatch, {"repository": {"url": "https://github.com/o/r", "directory": directory}})
        result, _ = mod.try_npm("pkg", 5)
        assert result == ("https://github.com/o/r", "o", "r", subdir)

    def test_npm_tree_url_gives_the_folder_when_no_directory(self, monkeypatch):
        self._patch_http(monkeypatch, {"repository": {"url": "https://github.com/o/r/tree/main/packages/pkg"}})
        result, _ = mod.try_npm("pkg", 5)
        assert result == ("https://github.com/o/r", "o", "r", "packages/pkg")

    def test_npm_homepage_never_gives_a_folder(self, monkeypatch):
        self._patch_http(monkeypatch, {"repository": "https://example.com/x",
                                       "homepage": "https://github.com/o/r/tree/main/docs#readme"})
        result, _ = mod.try_npm("pkg", 5)
        assert result == ("https://github.com/o/r", "o", "r", None)

    def test_pypi_project_urls_priority(self, monkeypatch):
        self._patch_http(
            monkeypatch,
            {
                "info": {
                    "project_urls": {
                        "Homepage": "https://example.com/docs",
                        "Source": "https://github.com/psf/requests",
                        "Repository": "https://github.com/psf/requests-mirror",
                    },
                    "home_page": "https://example.com/old",
                },
            },
        )
        result, _ = mod.try_pypi("requests", 5)
        assert result == ("https://github.com/psf/requests", "psf", "requests", None)

    def test_pypi_falls_back_to_home_page(self, monkeypatch):
        self._patch_http(
            monkeypatch,
            {
                "info": {
                    "project_urls": {"Documentation": "https://example.com/docs"},
                    "home_page": "https://github.com/owner/repo",
                },
            },
        )
        result, _ = mod.try_pypi("foo", 5)
        assert result == ("https://github.com/owner/repo", "owner", "repo", None)

    def test_pypi_no_github_link(self, monkeypatch):
        self._patch_http(
            monkeypatch,
            {"info": {"project_urls": {"Homepage": "https://example.com/x"}, "home_page": "https://example.com/y"}},
        )
        result, outcome = mod.try_pypi("foo", 5)
        assert result is None
        assert outcome == "no-github-link"

    def test_pypi_source_tree_url_gives_the_folder(self, monkeypatch):
        self._patch_http(monkeypatch, {"info": {"project_urls": {
            "Source": "https://github.com/apache/arrow/tree/main/python"}}})
        result, _ = mod.try_pypi("pyarrow", 5)
        assert result == ("https://github.com/apache/arrow", "apache", "arrow", "python")

    # Live PyPI answers (trimmed): current metadata writes the labels in lower
    # case, and a homepage may come first and be a GitHub URL too.
    @pytest.mark.parametrize("name, project_urls, url", [
        ("numpy", {"documentation": "https://numpy.org/doc/", "homepage": "https://numpy.org",
                   "source": "https://github.com/numpy/numpy", "tracker": "https://github.com/numpy/numpy/issues"},
         "https://github.com/numpy/numpy"),
        ("cryptography", {"documentation": "https://cryptography.io/",
                          "homepage": "https://github.com/pyca/cryptography",
                          "issues": "https://github.com/pyca/cryptography/issues",
                          "source": "https://github.com/pyca/cryptography/"},
         "https://github.com/pyca/cryptography"),
        ("pandas", {"homepage": "https://pandas.pydata.org", "repository": "https://github.com/pandas-dev/pandas"},
         "https://github.com/pandas-dev/pandas"),
        ("flask-sqlalchemy", {"Source Code": "https://github.com/pallets-eco/flask-sqlalchemy/"},
         "https://github.com/pallets-eco/flask-sqlalchemy"),
        ("x", {"Source_Code": "https://github.com/o/x"}, "https://github.com/o/x"),
        # A repository label wins over a homepage listed before it.
        ("y", {"Homepage": "https://github.com/o/y-docs", "GitHub": "https://github.com/o/y"},
         "https://github.com/o/y"),
    ])
    def test_pypi_labels_in_any_letter_case(self, monkeypatch, name, project_urls, url):
        self._patch_http(monkeypatch, {"info": {"project_urls": project_urls, "home_page": None}})
        result, outcome = mod.try_pypi(name, 5)
        assert (result[0], result[3], outcome) == (url, None, "ok")

    def test_pypi_label_normalization(self):
        assert [mod._pypi_label(k) for k in ("Source Code", "source-code", "SOURCE_CODE", " Repository ")] == [
            "sourcecode", "sourcecode", "sourcecode", "repository"]

    def test_crates_repository(self, monkeypatch):
        self._patch_http(monkeypatch, {"crate": {"repository": "https://github.com/serde-rs/serde"}})
        result, _ = mod.try_crates("serde", 5)
        assert result == ("https://github.com/serde-rs/serde", "serde-rs", "serde", None)

    def test_crates_falls_back_to_homepage(self, monkeypatch):
        self._patch_http(monkeypatch, {"crate": {"homepage": "https://github.com/owner/repo"}})
        result, _ = mod.try_crates("foo", 5)
        assert result == ("https://github.com/owner/repo", "owner", "repo", None)


# The npm and PyPI answers #582 reproduced, trimmed to the fields the
# resolver reads. Before the fix npm's dotted repository URLs did not parse,
# so `next` and `three` resolved to these unrelated PyPI projects. The two
# babel packages share one repository, each in its own folder.
REGISTRY_ANSWERS = {
    "https://registry.npmjs.org/next": {"repository": {
        "type": "git", "url": "git+https://github.com/vercel/next.js.git"}, "homepage": "https://nextjs.org"},
    "https://registry.npmjs.org/three": {"repository": {
        "type": "git", "url": "git+https://github.com/mrdoob/three.js.git"}, "homepage": "https://threejs.org/"},
    "https://registry.npmjs.org/socket.io": {
        "repository": {"type": "git", "url": "git+https://github.com/socketio/socket.io.git"},
        "homepage": "https://github.com/socketio/socket.io/tree/main/packages/socket.io#readme"},
    "https://pypi.org/pypi/next/json": {
        "info": {"project_urls": {"Homepage": "https://github.com/dheerajmpai/saenews"}}},
    "https://pypi.org/pypi/three/json": {"info": {"home_page": "https://github.com/codeforamerica/three"}},
    "https://pypi.org/pypi/requests/json": {"info": {"project_urls": {"Source": "https://github.com/psf/requests"}}},
    "https://registry.npmjs.org/@babel%2Fcore": {"repository": {
        "url": "https://github.com/babel/babel.git", "type": "git", "directory": "packages/babel-core"}},
    "https://registry.npmjs.org/@babel%2Fparser": {"repository": {
        "url": "https://github.com/babel/babel.git", "type": "git", "directory": "packages/babel-parser"}},
}


def _registries(monkeypatch, answers=REGISTRY_ANSWERS, seen=None):
    def fake(url, timeout):
        if seen is not None:
            seen.append(url)
        return (answers[url], "ok") if url in answers else (None, "404")

    monkeypatch.setattr(mod, "_http_get_json", fake)


class TestReproducedCases:
    """#582's reproduced resolutions, end to end through the registry parsers."""

    @pytest.mark.parametrize("name, url, skill", [
        ("next", "https://github.com/vercel/next.js", "next"),
        ("three", "https://github.com/mrdoob/three.js", "three"),
        ("socket.io", "https://github.com/socketio/socket.io", "socket-io"),
    ])
    def test_dotted_repositories_resolve_on_npm(self, monkeypatch, name, url, skill):
        seen: list[str] = []
        _registries(monkeypatch, seen=seen)
        result = mod.resolve_package(name)
        assert result["status"] == "ok"
        assert result["registry_used"] == "npm"
        assert result["resolved_url"] == url
        assert result["repo_name"] == url.rsplit("/", 1)[1]
        assert result["skill_name"] == skill
        assert result["source_subdir"] is None  # none of the three declares a folder
        assert seen == [f"https://registry.npmjs.org/{name}"]

    def test_the_pre_fix_next_resolution_is_ambiguous(self, monkeypatch):
        # npm's answer without a GitHub link (what the old regex saw) no
        # longer lets PyPI's unrelated `next` through silently.
        answers = {**REGISTRY_ANSWERS, "https://registry.npmjs.org/next": {"homepage": "https://nextjs.org"}}
        _registries(monkeypatch, answers)
        result = mod.resolve_package("next")
        assert result["status"] == "ambiguous"
        assert result["resolved_url"] == "https://github.com/dheerajmpai/saenews"
        assert result["registry_used"] == "pypi"
        assert result["name_found_in"] == ["npm", "pypi"]
        assert result["registry_outcomes"] == {"npm": "no-github-link", "pypi": "ok"}

    def test_a_pypi_pin_resolves_on_pypi_only(self, monkeypatch):
        parsed = mod.parse_target("requests==2.31")
        assert (parsed["kind"], parsed["package_name"], parsed["target_version"], parsed["registry"]) == (
            "package", "requests", "2.31", "pypi")
        seen: list[str] = []
        answers = {**REGISTRY_ANSWERS,  # npm has an unrelated `requests` too
                   "https://registry.npmjs.org/requests": {
                       "repository": "git+https://github.com/unshiftio/requests.git"}}
        _registries(monkeypatch, answers, seen)
        result = mod.resolve_package(parsed["package_name"], registry=parsed["registry"])
        assert result["status"] == "ok"
        assert result["resolved_url"] == "https://github.com/psf/requests"
        assert result["registries_tried"] == ["pypi"]
        assert seen == ["https://pypi.org/pypi/requests/json"]

    def test_a_tree_url_names_the_repository_not_its_folder(self):
        parsed = mod.parse_target("https://github.com/org/repo/tree/main/pkg")
        assert (parsed["repo"], parsed["ref"], parsed["subdir"]) == ("repo", "main", "pkg")


class TestResolvePackage:
    def test_first_registry_wins(self, monkeypatch):
        def fake_npm(name, t):
            return ("https://github.com/lodash/lodash", "lodash", "lodash", None), "ok"

        def fake_pypi(name, t):
            raise AssertionError("pypi must not be called once npm resolved")

        monkeypatch.setattr(mod, "try_npm", fake_npm)
        monkeypatch.setattr(mod, "try_pypi", fake_pypi)
        result = mod.resolve_package("lodash")
        assert result["status"] == "ok"
        assert result["registry_used"] == "npm"
        assert result["registries_tried"] == ["npm"]
        assert result["registry_outcomes"] == {"npm": "ok"}
        assert result["name_found_in"] == ["npm"]
        assert result["source_subdir"] is None

    def test_falls_through_to_pypi(self, monkeypatch):
        monkeypatch.setattr(mod, "try_npm", lambda n, t: (None, "404"))
        monkeypatch.setattr(
            mod, "try_pypi", lambda n, t: (("https://github.com/psf/requests", "psf", "requests", None), "ok")
        )
        result = mod.resolve_package("requests")
        assert result["status"] == "ok"
        assert result["registry_used"] == "pypi"
        assert result["registries_tried"] == ["npm", "pypi"]
        assert result["registry_outcomes"] == {"npm": "404", "pypi": "ok"}
        assert result["name_found_in"] == ["pypi"]

    def test_falls_through_all_registries(self, monkeypatch):
        monkeypatch.setattr(mod, "try_npm", lambda n, t: (None, "404"))
        monkeypatch.setattr(mod, "try_pypi", lambda n, t: (None, "404"))
        monkeypatch.setattr(mod, "try_crates", lambda n, t: (None, "404"))
        result = mod.resolve_package("nonexistent")
        assert result["status"] == "fallthrough"
        assert "resolved_url" not in result
        assert result["registries_tried"] == ["npm", "pypi", "crates"]
        assert result["registry_outcomes"] == {"npm": "404", "pypi": "404", "crates": "404"}
        assert result["name_found_in"] == []

    def test_timeouts_and_404s_never_make_it_ambiguous(self, monkeypatch):
        monkeypatch.setattr(mod, "try_npm", lambda n, t: (None, "timeout"))
        monkeypatch.setattr(mod, "try_pypi", lambda n, t: (None, "404"))
        monkeypatch.setattr(
            mod, "try_crates", lambda n, t: (("https://github.com/serde-rs/serde", "serde-rs", "serde", None), "ok")
        )
        result = mod.resolve_package("serde")
        assert result["status"] == "ok"
        assert result["registry_used"] == "crates"
        assert result["registry_outcomes"] == {"npm": "timeout", "pypi": "404", "crates": "ok"}
        assert result["name_found_in"] == ["crates"]

    @pytest.mark.parametrize("earlier", ["no-github-link", "error"])
    def test_an_earlier_answer_makes_it_ambiguous(self, monkeypatch, earlier):
        monkeypatch.setattr(mod, "try_npm", lambda n, t: (None, "timeout"))
        monkeypatch.setattr(mod, "try_pypi", lambda n, t: (None, earlier))
        monkeypatch.setattr(
            mod, "try_crates", lambda n, t: (("https://github.com/serde-rs/serde", "serde-rs", "serde", None), "ok")
        )
        result = mod.resolve_package("serde")
        assert result["status"] == "ambiguous"
        assert result["resolved_url"] == "https://github.com/serde-rs/serde"
        assert result["registry_used"] == "crates"
        assert result["name_found_in"] == ["pypi", "crates"]
        assert result["registry_outcomes"] == {"npm": "timeout", "pypi": earlier, "crates": "ok"}

    def test_a_later_answer_is_never_asked(self, monkeypatch):
        # The chain stops at the first resolution: npm first is never ambiguous.
        monkeypatch.setattr(mod, "try_npm", lambda n, t: (("https://github.com/o/r", "o", "r", None), "ok"))
        monkeypatch.setattr(mod, "try_pypi", lambda n, t: pytest.fail("pypi must not be called"))
        assert mod.resolve_package("r")["status"] == "ok"

    @pytest.mark.parametrize("registry", ["npm", "pypi", "crates"])
    def test_one_registry_only(self, monkeypatch, registry):
        called: list[str] = []
        for name in ("npm", "pypi", "crates"):
            def fake(n, t, name=name):
                called.append(name)
                return (None, "no-github-link") if name != registry else (
                    (f"https://github.com/o/{name}", "o", name, None), "ok")
            monkeypatch.setattr(mod, f"try_{name}", fake)
        result = mod.resolve_package("pkg", registry=registry)
        assert called == [registry]
        assert result["status"] == "ok"
        assert result["registries_tried"] == [registry]
        assert result["resolved_url"] == f"https://github.com/o/{registry}"

    @staticmethod
    def _each_registry_knows_it(monkeypatch) -> list[str]:
        called: list[str] = []
        for name in ("npm", "pypi", "crates"):
            def fake(n, t, name=name):
                called.append(name)
                return (f"https://github.com/o/{name}", "o", name, None), "ok"
            monkeypatch.setattr(mod, f"try_{name}", fake)
        return called

    @pytest.mark.parametrize("language, registry", [
        ("python", "pypi"), ("Python", "pypi"), ("py", "pypi"), ("rust", "crates"), ("TypeScript", "npm"),
        ("javascript", "npm"), (" js ", "npm"), ("ts", "npm")])
    def test_a_language_hint_picks_its_registry(self, monkeypatch, language, registry):
        # `numpy language=python` in a batch file never reaches npm's unrelated numpy.
        called = self._each_registry_knows_it(monkeypatch)
        result = mod.resolve_package("numpy", language=language)
        assert called == [registry]
        assert (result["status"], result["registry_used"], result["name_found_in"]) == ("ok", registry, [registry])

    @pytest.mark.parametrize("language", ["go", "Java", "", None])
    def test_any_other_language_walks_the_chain(self, monkeypatch, language):
        called = self._each_registry_knows_it(monkeypatch)
        assert mod.resolve_package("cobra", language=language)["registry_used"] == "npm"
        assert called == ["npm"]

    def test_the_registry_wins_over_the_language(self, monkeypatch):
        called = self._each_registry_knows_it(monkeypatch)
        result = mod.resolve_package("requests", registry="pypi", language="rust")
        assert (called, result["registry_used"]) == (["pypi"], "pypi")

    def test_statuses_and_exit_codes_agree(self):
        assert set(mod.STATUSES) == set(mod.EXIT_CODES)
        assert mod.EXIT_CODES == {"ok": 0, "fallthrough": 1, "ambiguous": 3}


def _fake_result(status):
    def fake(name, timeout, registry=None, language=None):
        out = {"status": status, "package_name": name, "name_found_in": [], "registries_tried": ["npm"],
               "registry_outcomes": {"npm": "404"}, "registry": registry, "language": language, "timeout": timeout}
        if status != "fallthrough":
            out.update(resolved_url="https://github.com/o/r", repo_owner="o", repo_name="r", skill_name="r",
                       registry_used="npm", source_subdir=None)
        return out
    return fake


class TestCli:
    def test_cli_ok_exit_zero(self, monkeypatch, capsys):
        monkeypatch.setattr(mod, "resolve_package", _fake_result("ok"))
        rc = mod.main(["resolve", "lodash"])
        assert rc == 0
        out = capsys.readouterr().out
        assert '"status": "ok"' in out

    def test_cli_fallthrough_exit_one(self, monkeypatch, capsys):
        monkeypatch.setattr(mod, "resolve_package", _fake_result("fallthrough"))
        rc = mod.main(["resolve", "nonexistent"])
        assert rc == 1
        out = capsys.readouterr().out
        assert '"status": "fallthrough"' in out

    def test_cli_ambiguous_exit_three(self, monkeypatch, capsys):
        monkeypatch.setattr(mod, "resolve_package", _fake_result("ambiguous"))
        assert mod.main(["resolve", "next"]) == 3
        assert json.loads(capsys.readouterr().out)["status"] == "ambiguous"

    def test_cli_passes_registry_language_and_timeout(self, monkeypatch, capsys):
        monkeypatch.setattr(mod, "resolve_package", _fake_result("ok"))
        assert mod.main(["resolve", "requests", "--registry", "pypi", "--timeout", "3"]) == 0
        out = json.loads(capsys.readouterr().out)
        assert (out["registry"], out["language"], out["timeout"]) == ("pypi", None, 3.0)
        assert mod.main(["resolve", "numpy", "--language", "python"]) == 0
        out = json.loads(capsys.readouterr().out)
        assert (out["registry"], out["language"]) == (None, "python")

    def test_cli_rejects_an_unknown_registry(self, capsys):
        with pytest.raises(SystemExit) as exc:
            mod.main(["resolve", "x", "--registry", "maven"])
        assert exc.value.code == 2

    def test_the_bare_form_still_resolves(self, monkeypatch, capsys):
        monkeypatch.setattr(mod, "resolve_package", _fake_result("ok"))
        assert mod.main(["lodash", "--timeout", "5"]) == 0
        out = json.loads(capsys.readouterr().out)
        assert (out["package_name"], out["timeout"]) == ("lodash", 5.0)

    def test_parse_target_from_the_flag(self, capsys):
        assert mod.main(["parse-target", "--target", "cognee@0.5.0"]) == 0
        out = json.loads(capsys.readouterr().out)
        assert (out["kind"], out["package_name"], out["target_version"]) == ("package", "cognee", "0.5.0")

    def test_parse_target_from_stdin(self, monkeypatch, capsys):
        text = "Je veux une compétence d'accueil, pas `$HOME`\n"
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(text.encode("utf-8")), encoding="ascii"))
        assert mod.main(["parse-target"]) == 0
        out = json.loads(capsys.readouterr().out)
        assert (out["kind"], out["input"]) == ("unparsed", text.strip())

    def test_the_script_runs_as_a_program(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "parse-target"], input=b"requests==2.31",
                                capture_output=True, check=False)
        assert result.returncode == 0, result.stderr
        out = json.loads(result.stdout)
        assert (out["kind"], out["registry"], out["target_version"]) == ("package", "pypi", "2.31")
