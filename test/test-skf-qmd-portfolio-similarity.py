#!/usr/bin/env python3
"""skf-qmd-portfolio-similarity.py: the briefs QMD holds that look close to a proposed one, and a brief
collection's document count.

#1139 (determinism-8): Brief Skill's Deep-tier portfolio check had the model
list the `-brief` collections with awk, run `timeout 20 qmd query` in
batches of about four and merge the top three by score, and the QMD
registration read `qmd status` by eye to verify the embed. `similar` and
`verify-collection` do each in one call. These checks run the helper
against a stand-in `qmd` placed first on PATH, a Python script behind a
POSIX wrapper and a `qmd.cmd`, that answers from a fixture and logs each
call: never the qmd a developer has installed, nor its index.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HELPER = REPO / "src" / "shared" / "scripts" / "skf-qmd-portfolio-similarity.py"

spec = importlib.util.spec_from_file_location("skf_qmd_portfolio_similarity", HELPER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# How long the stand-in sleeps for a query that times out: past `--timeout 1`, and short, so a stand-in a kill
# missed ends soon.
SLEEP = 3
# A child the stand-in starts, as qmd's launcher starts its CLI, writes its marker this long after it starts.
GRANDCHILD = ("import pathlib, sys, time; time.sleep(3); pathlib.Path(sys.argv[1]).write_text('x')")

STUB = '''\
import json
import pathlib
import subprocess
import sys
import time
import uuid

fixture = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
args = sys.argv[2:]
pathlib.Path(fixture["log"], uuid.uuid4().hex + ".json").write_text(json.dumps(args), encoding="utf-8")
if args[:2] == ["collection", "list"]:
    reply = fixture["list"]
elif args[:1] == ["query"] and "-c" in args:
    reply = fixture["query"].get(args[args.index("-c") + 1], {"stdout": "[]\\n"})
else:
    reply = {"stderr": "unexpected call\\n", "exit": 9}
if reply.get("grandchild"):
    subprocess.Popen([sys.executable, "-c", fixture["grandchild"], reply["grandchild"]])
time.sleep(reply.get("sleep", 0))
sys.stdout.buffer.write(reply.get("stdout", "").encode("utf-8"))
sys.stdout.flush()
sys.stderr.buffer.write(reply.get("stderr", "").encode("utf-8"))
sys.stderr.flush()
sys.exit(reply.get("exit", 0))
'''


def _listing(*blocks: tuple[str, int | None]) -> str:
    """`qmd collection list` output as qmd 2.8 prints it: a header, then one block per collection."""
    lines = [f"Collections ({len(blocks)}):", ""]
    for name, files in blocks:
        lines.append(f"{name} (qmd://{name}/)")
        lines.append("  Pattern:  skill-brief.yaml")
        if files is not None:
            lines.append(f"  Files:    {files}")
        lines.append("  Updated:  2h ago")
        lines.append("")
    return "\n".join(lines)


def _brief(description: str | None) -> str:
    """A skill-brief.yaml body, as `qmd query --full` returns it."""
    text = "name: demo\nversion: 1.0.0\nsource_type: source\n"
    if description is not None:
        text += f"description: >-\n  {description}\n  Use when you need it.\n"
    return text + "scope:\n  type: full-library\n"


def _hit(score: float, body: str | None = None) -> dict:
    row = {"docid": "#abc123", "score": score, "file": "qmd://x/skill-brief.yaml", "line": 1, "title": "x"}
    if body is not None:
        row["body"] = body
    return {"stdout": json.dumps([row], indent=2) + "\n"}


class Qmd:
    """A stand-in qmd in its own folder: the fixture it answers from and the calls it logged."""

    def __init__(self, root: Path, listing: str = "", list_exit: int = 0, queries: dict | None = None):
        self.bin = root / "bin"
        self.logs = root / "calls"
        self.project = root / "project"
        for folder in (self.bin, self.logs, self.project):
            folder.mkdir(parents=True, exist_ok=True)
        fixture = root / "fixture.json"
        fixture.write_text(json.dumps({
            "log": str(self.logs),
            "list": {"stdout": listing, "exit": list_exit, "stderr": "database is locked\n" if list_exit else ""},
            "query": queries or {},
            "grandchild": GRANDCHILD,
        }), encoding="utf-8")
        stub = root / "qmd_stub.py"
        stub.write_text(STUB, encoding="utf-8")
        script = self.bin / "qmd"
        script.write_bytes(f"#!/bin/sh\nexec '{sys.executable}' '{stub}' '{fixture}' \"$@\"\n".encode("utf-8"))
        script.chmod(0o755)
        (self.bin / "qmd.cmd").write_bytes(
            f'@echo off\r\n"{sys.executable}" "{stub}" "{fixture}" %*\r\nexit /b %ERRORLEVEL%\r\n'.encode("utf-8"))

    def calls(self) -> list[list[str]]:
        return [json.loads(path.read_text(encoding="utf-8")) for path in self.logs.glob("*.json")]

    def queried(self) -> list[str]:
        return sorted(call[call.index("-c") + 1] for call in self.calls() if call[:1] == ["query"])

    def run(self, *args: str, stdin: str = "", path: Path | None = None) -> subprocess.CompletedProcess:
        env = {**os.environ, "PATH": str(path if path is not None else self.bin)}
        return subprocess.run([sys.executable, str(HELPER), *args], input=stdin.encode("utf-8"), capture_output=True,
                              timeout=120, check=False, env=env, cwd=self.project)


SIMILAR = ("similar", "--name", "demo", "--text-file", "-", "--cap", "12", "--concurrency", "4", "--timeout", "1",
           "--min-score", "0.6", "--top", "3")


def _json(proc: subprocess.CompletedProcess):
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert b"\r\n" not in proc.stdout
    return json.loads(proc.stdout.decode("utf-8"))


# --------------------------------------------------------------------------
# similar
# --------------------------------------------------------------------------


@pytest.fixture
def portfolio(tmp_path) -> Qmd:
    """Fourteen -brief collections, the proposed name's own third, beside collections of other kinds.

    The sweep takes the first twelve -brief collections but `demo-brief`, so `b12` and `b13` stay out, though
    `b13` would score highest. `b04` times out; `b05` exits non-zero and `b06` prints no JSON.
    """
    names = ["b01-brief", "b02-brief", "demo-brief", "b03-brief", "notes", "b04-brief", "b05-brief", "demo-temporal",
             "b06-brief", "b07-brief", "b08-brief", "b09-brief", "b10-brief", "b11-brief", "b12-brief", "b13-brief"]
    queries = {
        "b01-brief": _hit(0.71, _brief("Markdown parsing for agents.")),
        "b02-brief": _hit(0.88, "not: [a brief"),
        "b03-brief": _hit(0.93, _brief("Render   markdown\n  to HTML.")),
        "b04-brief": {**_hit(0.99, _brief("Slow.")), "sleep": SLEEP},
        "b05-brief": {"stderr": "boom\nmore\n", "exit": 2},
        "b06-brief": {"stdout": "No results found.\n"},
        "b07-brief": _hit(0.88, _brief(None)),
        "b08-brief": _hit(0.65, _brief("Low.")),
        "b09-brief": _hit(0.4, _brief("Under the floor.")),  # qmd filters it; the helper does too
        "b10-brief": {"stdout": "[]\n"},
        "b13-brief": _hit(0.97, _brief("Past the cap.")),
        "demo-brief": _hit(1.0, _brief("Its own.")),
    }
    return Qmd(tmp_path, _listing(*[(name, 1) for name in names]), queries=queries)


def test_similar_sweeps_the_cap_and_keeps_the_three_best_past_a_timeout(portfolio):
    started = time.monotonic()
    result = _json(portfolio.run(*SIMILAR, stdin="Parse markdown\n  fast and   safe.\n"))
    assert time.monotonic() - started < 60
    assert result["hits"] == [
        {"name": "b03", "collection": "b03-brief", "score": 0.93, "description": "Render markdown to HTML. Use when "
                                                                                 "you need it."},
        {"name": "b02", "collection": "b02-brief", "score": 0.88, "description": None},
        {"name": "b07", "collection": "b07-brief", "score": 0.88, "description": None},
    ]
    assert result["skipped"] == [
        {"collection": "b04-brief", "reason": "timed out after 1s"},
        {"collection": "b05-brief", "reason": "exited 2: boom"},
        {"collection": "b06-brief", "reason": "printed no JSON"},
    ]
    # Twelve queried, the proposed name's own never, nor a collection of another kind or past the cap.
    assert portfolio.queried() == [f"b{n:02d}-brief" for n in range(1, 13)]


def test_each_query_is_one_line_asks_one_collection_for_its_best_full_hit(portfolio):
    _json(portfolio.run(*SIMILAR, stdin="Parse markdown\n  fast and   safe.\n"))
    queries = [call for call in portfolio.calls() if call[:1] == ["query"]]
    assert len(queries) == 12
    for call in queries:
        assert call[:3] == ["query", "demo Parse markdown fast and safe.", "-c"]
        assert call[4:] == ["-n", "1", "--min-score", "0.6", "--format", "json", "--full"]
    assert [call for call in portfolio.calls() if call[:1] != ["query"]] == [["collection", "list"]]


def test_top_and_min_score_bound_the_hits(portfolio):
    args = list(SIMILAR)
    args[args.index("--top") + 1] = "5"
    args[args.index("--min-score") + 1] = "0.5"
    hits = _json(portfolio.run(*args, stdin="markdown"))["hits"]
    assert [(hit["collection"], hit["score"]) for hit in hits] == [
        ("b03-brief", 0.93), ("b02-brief", 0.88), ("b07-brief", 0.88), ("b01-brief", 0.71), ("b08-brief", 0.65)]


def test_a_text_file_is_read_as_utf8(portfolio, tmp_path):
    path = tmp_path / "intent.txt"
    path.write_bytes("Café menus\r\nin markdown\r\n".encode("utf-8"))
    args = list(SIMILAR)
    args[args.index("--text-file") + 1] = str(path)
    _json(portfolio.run(*args))
    queries = {call[1] for call in portfolio.calls() if call[:1] == ["query"]}
    assert queries == {"demo Café menus in markdown"}


def test_an_unreadable_text_file_is_a_usage_error(portfolio, tmp_path):
    args = list(SIMILAR)
    args[args.index("--text-file") + 1] = str(tmp_path / "missing.txt")
    proc = portfolio.run(*args)
    assert proc.returncode == 2 and proc.stdout == b""
    assert len(proc.stderr.decode("utf-8", "replace").splitlines()) == 1


@pytest.mark.parametrize("listing", [
    pytest.param(_listing(("demo-brief", 1), ("notes", 3), ("demo-temporal", 2)), id="only-its-own"),
    pytest.param("No collections found. Run 'qmd collection add .' to create one.\n", id="no-collection"),
])
def test_an_empty_portfolio_is_no_failure(tmp_path, listing):
    """A first Deep-tier brief has no portfolio to compare: no hit, nothing skipped, no query run."""
    qmd = Qmd(tmp_path, listing)
    assert _json(qmd.run(*SIMILAR, stdin="markdown")) == {"hits": [], "skipped": []}
    assert qmd.queried() == []


@pytest.mark.parametrize("command", [SIMILAR, ("verify-collection", "demo-brief")], ids=["similar", "verify"])
def test_no_qmd_on_path_exits_1_with_one_line(tmp_path, command):
    qmd = Qmd(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    proc = qmd.run(*command, stdin="markdown", path=empty)
    assert proc.returncode == 1 and proc.stdout == b""
    assert proc.stderr.decode("utf-8", "replace").splitlines() == ["skf-qmd-portfolio-similarity: qmd not found on "
                                                                   "PATH"]


@pytest.mark.parametrize("command", [SIMILAR, ("verify-collection", "demo-brief")], ids=["similar", "verify"])
def test_a_failed_listing_exits_1_with_one_line(tmp_path, command):
    qmd = Qmd(tmp_path, list_exit=1)
    proc = qmd.run(*command, stdin="markdown")
    assert proc.returncode == 1 and proc.stdout == b""
    [line] = proc.stderr.decode("utf-8", "replace").splitlines()
    assert line == "skf-qmd-portfolio-similarity: qmd collection list exited 1: database is locked"


def test_a_qmd_shim_in_the_current_folder_is_never_run(tmp_path):
    """The sibling's guard: shutil.which on Windows searches the current folder ahead of PATH."""
    qmd = Qmd(tmp_path, _listing(("b01-brief", 1)))
    proc = subprocess.run([sys.executable, str(HELPER), *SIMILAR], input=b"markdown", capture_output=True,
                          timeout=120, check=False, cwd=qmd.bin, env={**os.environ, "PATH": str(qmd.bin)})
    assert proc.returncode == 1, proc.stdout
    assert qmd.calls() == []


