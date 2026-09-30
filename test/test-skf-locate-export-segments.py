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
The last section pins the §2.5 prose that calls it.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
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
EXPORT_KEYS = {"name", "descriptionCount", "descriptions", "calls", "callCount", "awaitedCount"}
CALL_KEYS = {"file", "line", "fence", "language", "awaited", "chainedMember", "text"}
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
    return out


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
    assert set(out) == {"skillPackagePath", "files", "exports", "notCalled", "summary"}
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


def test_rust_path_names(tmp_path):
    code = "let store = Store::load(path).await?;\nimpl Store {\n    pub async fn load(path: &Path) -> Self { todo!() }\n}"
    export = _export(_run(_skill(tmp_path, _block("rust", code)), ["Store::load"]), "Store::load")
    assert [(c["awaited"], c["text"]) for c in export["calls"]] == [(True, "let store = Store::load(path).await?;")]
    assert [d["text"] for d in export["descriptions"]] == ["pub async fn load(path: &Path) -> Self { todo!() }"]


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
    section = _section_25()
    call = ('echo \'{"names": [<each exports[].name whose kind is function or method>], '
            '"skillPackagePath": "{resolved_skill_package}"}\' | uv run {locateExportSegmentsScript} --stdin')
    assert call in section
    for field in ("`descriptions[]`", "`awaitedCount`", "`chainedMember`", "`notCalled[]`"):
        assert field in section, field


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
    assert ("**sync** and `awaitedCount` is above 0 → **High severity** finding: `naive-coherence: "
            "\\`{name}\\` described as sync but example awaits it`") in section
    # An unawaited call still hands its result on when it is chained, returned or stored.
    start = section.index("A call hands its result on when")
    handed_on = section[start:section.index("read the call lines", start)]
    for way in ("`chainedMember`", "the example returns it", "stores it and awaits it later"):
        assert way in handed_on, way


def test_every_naive_finding_title_uses_one_separator():
    text = COHERENCE.read_text(encoding="utf-8")
    naive = text[text.index("### 2. Naive Mode"):text.index("### 2b.")]
    titles = re.findall(r"`naive-coherence(.)", naive)
    assert titles and set(titles) == {":"}, titles
