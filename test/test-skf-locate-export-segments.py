#!/usr/bin/env python3
"""Tests for locate-export-segments.py and the async/sync check that reads it (#582).

coherence-check.md §2.5 used to grep each description for `\\basync\\b` and
raise a High finding on a hit, so a sync export described beside its paired
async variant failed the check. The script now reports facts only (where the
skill describes each export, each example call to it and whether the call
awaits it) and the model decides what a description asserts. These tests
cover the script's facts: which calls are awaited, which lines declare
rather than call, what comments, strings and data blocks hide, which prose
describes an export, qualified names, line numbers, and the CLI contract.
The --inventory input reads the validated inventory file coverage-check
writes and keeps its function and method names. The last section pins the
§2.5 prose that calls it.

#783: a call's `directlyAwaited` holds only when the await applies to the
call itself, so §2.5's sync rule no longer raises a High finding for a sync
export used as an argument of an awaited call or under a chained member.

#842: a method given with its `owner` counts only the calls on that owner or
on a variable the same block binds to it, so `cognee.config.get(...)` is no
call of `cognee.agents.get`, and an argument list of annotated parameters is
a signature, not an unawaited call. #844: --inventory reads each class-like
entry's `methods`, tied to its class, so §2.5 checks class methods too.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_SKILL = REPO_ROOT / "src" / "skf-test-skill"
SCRIPT_PATH = TEST_SKILL / "scripts" / "locate-export-segments.py"
COHERENCE = TEST_SKILL / "references" / "coherence-check.md"
SCANNER_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-scan-skill-md-structure.py"

spec = importlib.util.spec_from_file_location("locate_export_segments", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
locate = mod.locate

FRONTMATTER = "---\nname: demo\ndescription: Demo skill. Use when testing.\n---\n\n# demo\n\n"
EXPORT_KEYS = {"name", "owner", "descriptionCount", "descriptions", "calls", "callCount", "awaitedCount",
               "directlyAwaitedCount", "unverifiedCalls", "otherReceiverCount"}
CALL_KEYS = {"file", "line", "fence", "language", "receiver", "receiverMatch", "awaited", "directlyAwaited",
             "awaitedVia", "enclosingCallee", "chainedMember", "text"}
DESCRIPTION_KEYS = {"file", "line", "endLine", "kind", "section", "header", "text", "truncated"}


def _skill(tmp_path: Path, body: str, refs: dict[str, str] | None = None) -> Path:
    """A skill package with SKILL.md and references/, written as LF bytes."""
    root = tmp_path / "skill"
    root.mkdir()
    (root / "SKILL.md").write_bytes((FRONTMATTER + body).encode("utf-8"))
    for rel, text in (refs or {}).items():
        path = root / "references" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    return root


def _run(root: Path, names: list[str]) -> dict:
    out = locate({"names": names, "skillPackagePath": str(root)})
    assert "error" not in out, out
    for export in out["exports"]:
        for call in export["calls"]:
            _assert_await_facts_agree(call)
    return out


def _assert_await_facts_agree(call: dict) -> None:
    """#783's invariant, held on every call each fixture of this suite produces: a direct await is an
    await, `awaitedVia` agrees with both flags, and only an argument or a runner names an enclosing callee."""
    assert not call["directlyAwaited"] or call["awaited"], call
    assert call["awaited"] == (call["awaitedVia"] is not None), call
    assert call["directlyAwaited"] == (call["awaitedVia"] == "direct"), call
    assert (call["enclosingCallee"] is not None) == (call["awaitedVia"] in ("argument", "runner")), call


def _export(out: dict, name: str) -> dict:
    found = [e for e in out["exports"] if e["name"] == name]
    assert len(found) == 1, f"{name} not in exports: {out['notCalled']}"
    return found[0]


def _block(language: str, code: str) -> str:
    return f"```{language}\n{code}\n```\n"


def _calls(tmp_path: Path, language: str, code: str, name: str = "fetchData") -> list[dict]:
    out = _run(_skill(tmp_path, _block(language, code)), [name])
    return _export(out, name)["calls"] if out["exports"] else []


def _signatures(tmp_path: Path, language: str, code: str, name: str = "fetchData") -> list[str]:
    root = _skill(tmp_path, _block(language, code) + _block(language, f"{name}(x)"))
    return [d["text"] for d in _export(_run(root, [name]), name)["descriptions"] if d["kind"] == "signature"]


# --------------------------------------------------------------------------
# #582: paired sync and async APIs are reported as facts, never judged
# --------------------------------------------------------------------------


PAIRED = """## Key API Summary

| Export | Kind | Purpose |
|---|---|---|
| `readFile` | async fn | Read a file |
| `readFileSync` | fn | The sync counterpart of the async `readFile` |

## Quick Start

```ts
const text = await readFile("a.txt");
const again = readFileSync("b.txt");
```
"""


def test_paired_sync_api_keeps_its_own_facts(tmp_path):
    """The #582 case: `async` in readFileSync's row is evidence, not a verdict."""
    out = _run(_skill(tmp_path, PAIRED), ["readFile", "readFileSync"])
    sync = _export(out, "readFileSync")
    assert [d["text"] for d in sync["descriptions"]] == [
        "| `readFileSync` | fn | The sync counterpart of the async `readFile` |"]
    assert sync["descriptions"][0]["header"] == "| Export | Kind | Purpose |"
    assert [(c["awaited"], c["text"]) for c in sync["calls"]] == [(False, 'const again = readFileSync("b.txt");')]
    assert sync["awaitedCount"] == 0
    both = _export(out, "readFile")
    assert both["awaitedCount"] == both["callCount"] == 1
    # The row naming readFile in its purpose text describes readFile too.
    assert len(both["descriptions"]) == 2


def test_output_holds_facts_and_no_verdict(tmp_path):
    out = _run(_skill(tmp_path, PAIRED), ["readFile", "readFileSync", "absent"])
    assert set(out) == {"skillPackagePath", "files", "exports", "notCalled", "notCalledUnverified", "summary"}
    assert out["notCalledUnverified"] == []
    for export in out["exports"]:
        assert set(export) == EXPORT_KEYS
        assert all(set(c) == CALL_KEYS for c in export["calls"])
        assert all(set(d) == DESCRIPTION_KEYS for d in export["descriptions"])
    assert out["notCalled"] == ["absent"]
    assert out["summary"] == {"names": 3, "called": 2, "notCalled": 1}


# --------------------------------------------------------------------------
# Awaited or not
# --------------------------------------------------------------------------


@pytest.mark.parametrize("language, code", [
    ("ts", "const d = await fetchData(url);"),
    ("ts", "const d = await client.api.fetchData(url);"),
    ("ts", "const d = await client\n  .fetchData(url);"),
    ("python", "d = await (fetchData(url))"),
    ("rust", "let d = fetchData(url).await?;"),
    ("rust", "let d = client.fetchData(url)\n    .await;"),
    ("ts", "await Promise.all([fetchData(a), other(b)]);"),
    ("ts", "await Promise.all(urls.map((u) => fetchData(u)));"),
    ("python", "rows = await asyncio.gather(fetchData(a), fetchData(b))"),
    ("python", "asyncio.run(fetchData(url))"),
    ("python", "loop.run_until_complete(fetchData(url))"),
    ("rust", "rt.block_on(fetchData(url));"),
    ("python", "async for row in fetchData(url):\n    print(row)"),
    ("python", "async with fetchData(url) as stream:\n    pass"),
    ("python", "async with a(), fetchData(url) as stream:\n    pass"),
    ("ts", "for await (const row of fetchData(url)) {\n  console.log(row);\n}"),
    ("cs", "await foreach (var row in FetchData(url)) { }"),
    ("swift", "let d = try await fetchData(url)"),
], ids=["await", "await-receiver", "await-fluent-newline", "await-grouping", "rust-postfix",
        "rust-postfix-newline", "promise-all", "promise-all-map", "gather", "asyncio-run",
        "run-until-complete", "block-on", "async-for", "async-with", "async-with-second",
        "for-await", "await-foreach", "swift-try-await"])
def test_awaited_calls(tmp_path, language, code):
    name = "FetchData" if language == "cs" else "fetchData"
    calls = _calls(tmp_path, language, code, name)
    assert calls and all(c["awaited"] for c in calls), calls


