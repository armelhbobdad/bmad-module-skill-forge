#!/usr/bin/env python3
"""Tests for skf-github-fetch.py: stage a GitHub repository's files at one ref.

No test reaches GitHub or runs the gh a developer has installed: the file
choice and the reader order run against scripted readers (_raw and _gh_raw
replaced by fakes), _raw reads from a local HTTP server standing in for
raw.githubusercontent.com, and _gh_raw runs a fake gh placed first on PATH
(POSIX only: the fake is a script).
"""

from __future__ import annotations

import http.server
import importlib.util
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HELPER = REPO / "src" / "shared" / "scripts" / "skf-github-fetch.py"

spec = importlib.util.spec_from_file_location("skf_github_fetch", HELPER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

LISTING = ["README.md", "go.mod", "main.go", "main_test.go", "util.go", "pkg/a.go",
           "src/main/java/com/acme/App.java", "src/main/java/com/acme/util/Helper.java",
           "skills/alpha/SKILL.md", "skills/module-help.csv"]
# A source file whose bytes a shell string or the model would change: quotes,
# an apostrophe, a backslash, CRLF line ends and a non-ASCII character.
TRICKY = "fn f<'a>(s: &'a str) -> &'a str { \"it's\\n\" }\r\n// café\r\n".encode("utf-8")


@pytest.fixture(autouse=True)
def _clock():
    mod._start_clock(None)


def _tree(tmp_path: Path, paths=LISTING, **extra) -> Path:
    path = tmp_path / "tree.json"
    path.write_text(json.dumps({"status": "ok", "tree": list(paths), "truncated": False, **extra}),
                    encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Which files
# --------------------------------------------------------------------------


def test_patterns_pick_listed_files_in_pattern_order_each_once():
    chosen, unmatched = mod.select(LISTING, ["go.mod", "*.go", "main.go", "index.js"],
                                   limit=5, excludes=["*_test.go"])
    assert chosen == ["go.mod", "main.go", "util.go"]
    assert unmatched == ["index.js"]


def test_a_glob_spans_folders_only_with_double_star():
    chosen, _ = mod.select(LISTING, ["src/main/java/**/*.java"])
    assert chosen == ["src/main/java/com/acme/App.java", "src/main/java/com/acme/util/Helper.java"]
    assert mod.select(LISTING, ["src/main/java/*.java"]) == ([], ["src/main/java/*.java"])
    assert mod.select(LISTING, ["./README.md"])[0] == ["README.md"]


def test_limit_caps_each_pattern():
    assert mod.select(LISTING, ["**/*.go"], limit=2)[0] == ["main.go", "main_test.go"]
    assert mod.select(LISTING, ["**/*.go"], limit=0)[0] == ["main.go", "main_test.go", "pkg/a.go", "util.go"]


@pytest.mark.parametrize("path", ["../escape.txt", "/etc/passwd", "a/../../b", "a\\b", "a//b"],
                         ids=["dotdot", "absolute", "inner-dotdot", "backslash", "empty-segment"])
def test_a_path_leading_outside_dest_is_never_written(tmp_path, path):
    assert mod._target(tmp_path, path) is None


# --------------------------------------------------------------------------
# Readers
# --------------------------------------------------------------------------


class Readers:
    def __init__(self, raw: dict, gh: dict):
        self.raw, self.gh, self.calls = raw, gh, []

    def fake_raw(self, owner, repo, ref, path):
        self.calls.append(("raw", path))
        return (self.raw[path], "") if path in self.raw else (None, "HTTP 404 from raw")

    def fake_gh(self, owner, repo, ref, path):
        self.calls.append(("gh", path))
        return (self.gh[path], "") if path in self.gh else (None, "gh: Not Found (HTTP 404)")


@pytest.fixture
def readers(monkeypatch):
    def install(raw: dict, gh: dict) -> Readers:
        r = Readers(raw, gh)
        monkeypatch.setattr(mod, "_raw", r.fake_raw)
        monkeypatch.setattr(mod, "_gh_raw", r.fake_gh)
        return r
    return install


def test_a_public_repository_is_read_from_the_raw_url(tmp_path, readers):
    r = readers({"go.mod": b"module x\n", "main.go": TRICKY}, {})
    out = mod.run("acme/lib", "v1.0.0", str(_tree(tmp_path)), str(tmp_path / "src"), ["go.mod", "main.go", "x.go"])
    assert (out["status"], out["via"], out["fetched"], out["unmatched"]) == ("ok", "raw", ["go.mod", "main.go"],
                                                                            ["x.go"])
    assert (tmp_path / "src" / "main.go").read_bytes() == TRICKY
    assert r.calls == [("raw", "go.mod"), ("raw", "main.go")]
    assert out["ref"] == "v1.0.0" and out["repo"] == "acme/lib" and out["message"] is None


def test_a_private_repository_switches_to_gh_after_the_first_miss(tmp_path, readers):
    r = readers({}, {"go.mod": b"module x\n", "main.go": b"package x\n", "util.go": b"package x\n"})
    out = mod.run("acme/lib", None, str(_tree(tmp_path)), str(tmp_path / "src"), ["go.mod", "main.go", "util.go"])
    assert (out["status"], out["via"], out["ref"]) == ("ok", "gh", "HEAD")
    assert r.calls == [("raw", "go.mod"), ("gh", "go.mod"), ("gh", "main.go"), ("gh", "util.go")]


def test_files_no_reader_could_read_make_the_run_partial_or_unavailable(tmp_path, readers):
    readers({"go.mod": b"module x\n"}, {})
    out = mod.run("acme/lib", "main", str(_tree(tmp_path)), str(tmp_path / "src"), ["go.mod", "main.go"])
    assert out["status"] == "partial" and out["fetched"] == ["go.mod"]
    assert out["failed"] == [{"path": "main.go", "detail": "raw: HTTP 404 from raw; gh: gh: Not Found (HTTP 404)"}]
    assert out["message"].startswith("Could not fetch main.go from acme/lib at main: ")
    readers({}, {})
    out = mod.run("acme/lib", "main", str(_tree(tmp_path)), str(tmp_path / "src2"), ["go.mod"])
    assert out["status"] == "unavailable" and out["fetched"] == [] and out["via"] is None


def test_nothing_matched_is_ok_and_costs_no_request(tmp_path, readers):
    r = readers({}, {})
    out = mod.run("acme/lib", "HEAD", str(_tree(tmp_path)), str(tmp_path / "src"), ["index.js", "src/index.ts"])
    assert (out["status"], out["fetched"], out["unmatched"]) == ("ok", [], ["index.js", "src/index.ts"])
    assert r.calls == []


def test_a_truncated_listing_is_reported(tmp_path, readers):
    readers({"go.mod": b"m\n"}, {})
    out = mod.run("acme/lib", "HEAD", str(_tree(tmp_path, truncated=True)), str(tmp_path / "s"), ["go.mod"])
    assert out["truncated"] is True


def test_a_truncated_listing_still_tries_a_literal_path_it_lacks(tmp_path, readers):
    """GitHub cuts a very large tree short: a root manifest the partial listing lacks is read anyway."""
    tree = _tree(tmp_path, ["README.md", "main.go"], truncated=True)
    r = readers({"go.mod": b"module x\n", "main.go": b"package x\n"}, {})
    out = mod.run("acme/lib", "HEAD", str(tree), str(tmp_path / "src"),
                  ["go.mod", "*.go", "src/index.ts", "pkg/*.go", "vendor/x.go"])
    assert (out["status"], out["fetched"]) == ("ok", ["go.mod", "main.go"])
    # A literal path no reader could read stays unmatched, and is no failure; a glob costs no request.
    assert out["unmatched"] == ["src/index.ts", "pkg/*.go", "vendor/x.go"] and out["failed"] == []
    assert ("raw", "src/index.ts") in r.calls and not any(path == "pkg/*.go" for _, path in r.calls)
    assert (tmp_path / "src" / "go.mod").read_bytes() == b"module x\n"
    # An excluded path is never guessed, and a complete listing guesses nothing.
    assert mod.select(["main.go"], ["main_test.go"], excludes=["*_test.go"], truncated=True) == \
        ([], ["main_test.go"])
    assert mod.select(["main.go"], ["go.mod"]) == ([], ["go.mod"])
    assert mod.select(["main.go"], ["go.mod"], truncated=True) == (["go.mod"], ["go.mod"])


@pytest.mark.parametrize("repo,ref,message", [
    ("gitlab.com/acme/lib", "HEAD", "is not a github.com repository"),
    ("acme/lib", "bad ref", "is not a valid branch, tag or commit name"),
], ids=["not-github", "bad-ref"])
def test_an_invalid_repo_or_ref_is_a_usage_error(tmp_path, repo, ref, message):
    with pytest.raises(mod.UsageError, match=message):
        mod.run(repo, ref, str(_tree(tmp_path)), str(tmp_path / "src"), ["go.mod"])


# --------------------------------------------------------------------------
# _raw against a local server, _gh_raw against a fake gh
# --------------------------------------------------------------------------


class _Handler(http.server.BaseHTTPRequestHandler):
    files: dict[str, bytes] = {}

    def do_GET(self):  # noqa: N802 - http.server's name
        body = self.files.get(self.path)
        self.send_response(200 if body is not None else 404)
        self.end_headers()
        self.wfile.write(body if body is not None else b"404: Not Found")

    def log_message(self, *args):
        pass


@pytest.fixture
def raw_server(monkeypatch):
    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(mod, "RAW_ROOT", f"http://127.0.0.1:{server.server_address[1]}")
    yield _Handler.files
    server.shutdown()
    _Handler.files = {}


def test_raw_reads_the_bytes_at_the_ref(raw_server):
    raw_server["/acme/lib/release/1.x/src/lib.rs"] = TRICKY
    assert mod._raw("acme", "lib", "release/1.x", "src/lib.rs") == (TRICKY, "")
    body, detail = mod._raw("acme", "lib", "release/1.x", "src/missing.rs")
    assert body is None and detail.startswith("HTTP 404 from http://127.0.0.1:")


@pytest.mark.skipif(sys.platform == "win32", reason="the stand-in gh is a POSIX shell script")
def test_gh_raw_asks_for_the_raw_media_type_at_the_ref(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / "file").write_bytes(TRICKY)
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        '[ "$1 $2 $3 $4 $5" = "api --hostname github.com -H Accept: application/vnd.github.raw" ] || exit 9\n'
        'case "$6" in "repos/acme/lib/contents/src/lib.rs?ref=v1.0.0") cat "$FILE" ;;\n'
        '  *) echo "gh: Not Found (HTTP 404)" >&2; exit 1 ;; esac\n',
        encoding="utf-8",
    )
    gh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("FILE", str(tmp_path / "file"))
    monkeypatch.chdir(tmp_path)
    assert mod._gh_raw("acme", "lib", "v1.0.0", "src/lib.rs") == (TRICKY, "")
    assert mod._gh_raw("acme", "lib", "v1.0.0", "src/nope.rs") == (None, "gh: Not Found (HTTP 404)")


def test_gh_raw_without_gh(monkeypatch):
    monkeypatch.setattr(mod._probe()._sibling(), "_resolve_outside_cwd", lambda _name: None)
    assert mod._gh_raw("acme", "lib", "HEAD", "x") == (None, "gh is not installed")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_the_cli_fetches_patterns_and_a_patterns_file(tmp_path, raw_server, monkeypatch, capsys):
    raw_server["/acme/lib/HEAD/skills/alpha/SKILL.md"] = b"---\nname: alpha\n---\n"
    raw_server["/acme/lib/HEAD/skills/module-help.csv"] = b"module,skill\n"
    raw_server["/acme/lib/HEAD/README.md"] = b"# Lib\n"
    (tmp_path / "fetch.txt").write_text("skills/alpha/SKILL.md\n\nskills/module-help.csv\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_gh_raw", lambda *a: (None, "gh is not installed"))
    rc = mod.main(["--repo", "https://github.com/acme/lib", "--ref", "", "--tree-file", str(_tree(tmp_path)),
                   "--dest", str(tmp_path / "src"), "--patterns-file", str(tmp_path / "fetch.txt"), "README.md"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0, out
    assert out["fetched"] == ["README.md", "skills/alpha/SKILL.md", "skills/module-help.csv"]
    assert out["dest"] == (tmp_path / "src").absolute().as_posix()
    assert (tmp_path / "src" / "skills" / "module-help.csv").read_bytes() == b"module,skill\n"


def test_the_cli_exit_codes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mod, "_raw", lambda *a: (None, "HTTP 404"))
    monkeypatch.setattr(mod, "_gh_raw", lambda *a: (None, "gh is not installed"))
    args = ["--repo", "acme/lib", "--tree-file", str(_tree(tmp_path)), "--dest", str(tmp_path / "src")]
    assert mod.main([*args, "go.mod"]) == 3
    assert json.loads(capsys.readouterr().out)["status"] == "unavailable"
    assert mod.main([*args, "nothing-listed.txt"]) == 0
    capsys.readouterr()
    failed = tmp_path / "failed.json"
    failed.write_text('{"status": "unavailable", "message": "gh is not logged in", "tree": []}', encoding="utf-8")
    assert mod.main(["--repo", "acme/lib", "--tree-file", str(failed), "--dest", str(tmp_path), "x"]) == 2
    assert "gh is not logged in" in json.loads(capsys.readouterr().err)["message"]


def test_help_runs_as_a_script():
    proc = subprocess.run([sys.executable, str(HELPER), "--help"], capture_output=True, text=True, check=False,
                          timeout=60)
    assert proc.returncode == 0 and "--tree-file" in proc.stdout
