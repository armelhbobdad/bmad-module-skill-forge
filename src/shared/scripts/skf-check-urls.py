# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Check URLs: tell which documentation URLs answer.

Brief Skill checks the documentation URLs a user or a headless caller
gives (step 1 §3.2, step 3 §2b and the headless input gate) with one call
to this helper instead of one `curl -sI` per URL whose headers the model
reads: `curl -sI` follows no redirect and never tries GET, so a server
that refuses HEAD was reported unreachable.

CLI:

  uv run skf-check-urls.py --timeout 5 --urls-file <path or ->

--urls-file names a file of URLs, one per line, or `-` for stdin, read as
UTF-8. Blank lines are skipped and each URL is checked once, in the order
it first appears. --timeout is the seconds each request may wait for the
server (default 5).

Each URL gets a HEAD request with redirects followed (the method stays
HEAD at every hop) and a User-Agent of its own. When HEAD answers 403, 405
or 501, which servers send when they refuse HEAD, the URL is asked again
with GET, and that answer counts. The URLs are checked at the same time.
A path or query with characters outside ASCII is sent percent-encoded as
UTF-8, as a browser sends it; the entry keeps the URL as given.

Output (stdout, one JSON array, in input order):

  [{"url": "<url>", "ok": true | false, "status": <int> | null,
    "error": null | "<reason>"}]

  ok      true when the final answer is a 2xx or 3xx status
  status  the final HTTP status, or null when none came back
  error   null when a status came back, else a short reason:
          "timed out", "not an http(s) URL", or the connection
          error's reason (a DNS failure, a refused connection, a
          TLS error)

Exit codes:
  0  the check ran, whatever the URLs answered ([] for an empty list)
  2  the --urls-file is missing or unreadable, or --timeout is not above
     0 (one line on stderr), or an argument is not valid
"""

from __future__ import annotations

import argparse
import http.client
import json
import socket
import string
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

USER_AGENT = "skf-check-urls/1.0 (+https://github.com/armelhbobdad/bmad-module-skill-forge)"
# The statuses a server sends when it refuses HEAD: the URL is asked again with GET.
RETRY_WITH_GET = frozenset({403, 405, 501})
MAX_WORKERS = 16


class _KeepMethodRedirect(urllib.request.HTTPRedirectHandler):
    """Follow a redirect with the method of the request that got it.

    Python 3.11's handler sends GET to the new location whatever the first
    request was, so a HEAD check would download every redirected page.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and req.get_method() == "HEAD":
            new.method = "HEAD"
        return new


_OPENER = urllib.request.build_opener(_KeepMethodRedirect)


def _is_timeout(exc: BaseException) -> bool:
    return isinstance(exc, (TimeoutError, socket.timeout))


def _reason(exc: object) -> str:
    """One line that names why a request got no status."""
    if isinstance(exc, BaseException) and _is_timeout(exc):
        return "timed out"
    text = " ".join(str(exc).split())
    return text or type(exc).__name__


def _wire(url: str) -> str:
    """The URL with a non-ASCII path, query or fragment percent-encoded as UTF-8: the request line is ASCII.

    The host is left as given, since http.client sends a non-ASCII host as IDNA.
    """
    parts = urllib.parse.urlsplit(url)
    path, query, fragment = (urllib.parse.quote(text, safe=string.punctuation)
                             for text in (parts.path, parts.query, parts.fragment))
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, fragment))


def _ask(url: str, method: str, timeout: float) -> tuple[int | None, str | None]:
    """(the final status, None), or (None, why no status came back)."""
    request = urllib.request.Request(_wire(url), method=method, headers={"User-Agent": USER_AGENT})
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            return response.status, None
    except urllib.error.HTTPError as exc:
        exc.close()
        return exc.code, None
    except urllib.error.URLError as exc:  # the connection failed: its reason, not "<urlopen error ...>"
        return None, _reason(exc.reason)
    except (OSError, ValueError, http.client.HTTPException) as exc:
        return None, _reason(exc)


def is_http_url(url: str) -> bool:
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    return parts.scheme.lower() in ("http", "https") and bool(parts.netloc)


def check_url(url: str, timeout: float) -> dict:
    """The {url, ok, status, error} entry of one URL."""
    if not is_http_url(url):
        return {"url": url, "ok": False, "status": None, "error": "not an http(s) URL"}
    status, error = _ask(url, "HEAD", timeout)
    if status in RETRY_WITH_GET:
        status, error = _ask(url, "GET", timeout)
    ok = status is not None and 200 <= status < 400
    return {"url": url, "ok": ok, "status": status, "error": None if status is not None else error}


def read_urls(text: str) -> list[str]:
    """One URL per line: blank lines skipped, each URL once, in the order it first appears."""
    urls: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        url = line.strip()
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def check_urls(urls: list[str], timeout: float) -> list[dict]:
    if not urls:
        return []
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(urls))) as pool:
        return list(pool.map(lambda url: check_url(url, timeout), urls))


def _read_input(name: str) -> str:
    """The --urls-file text as UTF-8, stdin for `-`; OSError or UnicodeDecodeError when it cannot be read."""
    if name == "-":
        stream = getattr(sys.stdin, "buffer", None)
        data = stream.read() if stream is not None else sys.stdin.read().encode("utf-8")
    else:
        with open(name, "rb") as handle:
            data = handle.read()
    return data.decode("utf-8-sig")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-check-urls",
        description="Check documentation URLs: HEAD with redirects followed, GET when HEAD answers 403, 405 or "
                    "501. Prints [{url, ok, status, error}] in input order.",
    )
    parser.add_argument("--urls-file", required=True,
                        help="a file of URLs, one per line, or - for stdin (UTF-8)")
    parser.add_argument("--timeout", type=float, default=5.0,
                        help="seconds each request may wait for the server (default 5)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if not args.timeout > 0:
        sys.stderr.write(f"skf-check-urls: --timeout must be above 0, got {args.timeout:g}\n")
        return 2
    try:
        text = _read_input(args.urls_file)
    except (OSError, UnicodeDecodeError) as exc:
        sys.stderr.write(f"skf-check-urls: cannot read --urls-file {args.urls_file}: {_reason(exc)}\n")
        return 2
    sys.stdout.write(json.dumps(check_urls(read_urls(text), args.timeout), ensure_ascii=False) + "\n")
    return 0


def _force_utf8(*streams) -> None:
    """Reconfigure stdout and stderr to UTF-8 with LF line ends, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which cannot print every
    character of a URL, and writes CRLF.
    """
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8", newline="\n")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors, newline="\n")


if __name__ == "__main__":
    _force_utf8(sys.stdout, sys.stderr)
    sys.exit(main())