@pytest.mark.parametrize("language, code, member", [
    ("ts", "const d = fetchData(url);", None),
    ("python", "d = fetchData(url)", None),
    ("ts", "await run(() => {\n  fetchData(url);\n});", None),
    ("ts", "setTimeout(() => fetchData(url), 10);", None),
    ("ts", "fetchData(url).then((d) => use(d));", "then"),
    ("ts", "fetchData(url)\n  .catch(report);", "catch"),
    ("java", "Data d = client.fetchData(url).join();", "join"),
    ("ts", "void fetchData(url);", None),
    ("ts", "if (await ready()) {\n  fetchData(url);\n}", None),
], ids=["plain", "plain-python", "callback-body", "callback-arrow-unawaited", "then", "catch-newline",
        "java-join", "void", "after-awaited-condition"])
def test_unawaited_calls(tmp_path, language, code, member):
    calls = _calls(tmp_path, language, code)
    assert len(calls) == 1
    assert calls[0]["awaited"] is False
    assert calls[0]["chainedMember"] == member


def test_awaited_count_counts_each_call(tmp_path):
    code = "const a = await fetchData(1);\nconst b = fetchData(2);\nawait Promise.all([fetchData(3)]);"
    export = _export(_run(_skill(tmp_path, _block("ts", code)), ["fetchData"]), "fetchData")
    assert (export["callCount"], export["awaitedCount"]) == (3, 2)
    # FRONTMATTER fills lines 1 to 7, so the fence is line 8.
    assert [c["line"] for c in export["calls"]] == [9, 10, 11]
    assert {c["fence"] for c in export["calls"]} == {8}


# --------------------------------------------------------------------------
# #783: directlyAwaited and awaitedVia, how a call is awaited
# --------------------------------------------------------------------------


@pytest.mark.parametrize("language, code, name, via, callee", [
    ("python", 'await coco.mount(coco.component_subpath("p", f), g)', "component_subpath", "argument", "coco.mount"),
    ("python", "d = await other(fetchData(a))", "fetchData", "argument", "other"),
    ("python", "rows = await asyncio.gather(fetchData(a))", "fetchData", "argument", "asyncio.gather"),
    ("python", "rows = await asyncio.gather(\n    fetchData(a),\n    other(b),\n)", "fetchData", "argument",
     "asyncio.gather"),
    ("python", "rows = await asyncio \\\n    .gather(fetchData(a))", "fetchData", "argument", "asyncio.gather"),
    ("python", "done, _ = await asyncio.wait([fetchData(a)])", "fetchData", "argument", "asyncio.wait"),
    ("ts", "await Promise.all([fetchData(a), other(b)]);", "fetchData", "argument", "Promise.all"),
    ("python", "asyncio.run(fetchData(url))", "fetchData", "runner", "asyncio.run"),
    ("python", "loop.run_until_complete(\n    fetchData(url)\n)", "fetchData", "runner", "loop.run_until_complete"),
    ("rust", "rt.block_on(fetchData(url));", "fetchData", "runner", "rt.block_on"),
    ("python", "async with fetchData(url) as stream:\n    pass", "fetchData", "consumer", None),
], ids=["argument-of-awaited-call", "argument", "gather", "gather-multiline", "gather-backslash", "wait",
        "promise-all", "asyncio-run", "run-until-complete-multiline", "block-on", "async-consumer"])
def test_awaited_through_another_call_is_not_direct(tmp_path, language, code, name, via, callee):
    """A call in the arguments of an awaited call or of a runner, and one an async loop or context manager
    consumes, is awaited but never directly; `enclosingCallee` names the call around an argument, on any line,
    so §2.5 can tell `asyncio.gather` from `Promise.all` (#783)."""
    out = _run(_skill(tmp_path, _block(language, code)), [name])
    export = _export(out, name)
    assert [(c["awaited"], c["directlyAwaited"], c["awaitedVia"], c["enclosingCallee"])
            for c in export["calls"]] == [(True, False, via, callee)]
    assert (export["awaitedCount"], export["directlyAwaitedCount"]) == (1, 0)


@pytest.mark.parametrize("language, code, name, member", [
    ("python", "v = await coco.use_context(E).embed(t)", "use_context", "embed"),
    ("ts", 'const docs = await db.collection("x").find({}).toArray();', "collection", "find"),
    ("python", "v = await (use_context(E).embed(t))", "use_context", "embed"),
    ("ts", "const v = await use_context(e)!.embed(t);", "use_context", "embed"),
    ("python", "v = await coco.use_context(E) \\\n    .embed(t)", "use_context", "embed"),
    ("python", "v = await \\\n    coco.use_context(E).embed(t)", "use_context", "embed"),
    ("ts", "const v = await fetchData(x)[0];", "fetchData", None),
    ("ts", "const v = await fetchData(c)(r);", "fetchData", None),
    ("ts", "const v = await fetchData(x)?.[0];", "fetchData", None),
    ("ts", "const v = await fetchData(x)?.(r);", "fetchData", None),
    ("python", "v = await fetchData(x) \\\n    [0]", "fetchData", None),
    ("ts", "const v = await (fetchData(x))[0];", "fetchData", None),
    ("ts", "const v = await (fetchData(x))(y);", "fetchData", None),
    ("ts", "const v = await (fetchData(x))\n  .embed(t);", "fetchData", None),
    ("python", "d = await (fetchData(url)).value", "fetchData", None),
    ("python", "d = await (fetchData(a) or other(b))", "fetchData", None),
], ids=["python-chain", "ts-chain", "grouped-chain", "ts-non-null-member", "backslash-before-member",
        "backslash-after-await", "subscript", "call", "optional-subscript", "optional-call", "backslash-subscript",
        "grouped-subscript", "grouped-call", "grouped-member-newline", "grouped-member", "grouped-with-other"])
def test_awaited_through_a_chain_is_not_direct(tmp_path, language, code, name, member):
    """The await applies to a member, subscript or call applied to the call's result, or to a group around the
    call, so it is not the call's own (#783)."""
    calls = _calls(tmp_path, language, code, name)
    assert [(c["awaited"], c["directlyAwaited"], c["awaitedVia"], c["chainedMember"]) for c in calls] == [
        (True, False, "chain", member)]


@pytest.mark.parametrize("language, code", [
    ("ts", "const d = await fetchData(url);"),
    ("ts", "const d = await client.api.fetchData(url);"),
    ("ts", "const d = await client\n  .fetchData(url);"),
    ("python", "d = await \\\n    fetchData(url)"),
    ("python", "d = await (fetchData(url))"),
    ("python", "d = await ( fetchData(url) )\nprint(d)"),
    ("ts", "const d = await ((fetchData(url)));"),
    ("ts", "const d = await (fetchData(url) as Data);"),
    ("ts", "const d = await (fetchData(url)!);"),
    ("ts", "use(await (fetchData(url)), 1);"),
    ("rust", "let d = fetchData(url).await?;"),
    ("rust", "let d = client.fetchData(url)\n    .await;"),
    ("rust", "let d = fetchData(url)?.await;"),
    ("swift", "let d = try await fetchData(url)"),
    ("ts", "await fetchData(url).then((d) => use(d));"),
    ("ts", "await fetchData(url).catch(report);"),
    ("ts", "await fetchData(url).finally(done);"),
    ("cs", "var d = await FetchData(url).ConfigureAwait(false);"),
], ids=["await", "await-receiver", "await-fluent-newline", "await-backslash", "await-grouping",
        "await-grouping-spaced", "await-nested-groups", "await-group-as", "await-group-non-null",
        "await-group-in-arguments", "rust-postfix", "rust-postfix-newline", "rust-try-postfix", "swift-try-await",
        "then", "catch", "finally", "configure-await"])
def test_directly_awaited_calls(tmp_path, language, code):
    """A member that waits for an awaitable (`then`, `ConfigureAwait`) under `await` shows the call returns
    one, so the await counts as the call's own."""
    name = "FetchData" if language == "cs" else "fetchData"
    calls = _calls(tmp_path, language, code, name)
    assert [(c["awaited"], c["directlyAwaited"], c["awaitedVia"], c["enclosingCallee"]) for c in calls] == [
        (True, True, "direct", None)]