def test_a_timed_out_query_stops_what_it_started(tmp_path):
    """qmd's launcher runs the CLI that loads the models as a child: the time limit kills the whole tree, so no
    model load outlives its query. The marker path is an argument, so a Windows path cannot break the code."""
    marker = tmp_path / "grandchild-survived"
    qmd = Qmd(tmp_path, _listing(("b01-brief", 1)), queries={"b01-brief": {"sleep": 60, "grandchild": str(marker)}})
    started = time.monotonic()
    result = _json(qmd.run(*SIMILAR, stdin="markdown"))
    assert result == {"hits": [], "skipped": [{"collection": "b01-brief", "reason": "timed out after 1s"}]}
    assert time.monotonic() - started < 30
    time.sleep(4)
    assert not marker.exists()


def test_windows_kill_uses_taskkill_tree(monkeypatch):
    calls = []
    classify = mod._load(mod.CLASSIFY)
    monkeypatch.setattr(classify, "_resolve_outside_cwd", lambda name: "taskkill" if name == "taskkill" else None)
    monkeypatch.setattr(mod.subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw.get("timeout"))))

    class Proc:
        pid = 4242
        killed = False

        def kill(self):
            self.killed = True

    proc = Proc()
    monkeypatch.delenv("SystemRoot", raising=False)
    monkeypatch.delenv("windir", raising=False)
    mod._kill_tree(proc, windows=True)
    assert calls == [(["taskkill", "/F", "/T", "/PID", "4242"], mod.KILL_WAIT_SEC)] and proc.killed


