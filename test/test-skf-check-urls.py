#!/usr/bin/env python3
"""skf-check-urls.py: which documentation URLs answer.

#1139 (determinism-5): Brief Skill's step 1 §3.2, step 3 §2b and headless
input gate each had the model run one `curl -sI` per doc URL and read the
headers itself. `curl -sI` follows no redirect and never tries GET, so a
server that refuses HEAD was reported unreachable. The helper sends HEAD
with redirects followed and asks again with GET on 403, 405 or 501. These
checks run it against a local http.server: a 2xx, a redirect to a page and
to a missing one, a 404, a server that refuses HEAD three ways, one that
answers too late, and input it cannot check. No test reaches another host.
"""

from __future__ import annotations

import http.server
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HELPER = REPO / "src" / "shared" / "scripts" / "skf-check-urls.py"

spec = importlib.util.spec_from_file_location("skf_check_urls", HELPER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# How long the slow page waits before it answers: past `--timeout 1`, and short, so the server thread ends soon.
SLOW = 2.5


class _Handler(http.server.BaseHTTPRequestHandler):
    """Each path answers by the method it gets; every request is logged as (method, path), and its User-Agent."""

    log: list[tuple[str, str]] = []
    agents: list[tuple[str, str, str | None]] = []
    # path -> {method: status}, "*" for any method
    routes = {
        "/ok": {"*": 200},
        "/missing": {"*": 404},
        "/no-head": {"HEAD": 405, "GET": 200},
        "/forbidden-head": {"HEAD": 403, "GET": 200},
        "/no-head-501": {"HEAD": 501, "GET": 200},
        "/forbidden": {"*": 403},
        "/caf%C3%A9": {"*": 200},
    }
    redirects = {"/moved": "/ok", "/moved-missing": "/missing", "/moved-twice": "/moved"}

    def _answer(self):
        self.log.append((self.command, self.path))
        self.agents.append((self.command, self.path, self.headers.get("User-Agent")))
        if self.path == "/slow":
            time.sleep(SLOW)
        if self.path in self.redirects:
            self.send_response(302)
            self.send_header("Location", self.redirects[self.path])
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        route = self.routes.get(self.path, {"*": 200} if self.path == "/slow" else {"*": 404})
        status = route.get(self.command, route.get("*", 404))
        body = f"{status} {self.path}\n".encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    do_HEAD = _answer  # noqa: N815 - http.server's names
    do_GET = _answer  # noqa: N815

    def log_message(self, *args):
        pass


class _Server(http.server.ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        pass  # the slow page writes to a client that gave up


@pytest.fixture
def server():
    _Handler.log = []
    _Handler.agents = []
    httpd = _Server(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _env() -> dict:
    """The environment without a proxy, so 127.0.0.1 is asked directly."""
    return {key: value for key, value in os.environ.items() if "proxy" not in key.lower()}


def _run(*args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HELPER), *args], input=stdin.encode("utf-8"), capture_output=True,
                          timeout=60, check=False, env=_env())


def _check(urls: list[str], timeout: str = "1") -> list[dict]:
    proc = _run("--timeout", timeout, "--urls-file", "-", stdin="".join(f"{url}\n" for url in urls))
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert b"\r\n" not in proc.stdout
    return json.loads(proc.stdout)


def _by_url(results: list[dict]) -> dict[str, dict]:
    return {entry["url"]: entry for entry in results}


# --------------------------------------------------------------------------
# The matrix rows
# --------------------------------------------------------------------------


def test_a_server_that_refuses_head_is_asked_with_get(server):
    """405, 403 and 501 to HEAD, 200 to GET: each URL is ok with the GET's status, so no site warns."""
    results = _by_url(_check([f"{server}/no-head", f"{server}/forbidden-head", f"{server}/no-head-501"]))
    for path in ("/no-head", "/forbidden-head", "/no-head-501"):
        assert results[f"{server}{path}"] == {"url": f"{server}{path}", "ok": True, "status": 200, "error": None}
        assert [method for method, at in _Handler.log if at == path] == ["HEAD", "GET"], path


def test_a_refusal_that_get_shares_is_not_ok(server):
    [entry] = _check([f"{server}/forbidden"])
    assert entry == {"url": f"{server}/forbidden", "ok": False, "status": 403, "error": None}
    assert [method for method, at in _Handler.log if at == "/forbidden"] == ["HEAD", "GET"]


def test_redirects_are_followed_with_head(server):
    """A 302 to a page is that page's 200, a 302 to a missing page its 404; HEAD stays HEAD at every hop."""
    results = _by_url(_check([f"{server}/moved", f"{server}/moved-missing", f"{server}/moved-twice"]))
    assert results[f"{server}/moved"] == {"url": f"{server}/moved", "ok": True, "status": 200, "error": None}
    assert results[f"{server}/moved-twice"]["status"] == 200 and results[f"{server}/moved-twice"]["ok"] is True
    assert results[f"{server}/moved-missing"] == {"url": f"{server}/moved-missing", "ok": False, "status": 404,
                                                  "error": None}
    assert {method for method, _ in _Handler.log} == {"HEAD"}, _Handler.log


def test_an_ok_page_gets_one_head_and_no_get(server):
    [entry] = _check([f"{server}/ok"])
    assert entry == {"url": f"{server}/ok", "ok": True, "status": 200, "error": None}
    assert _Handler.log == [("HEAD", "/ok")]


def test_a_missing_page_is_not_ok(server):
    [entry] = _check([f"{server}/missing"])
    assert entry == {"url": f"{server}/missing", "ok": False, "status": 404, "error": None}
    assert _Handler.log == [("HEAD", "/missing")]


def test_a_page_that_answers_too_late_timed_out(server):
    started = time.monotonic()
    [entry] = _check([f"{server}/slow"], timeout="1")
    assert entry == {"url": f"{server}/slow", "ok": False, "status": None, "error": "timed out"}
    assert time.monotonic() - started < SLOW + 30


def test_a_line_that_is_no_http_url_is_not_ok_and_not_asked(server):
    results = _by_url(_check(["docs.example.com", "ftp://example.com/docs", "mailto:docs@example.com"]))
    for url, entry in results.items():
        assert entry == {"url": url, "ok": False, "status": None, "error": "not an http(s) URL"}
    assert _Handler.log == []


def test_a_refused_connection_names_its_reason():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    [entry] = _check([f"http://127.0.0.1:{port}/docs"])
    assert entry["ok"] is False and entry["status"] is None
    assert isinstance(entry["error"], str) and entry["error"] and "\n" not in entry["error"]


# --------------------------------------------------------------------------
# Input and output
# --------------------------------------------------------------------------


def test_each_url_once_in_input_order(server):
    """Blank lines are skipped, a repeated URL is checked once, and the entries keep the input order, the slow
    one included, though the URLs are checked at the same time."""
    urls = [f"{server}/slow", f"{server}/missing", f"{server}/ok", f"{server}/missing", "docs.example.com"]
    proc = _run("--timeout", "1", "--urls-file", "-", stdin="\n".join(urls[:2]) + "\n\n  \n" + "\n".join(urls[2:]))
    assert proc.returncode == 0, proc.stderr
    results = json.loads(proc.stdout)
    assert [entry["url"] for entry in results] == [f"{server}/slow", f"{server}/missing", f"{server}/ok",
                                                   "docs.example.com"]
    assert sorted(_Handler.log) == sorted([("HEAD", "/slow"), ("HEAD", "/missing"), ("HEAD", "/ok")])


def test_a_urls_file_is_read_as_utf8_with_crlf_and_a_bom(server, tmp_path):
    path = tmp_path / "urls.txt"
    path.write_bytes(("﻿" + f"{server}/ok\r\n{server}/café-missing\r\n").encode("utf-8"))
    proc = _run("--timeout", "1", "--urls-file", str(path))
    assert proc.returncode == 0, proc.stderr
    results = json.loads(proc.stdout.decode("utf-8"))
    assert [entry["url"] for entry in results] == [f"{server}/ok", f"{server}/café-missing"]
    assert results[0]["ok"] is True
    # The non-ASCII path reaches the server percent-encoded, which answers it with its own 404.
    assert results[1] == {"url": f"{server}/café-missing", "ok": False, "status": 404, "error": None}
    assert ("HEAD", "/caf%C3%A9-missing") in _Handler.log


def test_a_non_ascii_path_is_sent_percent_encoded(server):
    """A localized docs page pasted as the browser shows it: the request line is ASCII, the entry keeps the URL."""
    [entry] = _check([f"{server}/café"])
    assert entry == {"url": f"{server}/café", "ok": True, "status": 200, "error": None}
    assert _Handler.log == [("HEAD", "/caf%C3%A9")]


def test_every_request_carries_the_helpers_user_agent(server):
    """The HEAD, each redirect hop and the GET retry name the helper, not urllib's default agent."""
    _check([f"{server}/moved", f"{server}/no-head", f"{server}/ok"])
    asked = {(method, path) for method, path, _ in _Handler.agents}
    assert {("HEAD", "/moved"), ("HEAD", "/ok"), ("HEAD", "/no-head"), ("GET", "/no-head")} <= asked
    assert {agent for _, _, agent in _Handler.agents} == {mod.USER_AGENT}


def test_an_empty_list_prints_an_empty_array():
    for stdin in ("", "\n\n  \n"):
        proc = _run("--timeout", "5", "--urls-file", "-", stdin=stdin)
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout) == []