@pytest.mark.parametrize("language, code", [
    ("ts", "const d = fetchData(url);"),
    ("ts", "return fetchData(url).then((d) => use(d));"),
    ("cs", "var t = FetchData(url).ConfigureAwait(false);"),
    ("python", "task = asyncio.create_task(fetchData(url))"),
], ids=["plain", "then-unawaited", "configure-await-unawaited", "create-task"])
def test_unawaited_calls_have_no_via(tmp_path, language, code):
    name = "FetchData" if language == "cs" else "fetchData"
    calls = _calls(tmp_path, language, code, name)
    assert [(c["awaited"], c["directlyAwaited"], c["awaitedVia"], c["enclosingCallee"]) for c in calls] == [
        (False, False, None, None)]


def test_directly_awaited_count_counts_only_direct_calls(tmp_path):
    code = "a = await fetchData(1)\nb = await asyncio.gather(fetchData(2))\nc = fetchData(3)"
    export = _export(_run(_skill(tmp_path, _block("python", code)), ["fetchData"]), "fetchData")
    assert [c["directlyAwaited"] for c in export["calls"]] == [True, False, False]
    assert (export["callCount"], export["awaitedCount"], export["directlyAwaitedCount"]) == (3, 2, 1)


# --------------------------------------------------------------------------
# Declarations are signatures, never calls
# --------------------------------------------------------------------------


@pytest.mark.parametrize("language, line", [
    ("python", "def fetchData(url):"),
    ("python", "async def fetchData(url):"),
    ("ts", "function fetchData(url) {"),
    ("ts", "export async function fetchData(url: string): Promise<Data> {"),
    ("ts", "export default async function fetchData(url) {"),
    ("js", "function* fetchData(url) {"),
    ("ts", "  fetchData(url: string): Promise<Data>;"),
    ("ts", "  async fetchData(url) {"),
    ("ts", "  fetchData(url) {"),
    ("ts", "  static fetchData(url) {"),
    ("rust", "pub async fn fetchData(url: &str) -> Data {"),
    ("go", "func fetchData(url string) (Data, error) {"),
    ("go", "func (c *Client) fetchData(url string) error {"),
    ("java", "public CompletableFuture<Data> fetchData(String url) {"),
    ("java", "public static void fetchData(String url) {"),
    ("java", "String[] fetchData(String url) {"),
    ("cs", "public async Task<Data> fetchData(string url) {"),
    ("kotlin", "suspend fun fetchData(url: String): Data {"),
    ("swift", "public func fetchData(url: URL) async throws -> Data {"),
    ("python", "fetchData(url: str) -> Data"),
    ("", "Promise<Data> fetchData(url)"),
], ids=["py-def", "py-async-def", "js-function", "ts-export-async", "ts-export-default", "js-generator",
        "ts-interface-signature", "ts-async-method", "ts-method-shorthand", "ts-static-method",
        "rust-pub-async-fn", "go-func", "go-receiver", "java-generic-return", "java-void", "java-array-return",
        "cs-task", "kotlin-suspend", "swift-func", "doc-signature-arrow", "untagged-typed"])
def test_declarations_are_signatures(tmp_path, language, line):
    assert _signatures(tmp_path, language, line) == [line.strip()]


@pytest.mark.parametrize("language, code", [
    ("ts", "const x = a * fetchData(url);"),
    ("python", "if limit > fetchData(url):\n    pass"),
    ("python", "return fetchData(url)"),
    ("ts", "const x = cond ? fetchData(url) : null;"),
    ("kotlin", "fetchData(url) { data -> show(data) }"),
    ("python", "@fetchData(retries=3)\ndef handler():\n    pass"),
    ("go", "x := fetchData(url)"),
    ("go", "go fetchData(url)"),
], ids=["multiplication", "comparison", "return", "ternary", "kotlin-trailing-lambda", "decorator",
        "go-short-assign", "go-goroutine"])
def test_calls_that_look_like_declarations(tmp_path, language, code):
    assert len(_calls(tmp_path, language, code)) == 1


def test_declaration_of_a_qualified_name_matches_its_last_part(tmp_path):
    code = "async def add(data, dataset_name='main'):\n    ...\n\nawait cognee.add(data)\nitems.add(x)"
    export = _export(_run(_skill(tmp_path, _block("python", code)), ["cognee.add"]), "cognee.add")
    assert [d["text"] for d in export["descriptions"] if d["kind"] == "signature"] == [
        "async def add(data, dataset_name='main'):"]
    # Only the qualified call counts: `items.add(x)` is another object's method.
    assert [c["text"] for c in export["calls"]] == ["await cognee.add(data)"]


@pytest.mark.parametrize("language, code, name", [
    ("python", "get(key: str, reveal_secrets: bool = False)", "get"),
    ("python", 'add(data, name: str = "main")', "add"),
    ("python", "cognee.config.get(key: str, reveal_secrets: bool = False)", "get"),
    ("python", "search(*args: Any, **kwargs: Any)", "search"),
    ("python", "search(\n    query: str,\n    top_k: int = 10,\n)", "search"),
    ("ts", "search(query: string, opts?: Options)", "search"),
    ("ts", "search(...terms: string[])", "search"),
    ("kotlin", "search(query: String)", "search"),
    ("scala", "search(query: String)", "search"),
], ids=["py-annotated", "py-second-annotated", "py-receiver", "py-star-args", "py-multiline", "ts-optional",
        "ts-rest", "kotlin", "scala"])
def test_annotated_parameter_lists_are_signatures(tmp_path, language, code, name):
    """#842: a signature line that lists annotated parameters with no return type after it declares the name,
    with or without a receiver: it is never an unawaited call."""
    assert _signatures(tmp_path, language, code, name) == [code.split("\n")[0]]


@pytest.mark.parametrize("language, code", [
    ("python", "fetchData(lambda x: x)"),
    ("python", "fetchData(lambda: 0)"),
    ("python", "fetchData(lambda a, b: a + b)"),
    ("python", "fetchData(items, key=lambda k, v: v)"),
    ("ts", "fetchData(dev ? 'x' : y);"),
    ("ts", "fetchData(dev?'x':y);"),
    ("python", "fetchData(x := 1)"),
    ("python", 'fetchData(url, headers={"a": "b"}, rows=items[1:2])'),
    ("ts", "const x = cond ? fetchData(a) : b;"),
    ("ts", "fetchData(cond ? a : b);"),
    ("ts", "fetchData((req: Request) => req.url);"),
    ("kotlin", "fetchData(a ?: b)"),
    ("kotlin", "fetchData(a::b)"),
    ("kotlin", "fetchData(object : Listener {\n    override fun done() {}\n})"),
    ("scala", "fetchData(xs: _*)"),
    ("scala", "val f = fetchData(1, _: Int)"),
    ("swift", "fetchData(id: 1)"),
    ("cs", "fetchData(id: 1);"),
    ("dart", "fetchData(id: 1);"),
    ("", "fetchData(id: 1)"),
], ids=["lambda-param", "lambda", "lambda-two-params", "lambda-keyword", "ternary-string", "ternary-tight",
        "walrus", "dict-and-slice", "ternary-around", "ternary-inside", "typed-arrow",
        "kotlin-elvis", "kotlin-reference", "kotlin-anonymous-object", "scala-varargs", "scala-typed-placeholder",
        "swift-named", "cs-named", "dart-named", "untagged"])
def test_arguments_that_look_annotated_stay_calls(tmp_path, language, code):
    assert len(_calls(tmp_path, language, code)) == 1


def test_rust_path_names(tmp_path):
    code = "let store = Store::load(path).await?;\nimpl Store {\n    pub async fn load(path: &Path) -> Self { todo!() }\n}"
    export = _export(_run(_skill(tmp_path, _block("rust", code)), ["Store::load"]), "Store::load")
    assert [(c["awaited"], c["text"]) for c in export["calls"]] == [(True, "let store = Store::load(path).await?;")]
    assert [d["text"] for d in export["descriptions"]] == ["pub async fn load(path: &Path) -> Self { todo!() }"]


# --------------------------------------------------------------------------
# #842, #844: a method is called on its owner
# --------------------------------------------------------------------------


def _locate_methods(root: Path, methods: list[tuple[str, str]], owners: list[str] | None = None,
                    names: list[str] | None = None) -> dict:
    """locate() with `methods` given as (owner, name) pairs."""
    out = locate({"names": names or [], "methods": [{"name": n, "owner": o} for o, n in methods],
                  "owners": owners or [], "skillPackagePath": str(root)})
    assert "error" not in out, out
    for export in out["exports"]:
        for call in export["calls"] + export["unverifiedCalls"]:
            _assert_await_facts_agree(call)
    return out