def test_windows_kill_finds_taskkill_in_the_system_folder_when_path_lacks_it(monkeypatch, tmp_path):
    """A PATH without System32 (the e2e tests run with PATH set to the fake qmd's folder) still stops the tree."""
    system32 = tmp_path / "System32"
    system32.mkdir()
    (system32 / "taskkill.exe").write_bytes(b"")
    calls = []
    classify = mod._load(mod.CLASSIFY)
    monkeypatch.setattr(classify, "_resolve_outside_cwd", lambda name: None)
    monkeypatch.setattr(mod.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    monkeypatch.setenv("SystemRoot", str(tmp_path))

    class Proc:
        pid = 4242
        killed = False

        def kill(self):
            self.killed = True

    proc = Proc()
    mod._kill_tree(proc, windows=True)
    assert calls == [[str(system32 / "taskkill.exe"), "/F", "/T", "/PID", "4242"]] and proc.killed


def test_queries_run_at_most_concurrency_at_a_time(monkeypatch):
    active, most, lock = [0], [0], threading.Lock()

    def query(qmd, query, collection, suffix, min_score, timeout):
        with lock:
            active[0] += 1
            most[0] = max(most[0], active[0])
        time.sleep(0.05)
        with lock:
            active[0] -= 1
        return {"name": collection[:-6], "collection": collection, "score": 0.7, "description": None}, None

    monkeypatch.setattr(mod, "find_qmd", lambda: "qmd")
    monkeypatch.setattr(mod, "list_collections", lambda qmd: _listing(*[(f"b{n:02d}-brief", 1) for n in range(10)]))
    monkeypatch.setattr(mod, "query_collection", query)
    result = mod.similar("demo", "text", "-brief", 8, 2, 20.0, 0.6, 3)
    assert most[0] == 2
    assert [hit["collection"] for hit in result["hits"]] == ["b00-brief", "b01-brief", "b02-brief"]


# --------------------------------------------------------------------------
# verify-collection
# --------------------------------------------------------------------------


@pytest.mark.parametrize("listing,name,documents", [
    pytest.param(_listing(("other-brief", 4), ("demo-brief", 1)), "demo-brief", 1, id="listed"),
    pytest.param(_listing(("demo-brief", 0)), "demo-brief", 0, id="listed-empty"),
    pytest.param(_listing(("other-brief", 4)), "demo-brief", 0, id="not-listed"),
    pytest.param("No collections found. Run 'qmd collection add .' to create one.\n", "demo-brief", 0, id="none"),
    pytest.param(_listing(("demo-brief", None)), "demo-brief", None, id="no-count"),
    pytest.param("other-brief\ndemo-brief\n", "demo-brief", None, id="bare-names"),
])
def test_verify_collection_prints_the_listed_count(tmp_path, listing, name, documents):
    qmd = Qmd(tmp_path, listing)
    assert _json(qmd.run("verify-collection", name)) == {"name": name, "documents": documents}
    assert qmd.calls() == [["collection", "list"]]


def test_a_count_belongs_to_its_own_block():
    listing = _listing(("demo-brief", None), ("next-brief", 7))
    assert mod.file_counts(listing) == {"demo-brief": None, "next-brief": 7}


# --------------------------------------------------------------------------
# The description a hit's body holds
# --------------------------------------------------------------------------


def test_brief_description_reads_the_first_yaml_document():
    assert mod.brief_description("name: x\ndescription: |\n  Two\n  lines.\n") == "Two lines."
    assert mod.brief_description("name: x\ndescription: Closed by SKF 1.x.\n---\n") == "Closed by SKF 1.x."
    for body in (None, "", "name: x\n", "- a list\n", "description: [1, 2]\n", "a: [unclosed\n"):
        assert mod.brief_description(body) is None, body
