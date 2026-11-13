# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""SKF QMD Portfolio Similarity: compare a proposed brief with the briefs
QMD has indexed, and check that a brief's collection holds its file.

Brief Skill registers each brief it writes at Deep tier as a QMD collection
named `<name>-brief` (references/qmd-collection-registration.md). Step 1
runs `similar` to show the briefs that look close to a proposed name, and
the registration runs `verify-collection` after `qmd embed`. Both used to
be shell the model ran, capped, batched and merged by hand.

CLI:

  uv run skf-qmd-portfolio-similarity.py similar --name <name> \\
      --text-file <path or -> [--suffix -brief] [--cap 12] \\
      [--concurrency 4] [--timeout 20] [--min-score 0.6] [--top 3]
  uv run skf-qmd-portfolio-similarity.py verify-collection <collection>

similar
-------
Lists the collections with `qmd collection list` and keeps those whose
name ends in --suffix, except `<name><suffix>`, the proposed name's own
(step 1's exact-name collision check covers it). It takes the first --cap
of them in listing order (qmd gives no recency order, so the cap bounds
the count, not the age) and runs, on each,

  qmd query "<name> <text>" -c <collection> -n 1 --min-score <x> \\
      --format json --full

at most --concurrency at a time, each stopped after --timeout seconds
with all it started (qmd's launcher runs the CLI that loads the models as
a child process).
The text is read from --text-file (`-` for stdin, UTF-8) and folded to one
line: qmd reads a query of several lines as a typed query document.

Output (stdout, one JSON object):

  {"hits": [{"name": "<collection less the suffix>",
             "collection": "<collection>", "score": <number>,
             "description": "<the brief's description>" | null}],
   "skipped": [{"collection": "<collection>", "reason": "<why>"}]}

  hits     the best hit of each collection that has one at or above
           --min-score, highest score first (ties by collection name),
           the first --top of them. `description` is the `description`
           of the brief the hit's full body holds as YAML, on one line,
           or null when the body is not a brief with one.
  skipped  each queried collection whose query timed out, exited
           non-zero or printed no JSON, in listing order. The other
           collections' hits are kept.

No collection with the suffix is no failure: {"hits": [], "skipped": []}.

verify-collection
-----------------
Prints {"name": "<collection>", "documents": <int> | null}: the `Files:`
count `qmd collection list` gives the collection, 0 when the collection is
not listed, null when it is listed with no count (an older qmd that prints
bare names).

qmd is found on PATH with skf-qmd-classify-collections.py's
_resolve_outside_cwd (a qmd shim in the current folder is never run), and
the listing is read with its parse_collection_list_output. That sibling
script is loaded from this folder when a command runs, so --help needs no
dependency.

Exit codes:
  0  the command ran (the listing was read)
  1  qmd is not on PATH, or `qmd collection list` failed (one line on
     stderr)
  2  usage: a bad argument, or a --text-file that cannot be read
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLASSIFY = HERE / "skf-qmd-classify-collections.py"
LIST_TIMEOUT = 30
KILL_WAIT_SEC = 5  # each wait after a time limit: taskkill, then qmd itself
_FILES_RE = re.compile(r"^\s+Files:\s*(\d+)\s*$")

_SIBLINGS: dict[str, object] = {}


class QmdUnavailable(Exception):
    """qmd is not on PATH, or its collection listing failed."""


def _load(path: Path):
    """A sibling script loaded by its path, once. Loaded when a command runs, so --help needs no dependency."""
    module = _SIBLINGS.get(path.name)
    if module is None:
        spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SIBLINGS[path.name] = module
    return module


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def find_qmd() -> str:
    qmd = _load(CLASSIFY)._resolve_outside_cwd("qmd")
    if qmd is None:
        raise QmdUnavailable("qmd not found on PATH")
    return qmd


def _taskkill() -> str | None:
    """taskkill.exe from the Windows system folder, else from PATH: a PATH that leaves System32 out must not leave
    the CLI qmd started running past the time limit."""
    root = os.environ.get("SystemRoot") or os.environ.get("windir")
    if root:
        candidate = os.path.join(root, "System32", "taskkill.exe")
        if os.path.isfile(candidate):
            return candidate
    return _load(CLASSIFY)._resolve_outside_cwd("taskkill")


def _kill_tree(proc: subprocess.Popen, windows: bool = os.name == "nt") -> None:
    """Kill qmd and everything it started: its launcher runs the CLI that loads the models as a child."""
    try:
        if windows:
            taskkill = _taskkill()
            if taskkill:
                subprocess.run([taskkill, "/F", "/T", "/PID", str(proc.pid)], stdin=subprocess.DEVNULL,
                               capture_output=True, timeout=KILL_WAIT_SEC, check=False)
            proc.kill()
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass


def _run(argv: list[str], timeout: float) -> tuple[int | None, str, str]:
    """Run qmd: (returncode, stdout, stderr), returncode None when it ran past timeout. OSError when it cannot start.

    The call gets its own process group (a POSIX session), so a time limit
    stops the whole tree and a timed-out query loads no model past it.
    Output goes to temporary files, not pipes, so a process left holding
    one cannot block the wait.
    """
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    with tempfile.TemporaryFile() as out_f, tempfile.TemporaryFile() as err_f:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out_f, stderr=err_f, **kwargs)
        try:
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            try:
                proc.wait(timeout=KILL_WAIT_SEC)
            except subprocess.TimeoutExpired:
                pass
            returncode = None
        texts = []
        for handle in (out_f, err_f):
            handle.seek(0)
            texts.append(handle.read().decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n"))
    return returncode, texts[0], texts[1]


def list_collections(qmd: str) -> str:
    """The stdout of `qmd collection list`; QmdUnavailable when it fails."""
    try:
        returncode, stdout, stderr = _run([qmd, "collection", "list"], LIST_TIMEOUT)
    except OSError as exc:
        raise QmdUnavailable(f"qmd collection list failed: {_one_line(str(exc))}") from None
    if returncode is None:
        raise QmdUnavailable(f"qmd collection list timed out after {LIST_TIMEOUT}s")
    if returncode != 0:
        detail = _first_line(stderr) or _first_line(stdout) or "<no output>"
        raise QmdUnavailable(f"qmd collection list exited {returncode}: {detail}")
    return stdout


def collection_names(listing: str) -> list[str]:
    return _load(CLASSIFY).parse_collection_list_output(listing)


def file_counts(listing: str) -> dict[str, int | None]:
    """Collection name -> the `Files:` count its block of the listing gives, None when it gives none."""
    parse = _load(CLASSIFY).parse_collection_list_output
    counts: dict[str, int | None] = {}
    current = None
    for line in listing.splitlines():
        if not line.strip():
            continue
        if not line[0].isspace():
            names = parse(line)
            current = names[0] if names else None
            if current is not None:
                counts.setdefault(current, None)
            continue
        match = _FILES_RE.match(line)
        if match and current is not None:
            counts[current] = int(match.group(1))
    return counts


def _json_rows(stdout: str):
    """The JSON array a `qmd query --format json` call printed, from the first line that opens one, or None."""
    lines = stdout.splitlines(keepends=True)
    for at, line in enumerate(lines):
        if line.lstrip().startswith("["):
            try:
                rows, _ = json.JSONDecoder().raw_decode("".join(lines[at:]).lstrip())
            except json.JSONDecodeError:
                continue
            return rows if isinstance(rows, list) else None
    return None


def brief_description(body) -> str | None:
    """The `description` of the brief a hit's full body holds as YAML, on one line, or None."""
    if not isinstance(body, str) or not body.strip():
        return None
    import yaml

    try:
        for document in yaml.safe_load_all(body):
            if isinstance(document, dict):
                description = document.get("description")
                if isinstance(description, str) and description.strip():
                    return _one_line(description)
                return None
    except yaml.YAMLError:
        return None
    return None


def query_collection(qmd: str, query: str, collection: str, suffix: str, min_score: float,
                     timeout: float) -> tuple[dict | None, dict | None]:
    """(the collection's hit or None, a skipped entry or None)."""
    argv = [qmd, "query", query, "-c", collection, "-n", "1", "--min-score", f"{min_score:g}",
            "--format", "json", "--full"]
    try:
        returncode, stdout, stderr = _run(argv, timeout)
    except OSError as exc:
        return None, {"collection": collection, "reason": _one_line(str(exc)) or type(exc).__name__}
    if returncode is None:
        return None, {"collection": collection, "reason": f"timed out after {timeout:g}s"}
    if returncode != 0:
        detail = _first_line(stderr) or "<no stderr>"
        return None, {"collection": collection, "reason": f"exited {returncode}: {detail}"}
    rows = _json_rows(stdout)
    if rows is None:
        return None, {"collection": collection, "reason": "printed no JSON"}
    scored = [row for row in rows if isinstance(row, dict) and isinstance(row.get("score"), (int, float))
              and not isinstance(row.get("score"), bool) and row["score"] >= min_score]
    if not scored:
        return None, None
    best = max(scored, key=lambda row: row["score"])
    return {"name": collection[:len(collection) - len(suffix)] if suffix else collection,
            "collection": collection, "score": best["score"],
            "description": brief_description(best.get("body"))}, None


def similar(name: str, text: str, suffix: str, cap: int, concurrency: int, timeout: float, min_score: float,
            top: int) -> dict:
    qmd = find_qmd()
    own = f"{name}{suffix}"
    candidates = [c for c in collection_names(list_collections(qmd)) if c.endswith(suffix) and c != own]
    # A name the listing gives twice is queried once.
    swept = list(dict.fromkeys(candidates))[:cap]
    query = _one_line(f"{name} {text}")
    if not swept:
        return {"hits": [], "skipped": []}
    with ThreadPoolExecutor(max_workers=min(concurrency, len(swept))) as pool:
        results = list(pool.map(
            lambda collection: query_collection(qmd, query, collection, suffix, min_score, timeout), swept))
    hits = sorted((hit for hit, _ in results if hit is not None),
                  key=lambda hit: (-hit["score"], hit["collection"]))
    return {"hits": hits[:top], "skipped": [skip for _, skip in results if skip is not None]}


def verify_collection(name: str) -> dict:
    return {"name": name, "documents": file_counts(list_collections(find_qmd())).get(name, 0)}


def _read_text(name: str) -> str:
    """The --text-file text as UTF-8, stdin for `-`."""
    if name == "-":
        stream = getattr(sys.stdin, "buffer", None)
        data = stream.read() if stream is not None else sys.stdin.read().encode("utf-8")
    else:
        with open(name, "rb") as handle:
            data = handle.read()
    return data.decode("utf-8-sig", errors="replace")


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be 1 or more, got {value}")
    return number


def _positive_float(value: str) -> float:
    number = float(value)
    if not number > 0:
        raise argparse.ArgumentTypeError(f"must be above 0, got {value}")
    return number


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-qmd-portfolio-similarity",
        description="Compare a proposed brief with the briefs QMD has indexed (similar), or print the "
                    "document count of one collection (verify-collection).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    near = sub.add_parser("similar", help="print {hits, skipped}: the briefs that look close to a proposed one")
    near.add_argument("--name", required=True, help="the proposed skill name")
    near.add_argument("--text-file", required=True,
                      help="a file holding the intent text, or - for stdin (UTF-8); folded to one line")
    near.add_argument("--suffix", default="-brief", help="the suffix of the collections compared (default -brief)")
    near.add_argument("--cap", type=_positive_int, default=12,
                      help="query at most this many collections, the first ones listed (default 12)")
    near.add_argument("--concurrency", type=_positive_int, default=4,
                      help="run at most this many queries at a time (default 4)")
    near.add_argument("--timeout", type=_positive_float, default=20.0,
                      help="seconds each query may run before it is skipped (default 20)")
    near.add_argument("--min-score", type=float, default=0.6,
                      help="the lowest score a hit may have (default 0.6)")
    near.add_argument("--top", type=_positive_int, default=3, help="print at most this many hits (default 3)")
    verify = sub.add_parser("verify-collection", help="print {name, documents} for one collection")
    verify.add_argument("name", help="the collection name, such as <skill>-brief")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.cmd == "similar":
            try:
                text = _read_text(args.text_file)
            except OSError as exc:
                sys.stderr.write(f"skf-qmd-portfolio-similarity: cannot read --text-file {args.text_file}: "
                                 f"{_one_line(str(exc))}\n")
                return 2
            result = similar(args.name, text, args.suffix, args.cap, args.concurrency, args.timeout,
                             args.min_score, args.top)
        else:
            result = verify_collection(args.name)
    except QmdUnavailable as exc:
        sys.stderr.write(f"skf-qmd-portfolio-similarity: {_one_line(str(exc))}\n")
        return 1
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


def _force_utf8(*streams) -> None:
    """Reconfigure stdout and stderr to UTF-8 with LF line ends, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which cannot print every
    character of a brief's description, and writes CRLF.
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