def _method(out: dict, owner: str, name: str) -> dict:
    found = [e for e in out["exports"] if (e["owner"], e["name"]) == (owner, name)]
    assert len(found) == 1, f"{owner}.{name} not in exports: {out['notCalled']}"
    return found[0]


COGNEE = """agent = await cognee.agents.get(agent_id)
cognee.config.get("llm_model")
value = settings.get("x")
get("y")"""


def test_method_calls_need_the_owners_receiver(tmp_path):
    """#842: only the call on `agents` is a call of `agents.get`. Another owner's `get` is no call of it, and a
    receiver nothing ties to the owner, or none at all, gives an unverified call, never a counted one."""
    out = _locate_methods(_skill(tmp_path, _block("python", COGNEE)), [("agents", "get")], owners=["agents", "config"])
    export = _method(out, "agents", "get")
    assert [(c["receiver"], c["receiverMatch"], c["awaited"]) for c in export["calls"]] == [
        ("cognee.agents", "owner", True)]
    assert [(c["receiver"], c["receiverMatch"], c["text"]) for c in export["unverifiedCalls"]] == [
        ("settings", "unknown", 'value = settings.get("x")'), (None, "unknown", 'get("y")')]
    assert export["otherReceiverCount"] == 1
    assert export["callCount"] == export["awaitedCount"] == 1


def test_a_call_on_another_namespace_is_not_the_methods(tmp_path):
    """#842's cognee config.md regression: `cognee.config.get(key: str, ...)` is neither a call nor a signature of
    `agents.get`, and nor is a free `def get(` outside a class body of the owner."""
    body = (_block("python", "cognee.config.get(key: str, reveal_secrets: bool = False)")
            + _block("python", "async def get(agent_id: str) -> Agent:\n    ...")
            + _block("python", "agent = await cognee.agents.get(agent_id)"))
    export = _method(_locate_methods(_skill(tmp_path, body), [("agents", "get")], owners=["config"]), "agents", "get")
    assert [c["text"] for c in export["calls"]] == ["agent = await cognee.agents.get(agent_id)"]
    assert [d for d in export["descriptions"] if d["kind"] == "signature"] == []
    assert (export["unverifiedCalls"], export["otherReceiverCount"]) == ([], 0)


ANCHOR = _block("python", "UuidGenerator.next_uuid()")


@pytest.mark.parametrize("language, code", [
    ("python", "class UuidGenerator:\n    async def next_uuid(self, dep=None) -> uuid.UUID:\n        ..."),
    ("python", "class UuidGenerator(Base):\n    @property\n    def seed(self):\n        ...\n\n"
               "    async def next_uuid(self, dep=None):\n        ..."),
    ("ts", "class UuidGenerator {\n  async next_uuid(dep?: string): Promise<string> {\n    return x;\n  }\n}"),
    ("ts", "interface UuidGenerator {\n  next_uuid(dep?: string): Promise<string>;\n}"),
    ("rust", "impl UuidGenerator {\n    pub async fn next_uuid(&self) -> Uuid { todo!() }\n}"),
    ("go", "func (g *UuidGenerator) next_uuid(dep string) uuid.UUID {\n\treturn uuid.New()\n}"),
    ("python", "coco.UuidGenerator.next_uuid(self, dep=None) -> uuid.UUID"),
], ids=["python-class", "python-class-later-method", "ts-class", "ts-interface", "rust-impl", "go-receiver",
        "on-the-owner"])
def test_a_declaration_of_the_owners_method_is_its_signature(tmp_path, language, code):
    """A declaration is an owned method's inside a class body of the owner, on a Go receiver of its type, or on
    the owner itself."""
    root = _skill(tmp_path, _block(language, code) + ANCHOR)
    export = _method(_locate_methods(root, [("UuidGenerator", "next_uuid")]), "UuidGenerator", "next_uuid")
    line = next(line.strip() for line in code.split("\n") if "next_uuid" in line)
    assert [d["text"] for d in export["descriptions"] if d["kind"] == "signature"] == [line]


@pytest.mark.parametrize("language, code", [
    ("python", "async def next_uuid(self, dep=None) -> uuid.UUID:\n    ..."),
    ("python", "class IdGenerator:\n    async def next_uuid(self) -> int:\n        ..."),
    ("python", "class UuidGenerator:\n    class Inner:\n        def next_uuid(self) -> int:\n            ..."),
    ("python", "class UuidGenerator:\n    pass\n\ndef next_uuid(dep=None) -> str:\n    ..."),
    ("ts", "class IdGenerator {\n  async next_uuid(): Promise<number> {\n    return 1;\n  }\n}"),
    ("go", "func (g *IdGenerator) next_uuid() int {\n\treturn 0\n}"),
    ("python", "other.next_uuid(self, dep=None) -> uuid.UUID"),
], ids=["free-function", "another-class", "inner-class", "after-the-class", "ts-another-class", "go-another-receiver",
        "another-receiver"])
def test_a_declaration_elsewhere_is_not_the_owners(tmp_path, language, code):
    root = _skill(tmp_path, _block(language, code) + ANCHOR)
    export = _method(_locate_methods(root, [("UuidGenerator", "next_uuid")]), "UuidGenerator", "next_uuid")
    assert [d for d in export["descriptions"] if d["kind"] == "signature"] == []


@pytest.mark.parametrize("language, code, match", [
    ("python", "gen = UuidGenerator()\nuid = gen.next_uuid()", "bound"),
    ("python", "def make(id_gen: UuidGenerator):\n    return id_gen.next_uuid()", "bound"),
    ("python", "with UuidGenerator() as gen:\n    uid = gen.next_uuid()", "bound"),
    ("python", "async with coco.UuidGenerator(seed=1) as gen:\n    uid = gen.next_uuid()", "bound"),
    ("python", "gen = await UuidGenerator(seed)\nuid = gen.next_uuid()", "bound"),
    ("ts", "const gen = new UuidGenerator();\nconst uid = gen.next_uuid();", "bound"),
    ("ts", "let gen: UuidGenerator;\nconst uid = gen!.next_uuid();", "bound"),
    ("kotlin", "val gen = UuidGenerator()\nval uid = gen!!.next_uuid()", "bound"),
    ("java", "UuidGenerator gen = factory.make();\nUUID uid = gen.next_uuid();", "bound"),
    ("cs", "UuidGenerator gen = Make();\nvar uid = gen.next_uuid();", "bound"),
    ("rust", "let gen = UuidGenerator::new();\nlet uid = gen.next_uuid();", "bound"),
    ("ruby", "gen = UuidGenerator.new\nuid = gen.next_uuid()", "bound"),
    ("go", "gen := &coco.UuidGenerator{}\nuid := gen.next_uuid()", "bound"),
    ("go", "var gen UuidGenerator\nuid := gen.next_uuid()", "bound"),
    ("go", "var gen *UuidGenerator\nuid := gen.next_uuid()", "bound"),
    ("python", "uid = coco.UuidGenerator(seed=1).next_uuid()", "owner"),
    ("python", "uid = coco.UuidGenerator.next_uuid()", "owner"),
    ("python", "uid = uuidgenerator.next_uuid()", "owner"),
    ("rust", "let uid = UuidGenerator::new().next_uuid();", "owner"),
    ("ruby", "uid = UuidGenerator.new.next_uuid()", "owner"),
    ("python", "gen = await coco.UuidGenerator.create()\nuid = gen.next_uuid()", "unknown"),
    ("python", "gen = UuidGenerator().with_seed(1)\nuid = gen.next_uuid()", "unknown"),
    ("python", "make(gen=UuidGenerator())\nuid = gen.next_uuid()", "unknown"),
    ("python", "def make(seed, gen=UuidGenerator()):\n    return gen.next_uuid()", "unknown"),
    ("python", "gen = UuidGenerator(); uid = gen.next_uuid()", "unknown"),
    ("python", "uid = gen.next_uuid()\ngen = UuidGenerator()", "unknown"),
    ("python", "gen = UuidGenerator()\ngen = make()\nuid = gen.next_uuid()", "unknown"),
    ("python", "uid = self.gen.next_uuid()", "unknown"),
    ("python", "gen = MyUuidGenerator()\nuid = gen.next_uuid()", "unknown"),
    ("python", "gens = [UuidGenerator()]\nuid = gens[0].next_uuid()", "unknown"),
    ("python", "uid = next_uuid()", "unknown"),
], ids=["assigned", "annotated-parameter", "with-as", "async-with-as", "awaited-constructor", "ts-new",
        "ts-annotated", "kotlin-non-null", "java-typed", "cs-typed", "rust-new", "ruby-new", "go-struct-literal",
        "go-var", "go-var-pointer", "owner-call", "owner-member", "owner-any-case", "rust-new-chain",
        "ruby-new-chain", "member-call-result", "member-of-the-new-object", "keyword-argument",
        "parameter-default", "same-line", "bound-after-the-call", "rebound-to-a-call", "self-attribute",
        "longer-class-name", "subscript", "no-receiver"])