@pytest.mark.parametrize("args", [
    pytest.param(["--timeout", "5", "--urls-file", "{missing}"], id="missing-file"),
    pytest.param(["--timeout", "5", "--urls-file", "{folder}"], id="folder"),
    pytest.param(["--timeout", "0", "--urls-file", "-"], id="zero-timeout"),
    pytest.param(["--timeout", "-1", "--urls-file", "-"], id="negative-timeout"),
])
def test_bad_input_exits_2_with_one_stderr_line(tmp_path, args):
    args = [arg.replace("{missing}", str(tmp_path / "nope.txt")).replace("{folder}", str(tmp_path))
            for arg in args]
    proc = _run(*args)
    assert proc.returncode == 2
    assert proc.stdout == b""
    lines = proc.stderr.decode("utf-8", "replace").splitlines()
    assert len(lines) == 1 and lines[0].startswith("skf-check-urls: "), lines


def test_the_default_timeout_is_five_seconds():
    assert mod._build_parser().parse_args(["--urls-file", "-"]).timeout == 5.0


def test_read_urls_and_is_http_url():
    assert mod.read_urls(" https://a.dev/x \n\nhttps://a.dev/x\nhttp://b.dev\n") == ["https://a.dev/x", "http://b.dev"]
    assert mod.is_http_url("HTTPS://Docs.Example.com/api")
    for url in ("docs.example.com", "https://", "file:///tmp/x", "http://[::1"):
        assert not mod.is_http_url(url), url