def test_bound_receiver(tmp_path, language, code, match):
    """A receiver is tied to the owner when it names the owner, or when it is one identifier whose last binding on
    a line before the call is a constructor-like form of the owner. Any other receiver, or none, is unknown."""
    out = _locate_methods(_skill(tmp_path, _block(language, code) + ANCHOR), [("UuidGenerator", "next_uuid")])
    export = _method(out, "UuidGenerator", "next_uuid")
    assert [c["receiverMatch"] for c in export["calls"]] == ([] if match == "unknown" else [match]) + ["owner"]
    assert [c["receiverMatch"] for c in export["unverifiedCalls"]] == (["unknown"] if match == "unknown" else [])


def test_a_binding_holds_within_its_block(tmp_path):
    body = _block("python", "gen = UuidGenerator()") + _block("python", "uid = gen.next_uuid()") + ANCHOR
    export = _method(_locate_methods(_skill(tmp_path, body), [("UuidGenerator", "next_uuid")]),
                     "UuidGenerator", "next_uuid")
    assert [c["text"] for c in export["unverifiedCalls"]] == ["uid = gen.next_uuid()"]


def test_the_last_binding_before_a_call_decides(tmp_path):
    code = "client = SyncClient()\nclient.get(1)\nclient = AsyncClient()\nreply = await client.get(2)"
    out = _locate_methods(_skill(tmp_path, _block("python", code)), [("SyncClient", "get"), ("AsyncClient", "get")])
    for owner, text, awaited in (("SyncClient", "client.get(1)", False),
                                 ("AsyncClient", "reply = await client.get(2)", True)):
        export = _method(out, owner, "get")
        assert [(c["receiverMatch"], c["text"], c["awaited"]) for c in export["calls"]] == [("bound", text, awaited)]
        assert (export["unverifiedCalls"], export["otherReceiverCount"]) == ([], 1)


def test_a_member_calls_result_binds_nothing(tmp_path):
    """`agent` holds what `cognee.agents.create` returns, not the `agents` namespace: its `get` is unverified."""
    code = "agent = await cognee.agents.create(name)\nreply = await agent.get(1)"
    out = _locate_methods(_skill(tmp_path, _block("python", code)), [("cognee.agents", "get")])
    assert out["exports"] == []
    assert [[c["receiver"] for c in u["unverifiedCalls"]] for u in out["notCalledUnverified"]] == [["agent"]]


def test_owner_matching(tmp_path):
    """The receiver's last member names the owner in any case; when both have several parts the owner's are the
    receiver's last ones; an owner's type parameters are dropped."""
    code = ("msg = await client.messages.create(model=m)\nother_lib.agents.get(1)\nawait cognee.agents.get(2)\n"
            "agents.get(3)\nrepo: Repository<User> = make()\nrepo.find(4)")
    out = _locate_methods(_skill(tmp_path, _block("python", code)),
                          [("Messages", "create"), ("cognee.agents", "get"), ("Repository<T>", "find")])
    assert [(c["receiver"], c["receiverMatch"]) for c in _method(out, "Messages", "create")["calls"]] == [
        ("client.messages", "owner")]
    agents = _method(out, "cognee.agents", "get")
    assert [(c["receiver"], c["receiverMatch"]) for c in agents["calls"]] == [
        ("cognee.agents", "owner"), ("agents", "owner")]
    assert [c["receiver"] for c in agents["unverifiedCalls"]] == ["other_lib.agents"]
    assert [(c["receiver"], c["receiverMatch"]) for c in _method(out, "Repository", "find")["calls"]] == [
        ("repo", "bound")]


def test_a_method_with_only_unverified_calls_is_not_called(tmp_path):
    """§2.5's async rule cites a first call, so an owned method no call is tied to is in `notCalled[]`, as
    `owner.name`, never an export with `callCount` 0; its unverified calls reach `notCalledUnverified[]`."""
    root = _skill(tmp_path, _block("python", "uid = self.gen.next_uuid()\nnext_uuid()"))
    out = _locate_methods(root, [("coco.UuidGenerator", "next_uuid")])
    assert out["exports"] == []
    assert out["notCalled"] == ["coco.UuidGenerator.next_uuid"]
    assert [(u["name"], u["owner"], [c["text"] for c in u["unverifiedCalls"]]) for u in out["notCalledUnverified"]] == [
        ("next_uuid", "coco.UuidGenerator", ["uid = self.gen.next_uuid()", "next_uuid()"])]
    assert out["summary"] == {"names": 1, "called": 0, "notCalled": 1}


def test_same_method_name_on_two_classes_stays_apart(tmp_path):
    """Two owners' `update` each take the call on their own receiver, and each sees the other's as another owner's."""
    code = ('app = coco.App(main, name="demo")\nawait app.update()\n'
            "op: LiveComponentOperator = ctx.operator\nawait op.update(x)")
    out = _locate_methods(_skill(tmp_path, _block("python", code)),
                          [("App", "update"), ("LiveComponentOperator", "update")])
    assert [(e["owner"], e["name"]) for e in out["exports"]] == [("App", "update"), ("LiveComponentOperator", "update")]
    for owner, receiver, text in (("App", "app", "await app.update()"),
                                  ("LiveComponentOperator", "op", "await op.update(x)")):
        export = _method(out, owner, "update")
        assert [(c["receiver"], c["receiverMatch"], c["text"]) for c in export["calls"]] == [
            (receiver, "bound", text)]
        assert (export["callCount"], export["awaitedCount"]) == (1, 1)
        assert (export["unverifiedCalls"], export["otherReceiverCount"]) == ([], 1)


def test_descriptions_that_name_the_owner_come_first(tmp_path):
    """An owned method's descriptions that name its owner lead, so the cap never cuts them for another owner's."""
    body = ("".join(f"- `settings.get` reads setting {i}\n" for i in range(14)) + "- `cognee.agents.get` is async.\n\n"
            + _block("python", "agent = await cognee.agents.get(1)"))
    root = _skill(tmp_path, body)
    export = _method(_locate_methods(root, [("Agents", "get")]), "Agents", "get")
    assert (export["descriptionCount"], len(export["descriptions"])) == (15, mod.MAX_DESCRIPTIONS)
    assert export["descriptions"][0]["text"] == "- `cognee.agents.get` is async."
    # A name without an owner keeps the file order, so the cap cuts that description.
    plain = _export(_run(root, ["get"]), "get")
    assert "- `cognee.agents.get` is async." not in [d["text"] for d in plain["descriptions"]]


def test_many_owners_in_one_block_finish_quickly(tmp_path):
    """Each block's bindings are read once and each match once, whatever the number of owners."""
    count = 300
    code = "\n".join([f"c{i} = Owner{i}()" for i in range(count)] + [f"await c{i}.get({i})" for i in range(count)]
                     + [f"c{i}.m{i}()" for i in range(count)])
    methods = [(f"Owner{i}", "get") for i in range(count)] + [(f"Owner{i}", f"m{i}") for i in range(count)]
    started = time.perf_counter()
    out = _locate_methods(_skill(tmp_path, _block("python", code)), methods)
    assert time.perf_counter() - started < 5
    assert len(out["exports"]) == 2 * count
    assert all(e["callCount"] == 1 and e["calls"][0]["receiverMatch"] == "bound" for e in out["exports"])
    assert all(e["otherReceiverCount"] == count - 1 for e in out["exports"] if e["name"] == "get")


def test_a_name_without_an_owner_matches_any_receiver(tmp_path):
    """A `names` entry and a method given without an owner behave as before: every receiver's call counts, and
    each call carries its `receiver` and a null `receiverMatch`."""
    code = ('await cognee.agents.get(a);\ncognee.config.get("k");\nsettings.get("x");\nget("y");\n'
            "await client\n  .api?.get(z);")
    out = _run(_skill(tmp_path, _block("ts", code)), ["get"])
    export = _export(out, "get")
    assert [(c["receiver"], c["receiverMatch"], c["awaited"]) for c in export["calls"]] == [
        ("cognee.agents", None, True), ("cognee.config", None, False), ("settings", None, False), (None, None, False),
        ("client.api", None, True)]
    assert (export["owner"], export["unverifiedCalls"], export["otherReceiverCount"]) == (None, [], 0)
    assert (export["callCount"], export["awaitedCount"]) == (5, 2)


def test_methods_items_need_a_name_and_an_owner(tmp_path):
    root = _skill(tmp_path, _block("python", "await agents.get(1)\nagents.find(2)"))
    out = locate({"names": [], "methods": [
        {"name": "get"}, {"name": "get", "owner": ""}, {"owner": "agents"}, "get", {"name": 7, "owner": "agents"},
        {"name": "get", "owner": "cognee.agents"}, {"name": "get", "owner": "agents"},
        {"name": "get", "owner": "agents"}, {"name": "agents.find", "owner": "x"},
    ], "skillPackagePath": str(root)})
    # Duplicates name one method; an owner never applies to a qualified name.
    assert [(e["owner"], e["name"]) for e in out["exports"]] == [
        ("cognee.agents", "get"), ("agents", "get"), (None, "agents.find")]
    assert out["summary"] == {"names": 3, "called": 3, "notCalled": 0}


@pytest.mark.parametrize("extra", [{"methods": "get"}, {"methods": {"name": "get", "owner": "a"}}, {"owners": "a"}],
                         ids=["methods-string", "methods-object", "owners-string"])
def test_methods_and_owners_must_be_lists(tmp_path, extra):
    out = locate({"names": [], "skillPackagePath": str(tmp_path), **extra})
    assert out["code"] == "INVALID_INPUT" and next(iter(extra)) in out["error"]


@pytest.mark.parametrize("item, name", [
    ("async next_uuid(self, dep=None) -> uuid.UUID", "next_uuid"),
    ("update(self, *, ...) -> UpdateHandle[R]", "update"),
    ("  .drop()", "drop"),
    ("@staticmethod create(x)", "create"),
    ("@property name", "name"),
    ("@lru_cache(maxsize=1) compute(x)", "compute"),
    ("public static async fetch(url: string): Promise<Data>", "fetch"),
    ("def close(self) -> None", "close"),
    ("func (c *Client) Fetch(ctx) error", "Fetch"),
    ("String getName()", "getName"),
    ("Task<int> RunAsync<T>(Func<T> f)", "RunAsync"),
    ("UuidGenerator.next_uuid(dep)", "next_uuid"),
    ("get(agent_id)", "get"),
    ("async *stream()", "stream"),
    ("awaitTermination()", "awaitTermination"),
    ("name", "name"),
    ("__init__(self, deps=None) -> None", None),
    ("__aenter__()", None),
    ("await result", None),
    ("async", None),
    ("async *[Symbol.asyncIterator]()", None),
    ("(x) => x", None),
], ids=["async", "keyword-only", "leading-dot", "decorator", "property", "decorator-arguments", "modifiers", "def",
        "go-receiver", "return-type-first", "generic-return-type", "qualified", "get-is-a-name", "async-generator",
        "await-prefix-of-a-name", "no-parentheses", "dunder", "async-dunder", "await", "async-only",
        "async-iterator", "no-name"])
def test_methods_items_name_their_method(item, name):
    assert mod._method_name(item) == name


def test_inventory_input_ties_methods_to_their_owner(tmp_path):
    inventory = tmp_path / "inventory.json"
    inventory.write_bytes(json.dumps({"exports": [
        {"name": "fetch", "kind": "function"},
        {"name": "get", "kind": "method", "owner": "cognee.agents"},
        {"name": "close", "kind": "method"},
        {"name": "load", "kind": "method", "owner": 7},
        {"name": "TargetHandler", "kind": "interface", "methods": ["async apply(self, change) -> None", 7]},
        {"name": "Point", "kind": "struct", "methods": ["fn norm(&self) -> f64", "__init__()"]},
        {"name": "Shape", "kind": "type", "methods": ["area()"]},
        {"name": "Color", "kind": "enum", "methods": ["values()"]},
        {"name": "Http", "kind": "adapter", "methods": ["send()"]},
        {"name": "MAX", "kind": "constant"},
    ], "cross_check_mismatches": []}).encode("utf-8"))
    data = mod.inventory_input(inventory, "skill")
    # A method with no string owner is matched by its name, as before.
    assert data["names"] == ["fetch", "close", "load"]
    # Only a class, interface, struct, trait or type entry's `methods` are read.
    assert data["methods"] == [{"name": "get", "owner": "cognee.agents"}, {"name": "apply", "owner": "TargetHandler"},
                               {"name": "norm", "owner": "Point"}, {"name": "area", "owner": "Shape"}]
    assert data["owners"] == ["cognee.agents", "TargetHandler", "Point", "Shape", "Color", "Http"]


def test_inventory_reads_class_methods(tmp_path):
    """#844: a class entry's `methods` reach the locator, each tied to its class, so an example that never awaits
    a method the skill documents as async is checked."""
    skill = _skill(tmp_path, _block("python", "gen = UuidGenerator()\nuid = gen.next_uuid()"))
    inventory = tmp_path / "inventory.json"
    inventory.write_bytes(json.dumps({"exports": [{
        "name": "UuidGenerator", "kind": "class", "description": "",
        "methods": ["__init__(self, deps=None) -> None", "async next_uuid(self, dep=None) -> uuid.UUID",
                    "await result"],
    }], "cross_check_mismatches": []}).encode("utf-8"))
    result = _cli("--inventory", str(inventory), "--skill-dir", str(skill))
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert [(e["name"], e["owner"]) for e in out["exports"]] == [("next_uuid", "UuidGenerator")]
    export = out["exports"][0]
    assert (export["callCount"], export["awaitedCount"]) == (1, 0)
    assert [(c["receiver"], c["receiverMatch"]) for c in export["calls"]] == [("gen", "bound")]
    assert (out["notCalled"], out["summary"]["names"]) == ([], 1)


# --------------------------------------------------------------------------
# Comments, strings and data blocks hide nothing they should not
# --------------------------------------------------------------------------


@pytest.mark.parametrize("language, code", [
    ("ts", "// fetchData(url) is async\n/* fetchData(x) */\nconst s = \"fetchData(url)\";\nconst t = `fetchData(${x})`;"),
    ("python", "# fetchData(url)\ns = 'fetchData(url)'\ndoc = \"\"\"\nfetchData(url)\n\"\"\""),
    ("json", '{"call": "fetchData(url)"}'),
    ("text", "fetchData(url)"),
    ("console", "$ node -e 'fetchData(url)'"),
    ("yaml", "run: fetchData(url)"),
], ids=["ts-comments-strings", "python-comments-strings", "json", "text", "console", "yaml"])
def test_hidden_calls(tmp_path, language, code):
    assert _calls(tmp_path, language, code) == []


def test_rust_lifetime_is_not_a_string(tmp_path):
    code = "fn run<'a>(url: &'a str) {\n    let d = fetchData(url);\n}"
    assert [c["text"] for c in _calls(tmp_path, "rust", code)] == ["let d = fetchData(url);"]


def test_untagged_code_is_read_as_written(tmp_path):
    assert len(_calls(tmp_path, "", "d = fetchData(url)  # fetchData(again)")) == 2


def test_unclosed_fence_runs_to_the_end(tmp_path):
    root = _skill(tmp_path, "```ts\nconst d = await fetchData(url);\n")
    assert _export(_run(root, ["fetchData"]), "fetchData")["awaitedCount"] == 1


def test_name_is_a_whole_identifier(tmp_path):
    code = "prefetchData(url);\nfetchDataAll(url);\n$fetchData(url);\nfetchData(url);\nfetchData<Data>(url);"
    assert [c["text"] for c in _calls(tmp_path, "ts", code)] == ["fetchData(url);", "fetchData<Data>(url);"]


def test_dollar_names(tmp_path):
    code = "const r = await $fetch('/api');"
    assert [c["awaited"] for c in _calls(tmp_path, "ts", code, "$fetch")] == [True]


def test_non_ascii_identifiers(tmp_path):
    code = "await éfetchData(url);\nawait fetchDataé(url);\nconst x = await fetchData(url);\nawait données(url);"
    out = _run(_skill(tmp_path, _block("ts", code)), ["fetchData", "données"])
    assert [c["text"] for c in _export(out, "fetchData")["calls"]] == ["const x = await fetchData(url);"]
    assert [c["awaited"] for c in _export(out, "données")["calls"]] == [True]


def test_name_match_is_the_scanners_export_match(monkeypatch):
    """Both scripts decide alike whether a name stands in a line, non-ASCII identifiers included."""
    spec = importlib.util.spec_from_file_location("skf_scan_skill_md_structure", SCANNER_PATH)
    scanner = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    monkeypatch.setitem(sys.modules, spec.name, scanner)
    spec.loader.exec_module(scanner)
    names = ["get", "fetchData", "café", "données", "$state", "a.b", "Store::load", ".then"]
    lines = ["getAll(x)", "get(x)", "target(x)", "cafés()", "café()", "xcafé()", "données(1)", "donnéesX(1)",
             "$state()", "x$state()", "a.b()", "xa.b()", "Store::load()", "MyStore::load()", "fetchDataé()",
             "fetchData()", "promise.then(f)", "_fetchData()"]
    for name in names:
        ours = mod._bounded(name)
        theirs = re.compile(scanner._bounded(name, scanner._IDENT_CHARS))
        assert [line for line in lines if ours.search(line)] == [line for line in lines if theirs.search(line)], name


# --------------------------------------------------------------------------
# Descriptions
# --------------------------------------------------------------------------


DESCRIBED = """## Overview

The fetchData helper reads remote data, but plain prose is not a mention.

## API

### `fetchData(url)`

Fetches the data. Returns a Promise.

- `url`: where to read `fetchData` input.

#### Errors

Throws when offline.

## Usage

- `fetchData(url)` must be awaited.
- `other()` is unrelated.

Call `fetchData` once per page.

<!-- `fetchData` in a comment is not a description -->

```ts
const d = await fetchData(url);
```
"""


def _line(marker: str) -> int:
    """The 1-based line of the fixture SKILL.md that starts with `marker`."""
    lines = (FRONTMATTER + DESCRIBED).split("\n")
    return next(i + 1 for i, line in enumerate(lines) if line.startswith(marker))


def test_description_kinds_and_sections(tmp_path):
    export = _export(_run(_skill(tmp_path, DESCRIBED), ["fetchData"]), "fetchData")
    kinds = [(d["kind"], d["line"], d["section"]) for d in export["descriptions"]]
    assert kinds == [
        ("heading", _line("### `fetchData(url)`"), "demo > API"),
        ("list-item", _line("- `fetchData(url)` must"), "demo > Usage"),
        ("paragraph", _line("Call `fetchData`"), "demo > Usage"),
    ]
    heading = export["descriptions"][0]
    # The section runs to the next heading of the same or a higher level: its
    # own sub-heading's prose is in it, and its list item is not listed apart.
    assert heading["endLine"] == _line("## Usage") - 1
    assert heading["text"] == ("`fetchData(url)` Fetches the data. Returns a Promise. - `url`: where to read "
                               "`fetchData` input. Throws when offline.")
    assert export["descriptionCount"] == 3


def test_frontmatter_is_not_a_description(tmp_path):
    root = tmp_path / "skill"
    root.mkdir()
    (root / "SKILL.md").write_bytes(
        b"---\nname: demo\ndescription: Covers `fetchData`, which is async.\n---\n\n```ts\nfetchData(x)\n```\n")
    assert _export(_run(root, ["fetchData"]), "fetchData")["descriptions"] == []


def test_bare_heading_names_the_export(tmp_path):
    body = "## cognee.add\n\nIngests data.\n\n```python\nawait cognee.add(x)\n```\n"
    export = _export(_run(_skill(tmp_path, body), ["cognee.add"]), "cognee.add")
    assert [(d["kind"], d["text"]) for d in export["descriptions"]] == [("heading", "cognee.add Ingests data.")]


def test_long_text_is_cut_and_flagged(tmp_path):
    body = "- `fetchData` " + "word " * 400 + "\n\n```ts\nfetchData(x)\n```\n"
    entry = _export(_run(_skill(tmp_path, body), ["fetchData"]), "fetchData")["descriptions"][0]
    assert entry["truncated"] is True and len(entry["text"]) == mod.TEXT_CAP


def test_descriptions_are_capped_and_counted(tmp_path):
    body = "".join(f"- `fetchData` note {i}\n" for i in range(20)) + "\n```ts\nfetchData(x)\n```\n"
    export = _export(_run(_skill(tmp_path, body), ["fetchData"]), "fetchData")
    assert export["descriptionCount"] == 20
    assert len(export["descriptions"]) == mod.MAX_DESCRIPTIONS


def test_references_are_read_after_skill_md_in_path_order(tmp_path):
    refs = {
        "z-last.md": "- `fetchData` z\n\n```ts\nawait fetchData(1)\n```\n",
        "api/deep.md": "- `fetchData` deep\n",
        "a-first.md": "- `fetchData` a\n",
    }
    out = _run(_skill(tmp_path, "- `fetchData` top\n", refs), ["fetchData"])
    assert out["files"] == ["SKILL.md", "references/a-first.md", "references/api/deep.md", "references/z-last.md"]
    export = _export(out, "fetchData")
    assert [d["file"] for d in export["descriptions"]] == out["files"]
    assert [c["file"] for c in export["calls"]] == ["references/z-last.md"]


def test_line_numbers_match_grep_with_crlf_and_bom(tmp_path):
    root = tmp_path / "skill"
    root.mkdir()
    text = FRONTMATTER + "- `fetchData` reads.\n\n```ts\nconst d = await fetchData(url);\n```\n"
    (root / "SKILL.md").write_bytes(b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))
    export = _export(_run(root, ["fetchData"]), "fetchData")
    grep_lines = [i + 1 for i, line in enumerate(text.split("\n")) if "fetchData" in line]
    assert [export["descriptions"][0]["line"], export["calls"][0]["line"]] == grep_lines
    assert export["calls"][0]["text"] == "const d = await fetchData(url);"


# --------------------------------------------------------------------------
# Input and CLI contract
# --------------------------------------------------------------------------


def test_names_are_deduplicated_and_blank_names_dropped(tmp_path):
    out = _run(_skill(tmp_path, _block("ts", "fetchData(1)")), ["fetchData", "fetchData", "", "  ", 7])
    assert out["summary"] == {"names": 1, "called": 1, "notCalled": 0}


def test_no_names_gives_an_empty_result(tmp_path):
    out = _run(_skill(tmp_path, PAIRED), [])
    assert (out["exports"], out["notCalled"]) == ([], [])


@pytest.mark.parametrize("bad", [
    None,
    [],
    {"skillPackagePath": "x"},
    {"names": "fetchData", "skillPackagePath": "x"},
    {"names": ["fetchData"]},
    {"names": ["fetchData"], "skillPackagePath": ""},
], ids=["none", "list", "no-names", "names-not-list", "no-path", "empty-path"])
def test_invalid_input(bad):
    assert locate(bad)["code"] == "INVALID_INPUT"


def test_missing_folder_is_invalid(tmp_path):
    out = locate({"names": ["x"], "skillPackagePath": str(tmp_path / "absent")})
    assert out["code"] == "INVALID_INPUT" and "not a folder" in out["error"]


def _cli(*args, stdin: str | None = None):
    return subprocess.run([sys.executable, str(SCRIPT_PATH), *args], input=stdin,
                          capture_output=True, text=True, check=False)


def test_cli_stdin_positional_and_flag_agree(tmp_path):
    payload = json.dumps({"names": ["readFile", "readFileSync"], "skillPackagePath": str(_skill(tmp_path, PAIRED))})
    results = [_cli("--stdin", stdin=payload), _cli(payload), _cli("--json-input", payload)]
    assert [r.returncode for r in results] == [0, 0, 0]
    parsed = [json.loads(r.stdout) for r in results]
    assert parsed[0] == parsed[1] == parsed[2]
    assert parsed[0]["summary"]["called"] == 2


def test_cli_no_input_exit_1():
    result = _cli(stdin="")
    assert result.returncode == 1 and "no input" in result.stderr


def test_cli_malformed_json_exit_1():
    result = _cli("--stdin", stdin="{not json")
    assert result.returncode == 1 and json.loads(result.stdout)["code"] == "INVALID_INPUT"


def test_cli_invalid_schema_exit_2(tmp_path):
    result = _cli("--stdin", stdin=json.dumps({"names": "x", "skillPackagePath": str(tmp_path)}))
    assert result.returncode == 2 and json.loads(result.stdout)["code"] == "INVALID_INPUT"


def test_script_header():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env python3\n# /// script\n# requires-python = \">=3.11\"\n")
    assert "sys.exit(main())" in text


# --------------------------------------------------------------------------
# coherence-check §2.5 reads the script's facts and classifies the descriptions
# --------------------------------------------------------------------------


def _section_25() -> str:
    text = COHERENCE.read_text(encoding="utf-8")
    start = text.index("**2.5 Async/sync consistency.**")
    return text[start:text.index("**2.6 Table syntax.**", start)]


def _flow(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def test_coherence_binds_the_script():
    frontmatter = COHERENCE.read_text(encoding="utf-8").split("\n---\n", 1)[0]
    assert "locateExportSegmentsScript: 'scripts/locate-export-segments.py'" in frontmatter


def test_async_check_runs_the_script_on_function_and_method_names():
    """The script reads the names from the validated inventory file: none is echoed by hand."""
    section = _section_25()
    call = 'uv run {locateExportSegmentsScript} --inventory "{run_dir}/inventory.json" --skill-dir "{resolved_skill_package}"'
    assert call in section
    assert "echo '" not in section
    for field in ("`descriptions[]`", "`awaitedCount`", "`directlyAwaitedCount`", "`awaitedVia`",
                  "`enclosingCallee`", "`chainedMember`", "`notCalled[]`", "`owner`", "`receiverMatch`",
                  "`unverifiedCalls[]`"):
        assert field in section, field


def test_async_check_reads_class_methods_tied_to_their_owner():
    """#842, #844: §2.5 checks each class-like entry's `methods`, counts a method's calls on its owner only, and an
    unverified call or another owner's same-named method raises nothing."""
    section = _flow(_section_25())
    intro = section[:section.index("```bash")]
    assert ("each method a class, interface, struct, trait or type entry lists in `methods`, with that entry as its "
            "`owner`") in intro
    assert "only the calls on that owner or on a variable the same example binds to it" in intro
    assert ("a call with no receiver or on one it cannot tie to the owner is listed in `unverifiedCalls[]` (for a "
            "method with no tied call, in `notCalledUnverified[]`)") in intro
    assert ("Skip this check when the inventory has no `function` or `method` entry and no class, interface, struct, "
            "trait or type entry with `methods`") in intro
    no_claim = section[section.index("- **no claim**"):section.index("Then, for each export:")]
    assert "a same-named method of another owner" in no_claim
    assert "A call in `unverifiedCalls[]` or `notCalledUnverified[]` raises none either" in section
    # An owned method's finding and ledger record name it as `owner.name`.
    assert ("For an export with an `owner`, its finding's title writes `{owner}.{name}` for `{name}`, and so does "
            "its ledger record's `export`.") in section


def test_async_check_never_decides_from_the_word_async():
    section = _flow(_section_25())
    assert r"\basync\b" not in section and "grep" not in section
    assert "The word `async` in a description decides nothing" in section
    # The model classifies what the descriptions assert about this export.
    for claim in ("**async**", "**sync**", "**no claim**"):
        assert claim in section, claim
    assert "a paired sync or async variant" in section


def test_async_check_findings():
    section = _flow(_section_25())
    assert ("**async**, no call is awaited (`awaitedCount` is 0) and no unawaited call hands its result on "
            "→ **High severity** finding: `naive-coherence: \\`{name}\\` described as async but example lacks "
            "\\`await\\``") in section
    # #783: a direct await of a sync export is a High finding, and so is an argument of a call that needs
    # awaitables, its own bullet so it fires when no call is directly awaited; JS's combinators raise nothing.
    assert ("- **sync** and `directlyAwaitedCount` is above 0 → **High severity** finding: `naive-coherence: "
            "\\`{name}\\` described as sync but example awaits it` (cite the first directly awaited call). "
            "- **sync**, `directlyAwaitedCount` is 0 and a call sits in the arguments of a call that needs "
            "awaitable arguments → the same **High severity** finding (cite the first such call's `file` and "
            "`line`): its `awaitedVia` is `runner` (a runner such as Python `asyncio.run` or "
            "`loop.run_until_complete`, Rust `block_on`), or `argument` with an `enclosingCallee` of Python "
            "`asyncio.gather`, `asyncio.wait` or `asyncio.wait_for`. JavaScript `Promise.all`, `Promise.race` and "
            "`Promise.allSettled` accept plain values, so a call in their arguments raises nothing, and neither "
            "does any other call that is `awaited` but not `directlyAwaited` (`awaitedVia` `chain`, `consumer`, "
            "or `argument` of another callee).") in section
    assert "**sync** and `awaitedCount`" not in section
    # The intro names each way a call is awaited, so the model can read the fields the bullets use.
    for via in ("`direct`", "`chain`", "`consumer`", "`argument`", "`runner`"):
        assert via in section[:section.index("```bash")], via
    # An unawaited call still hands its result on when it is chained, returned or stored.
    start = section.index("A call hands its result on when")
    handed_on = section[start:section.index("read the call lines", start)]
    for way in ("`chainedMember`", "the example returns it", "stores it and awaits it later"):
        assert way in handed_on, way


def test_async_check_findings_cite_the_calls_own_file():
    """#783: the cited call can sit in a references/*.md file, so a §2.5 finding's Source is its file."""
    text = _flow(COHERENCE.read_text(encoding="utf-8"))
    record = text[text.index("Then write the records no script wrote"):]
    record = record[:record.index("each §5 incomplete integration pattern")]
    assert ("the §2.5 findings, titled with their `naive-coherence:` text and with their Source at the cited "
            "call's `{file}:{line}`;") in record
    assert "`SKILL.md:{line}`" not in record


def test_every_naive_finding_title_uses_one_separator():
    text = COHERENCE.read_text(encoding="utf-8")
    naive = text[text.index("### 2. Naive Mode"):text.index("### 2b.")]
    titles = re.findall(r"`naive-coherence(.)", naive)
    assert titles and set(titles) == {":"}, titles


def test_cli_inventory_reads_names_and_class_methods(tmp_path):
    """A method without an `owner` is matched by its name, as before; a class entry's `methods` reach the output
    tied to the class (#844)."""
    skill = _skill(tmp_path, PAIRED + _block("ts", "const r = new Reader();\nconst text = r.read(path);"))
    inventory = tmp_path / "inventory.json"
    inventory.write_bytes(json.dumps({"exports": [
        {"name": "readFile", "kind": "function", "description": "It's async."},
        {"name": "readFileSync", "kind": "method"},
        {"name": "Options", "kind": "interface"},
        {"name": "Reader", "kind": "class", "methods": ["async read(path: string): Promise<string>", "close()"]},
    ], "cross_check_mismatches": []}).encode("utf-8"))
    by_inventory = _cli("--inventory", str(inventory), "--skill-dir", str(skill))
    assert by_inventory.returncode == 0, by_inventory.stderr
    by_json = _cli(json.dumps({"names": ["readFile", "readFileSync"],
                               "methods": [{"name": "read", "owner": "Reader"}, {"name": "close", "owner": "Reader"}],
                               "owners": ["Options", "Reader"], "skillPackagePath": str(skill)}))
    out = json.loads(by_inventory.stdout)
    assert out == json.loads(by_json.stdout)
    assert [(e["owner"], e["name"]) for e in out["exports"]] == [
        (None, "readFile"), (None, "readFileSync"), ("Reader", "read")]
    assert [c["receiverMatch"] for c in out["exports"][1]["calls"]] == [None]
    assert [(c["receiver"], c["receiverMatch"], c["awaited"]) for c in out["exports"][2]["calls"]] == [
        ("r", "bound", False)]
    assert out["notCalled"] == ["Reader.close"]
    # Without its methods, the class leaves the function and method names as they were.
    names_only = _cli(json.dumps({"names": ["readFile", "readFileSync"], "skillPackagePath": str(skill)}))
    assert json.loads(names_only.stdout)["exports"] == out["exports"][:2]


def test_cli_inventory_needs_a_skill_dir_and_a_readable_file(tmp_path):
    assert _cli("--inventory", str(tmp_path / "inventory.json")).returncode == 2
    missing = _cli("--inventory", str(tmp_path / "absent.json"), "--skill-dir", str(tmp_path))
    assert missing.returncode == 1 and "cannot read --inventory" in missing.stderr
