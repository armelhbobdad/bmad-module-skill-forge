#!/usr/bin/env python3
"""Quick Skill contract: the skills-module shape (#527), the batch override
rule and review preview (#609), how resolve-target reads a target (#582,
#588), the inputs it takes by file and by flag (#592, #594), and the run
contract the shared emitter and skf-quick-batch.py keep (#585, #586, #587,
#593), the customization surface (#596), the ecosystem check and the helper
fallbacks it no longer has (#599), and one home per rule (#600).

Step 1 lists the repository once, into the run folder, and every later
read goes through that listing: step 3 fetches each file raw into the run
folder with skf-github-fetch.py and hands it to the helper that reads it
by path, and compile renders metadata.json from those files and a staged
heredoc. The chain runs here as the steps write it, against a local
server standing in for raw.githubusercontent.com (bash runs each block;
skipped on Windows), so the prose cannot drift from commands that work: a
skills module from its listing to its metadata.json, a library whose
source holds an apostrophe, and a run that fetched no source file, whose
empty envelope still reaches the renderer. The skills-module rule itself
lives in skf-skills-module.py (test/test-skf-skills-module.py runs the
real repository layouts); the step reads its answer. The batch rule, the halt
contract entry, the hint flags, the language pick and the preview are
pinned where each file states them.

resolve-target.md hands every target to skf-resolve-package.py parse-target
through a quoted heredoc, which runs here through bash with a target that
holds quotes, backticks and `$`. Every example the step and the registry data
list goes through the parser, every kind and status the script returns has a
branch, each route names the skill after the script's skill_name, and the
ambiguous-name gate, the language hint and the tag check through
skf-github-probe.py are pinned where the step states them.

Every HARD HALT in SKILL.md and the stage files stages its payload and runs
the shared emitter inline: each payload, filled in, builds an envelope the
skf-quick-skill schema accepts with the exit code the halt names, and no
halt is left without a code. Each headless gate records its auto-decision
under a gate name the schema lists, finalize's success payload builds a
valid envelope with the summary the schema defines (step 5's validation
counts in the schema's shape), and under --batch every target's end (step 6,
and every halt through its stage's Rules) returns to batch-mode.md, which
runs the health check once. The one halt that emits nothing is activation's
check for python3 and uv, which the emitter itself needs.

customize.toml offers only settings a step reads: each path scalar ships the
default SKILL.md binds, the template comment names the headings the validator
and the snippet anchors need, and the hook comments say when SKILL.md runs
them. The ecosystem check makes no web search while agentskills.io has no
registry API, and keeps its slug, gate and exit 8. A missing resolver or
language detector halts instead of being worked out by hand, and so does
every other shipped helper a step runs (the GitHub fetch helper, the
skills-module helper, the public-API extractor, the atomic writer and the
two validators): no file is fetched, parsed, copied or left unchecked by
hand (#599).
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
QS = REPO / "src" / "skf-quick-skill"
QUICK_EXTRACT = QS / "references" / "quick-extract.md"
COMPILE = QS / "references" / "compile.md"
TEMPLATE = QS / "assets" / "skill-template.md"
SKILL = QS / "SKILL.md"
BATCH_MODE = QS / "references" / "batch-mode.md"
HALT_CONTRACT = QS / "references" / "halt-contract.md"
RESOLVE_TARGET = QS / "references" / "resolve-target.md"
REGISTRY_RESOLUTION = QS / "references" / "registry-resolution.md"
FINALIZE = QS / "references" / "finalize.md"
HEALTH_CHECK = QS / "references" / "health-check.md"
RESOLVER = REPO / "src" / "shared" / "scripts" / "skf-resolve-package.py"
GITHUB_PROBE = REPO / "src" / "shared" / "scripts" / "skf-github-probe.py"
EMITTER = REPO / "src" / "shared" / "scripts" / "skf-emit-result-envelope.py"
ENVELOPE_SCHEMA = REPO / "src" / "shared" / "scripts" / "schemas" / "skf-quick-skill-result-envelope.v1.json"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    assert text.count(start) == 1, f"expected exactly one {start!r}"
    head = text.index(start)
    tail = text.find(end, head + len(start))
    assert tail != -1, f"expected {end!r} after {start!r}"
    return text[head:tail]


def _bash_block(text: str, needle: str) -> str:
    """The one ```bash block of `text` that holds `needle`."""
    blocks = [b for b in re.findall(r"^```bash\n(.*?)^```$", text, flags=re.M | re.S) if needle in b]
    assert len(blocks) == 1, f"expected one bash block holding {needle!r}, found {len(blocks)}"
    return blocks[0]


def _single_quoted_after(block: str, word: str) -> str:
    """The single-quoted argument that follows `word` in a shell block."""
    m = re.search(re.escape(word) + r" '([^']*)'", block)
    assert m, f"no {word} '...' in:\n{block}"
    return m.group(1)


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        pytest.skip(f"{name} is not installed")
    return path


# --------------------------------------------------------------------------
# #592: one listing, files fetched raw into the run folder, passed by path
# --------------------------------------------------------------------------

SCRIPTS = REPO / "src" / "shared" / "scripts"
GITHUB_FETCH = SCRIPTS / "skf-github-fetch.py"
SKILLS_MODULE = SCRIPTS / "skf-skills-module.py"
EXTRACTOR = SCRIPTS / "skf-extract-public-api.py"
RENDERER = SCRIPTS / "skf-render-quick-metadata.py"
WRITE_AND_VALIDATE = QS / "references" / "write-and-validate.md"


def _sniff() -> str:
    return _section(_read(QUICK_EXTRACT), "### 1.5. Repo-Shape Sniff", "### 2. ")


def _bash_blocks(text: str) -> list[str]:
    """Every ```bash block of `text`, one in a list item included, dedented."""
    return [textwrap.dedent(b) for b in re.findall(r"^[ ]*```bash\n(.*?)^[ ]*```$", text, flags=re.M | re.S)]


def _nested_bash_block(text: str, needle: str) -> str:
    """The one ```bash block of `text`, at any indent, that holds `needle`."""
    blocks = [b for b in _bash_blocks(text) if needle in b]
    assert len(blocks) == 1, f"expected one bash block holding {needle!r}, found {len(blocks)}"
    return blocks[0]


def test_step_1_lists_the_tree_once_into_the_run_folder():
    detect = _section(_read(RESOLVE_TARGET), "### 4. Detect Language", "### 5. ")
    assert _bash_block(detect, " tree ") == ('uv run {githubProbe} tree --repo {owner}/{repo} '
                                            '--ref {source_ref or HEAD} > "{run_dir}/tree.json"\n')
    assert _nested_bash_block(detect, "{detectLanguageHelper}") == \
        'uv run {detectLanguageHelper} --tree-file "{run_dir}/tree.json"\n'
    # The listing comes first, so a language hint still leaves step 3 its tree.json.
    assert detect.index("tree.json") < detect.index("1. **User-provided language hint**")
    [unavailable] = [line for line in detect.splitlines() if line.startswith('- **`status: "unavailable"`')]
    for needle in ("HARD HALT with **exit code 3 (resolution-failure)**", "the probe's `message`",
                   '"details": {"ref": "{source_ref or HEAD}", "cause": ', "github-probe-missing"):
        assert needle in unavailable, needle


def test_no_step_lists_the_tree_or_types_a_file_into_a_shell_string():
    """#592: no recursive tree, file text or export list passes through the model or an echo."""
    for path in HALT_FILES:
        text = _read(path)
        assert "git/trees" not in text, path.name
        assert not re.search(r"echo '\{", text), path.name
        for block in _bash_blocks(text):
            assert "gh api" not in block, (path.name, block)
    extract = _read(QUICK_EXTRACT)
    assert "via web browsing" not in extract and "or web browsing" not in extract
    assert "does pure parsing" not in extract
    compile_md = _read(COMPILE)
    assert "Probe `tool_versions.skf`" not in compile_md and "skf/VERSION" not in compile_md


def test_every_step_3_read_goes_through_the_fetch_helper():
    text = _read(QUICK_EXTRACT)
    frontmatter = text.split("---\n", 2)[1]
    for stem, script in (("githubFetch", "skf-github-fetch.py"), ("skillsModule", "skf-skills-module.py")):
        assert (f"{stem}ProbeOrder:\n  - '{{project-root}}/_bmad/skf/shared/scripts/{script}'\n"
                f"  - '{{project-root}}/src/shared/scripts/{script}'\n") in frontmatter, stem
    calls = [line for block in _bash_blocks(text) for line in block.splitlines() if "{githubFetch}" in line]
    assert len(calls) == 3, calls
    parser = _load(GITHUB_FETCH, "skf_github_fetch_for_quick_contract")._build_parser()
    for line in calls:
        line = re.sub(r"\[--limit <n>\] \[--exclude <glob>\]\.\.\. <path or glob>\.\.\.", "README.md", line)
        args = line.replace("uv run {githubFetch} ", "").replace("{owner}/{repo}", "acme/lib")
        args = args.replace("{source_ref or HEAD}", "HEAD").replace("{run_dir}", "/tmp/run")
        parsed = parser.parse_args([token.strip('"') for token in re.findall(r'"[^"]*"|\S+', args)])
        assert parsed.tree_file == "/tmp/run/tree.json" and parsed.dest == "/tmp/run/src"


@pytest.mark.skipif(sys.platform == "win32", reason="runs the step's commands through a POSIX shell")
def test_the_skills_module_chain_runs_from_the_listing_to_metadata(tmp_path, raw_github):
    """quick-extract §1 to §3 and compile §4 run as written: the listing, the sniff, the raw
    fetch, the skills-module envelope and the renderer, with a description holding quotes."""
    run_dir = _run_folder(tmp_path, BUILDER_TREE)
    raw_github.update({"README.md": b"# bmad-builder\n", "package.json": b'{"name": "bmad-builder", "main": ""}',
                       "skills/alpha/SKILL.md": ALPHA, "skills/beta/SKILL.md": b"# no frontmatter\n",
                       "skills/module-help.csv": MODULE_HELP})
    extract = _read(QUICK_EXTRACT)
    _run(_bash_block(_section(extract, "### 1. Read the Listing and README", "### 1.5. "), " sniff "), run_dir)
    sniffed = json.loads((run_dir / "sniff.json").read_text(encoding="utf-8"))
    assert (sniffed["skills_root"], sniffed["readme"]) == ("skills", "README.md")
    _run(_bash_block(_section(extract, "### 2. Fetch Source Files", "### 3. "), "--patterns-file"), run_dir)
    skills = _section(extract, "**Skills module** (`repo_shape: skills-module`): when §2", "### 4. ")
    _run(_bash_block(skills, " extract "), run_dir)
    envelope = json.loads((run_dir / "extract.json").read_text(encoding="utf-8"))
    assert [(e["name"], e["type"]) for e in envelope["exports"]] == [("alpha", "skill"), ("beta", "skill"),
                                                                      ("BA", "menu-code")]
    assert envelope["confidence"] == "medium" and envelope["package_name"] == "acme-module"
    metadata = _render(run_dir, tmp_path)
    assert metadata["exports"] == ["alpha", "beta", "BA"]
    assert metadata["description"] == DESCRIPTION
    assert metadata["tool_versions"]["skf"] == "3.0.0"


@pytest.mark.skipif(sys.platform == "win32", reason="runs the step's commands through a POSIX shell")
def test_the_library_chain_hands_the_files_to_the_extractor_by_path(tmp_path, raw_github):
    """A source file holding an apostrophe reaches the extractor as written (#592)."""
    run_dir = _run_folder(tmp_path, ["README.md", "pyproject.toml", "src/acme/__init__.py", "tests/test_a.py"])
    raw_github.update({"README.md": b"# acme\n", "pyproject.toml": PYPROJECT, "src/acme/__init__.py": INIT_PY})
    extract = _read(QUICK_EXTRACT)
    _run(_bash_block(_section(extract, "### 1. Read the Listing and README", "### 1.5. "), " sniff "), run_dir)
    assert json.loads((run_dir / "sniff.json").read_text(encoding="utf-8"))["skills_module"] is False
    fetch = _bash_block(_section(extract, "### 1. Read the Listing and README", "### 1.5. "), " sniff ")
    fetch = fetch.splitlines()[0].replace(" package.json", " pyproject.toml 'src/{package}/__init__.py'")
    _run(fetch.replace("{package}", "acme") + "\n", run_dir)
    call = _bash_block(_section(extract, "### 3. Parse Manifest and Scan Exports", "**Multi-module loop:**"),
                       "--manifest-file")
    call = call.replace("<lang>", "python").replace("<manifest path>", "pyproject.toml")
    call = call.replace("--entry-file <entry path> [--entry-file <entry path>]...", "--entry-file src/acme/__init__.py")
    _run(call, run_dir)
    envelope = json.loads((run_dir / "extract.json").read_text(encoding="utf-8"))
    assert [e["name"] for e in envelope["exports"]] == ["greet"]
    assert (run_dir / "src" / "src" / "acme" / "__init__.py").read_bytes() == INIT_PY
    metadata = _render(run_dir, tmp_path)
    assert (metadata["exports"], metadata["version"], metadata["source_package"]) == (["greet"], "0.4.0", "acme")


@pytest.mark.skipif(sys.platform == "win32", reason="runs the step's commands through a POSIX shell")
def test_a_run_that_fetched_no_source_file_still_reaches_the_zero_exports_gate(tmp_path):
    """No manifest and no entry point (no candidate in the listing, a language with no row, a fetch
    that read none): the extractor is not called with no file, and step 4 still renders metadata.json."""
    parse = _section(_read(QUICK_EXTRACT), "### 3. Parse Manifest and Scan Exports", "### 4. ")
    rule = _section(parse, "**When §2 fetched neither a manifest nor an entry point**", "\n\n")
    for needle in ("the listing holds no candidate", "the language has no row in §2's table",
                   "do not run the extractor", "§4.5 decides what follows"):
        assert needle in rule, needle
    assert "Stage it the same way when the extractor exits non-zero" in parse
    # #599: no envelope is parsed in the prompt when the extractor is missing; the step halts instead.
    assert "in-prompt per-language regex parsing" not in parse
    # The call with no file exits 2 and leaves its redirect empty, which the renderer refuses.
    called = subprocess.run([sys.executable, str(EXTRACTOR), "--mode", "quick", "--language", "python",
                             "--source-root", str(tmp_path)], capture_output=True, text=True, check=False)
    assert called.returncode == 2 and called.stdout == ""
    run_dir = _run_folder(tmp_path, ["README.md", "docs/guide.md"])
    block = _bash_block(parse, "no source file was fetched")
    assert block.startswith("cat > \"{run_dir}/extract.json\" <<'SKF_JSON'\n")
    _run(block.replace("{language}", "markdown"), run_dir)
    envelope = json.loads((run_dir / "extract.json").read_text(encoding="utf-8"))
    assert (envelope["language"], envelope["exports"], envelope["warnings"]) == \
        ("markdown", [], ["no source file was fetched"])
    metadata = _render(run_dir, tmp_path)
    assert (metadata["exports"], metadata["version"], metadata["stats"]["exports_documented"]) == ([], "1.0.0", 0)
    render = _section(_read(COMPILE), "### 4. Generate Metadata JSON", "### 5. ")
    failed = _section(render, "If the renderer exits non-zero", "\n\n")
    assert "fix that file once" in failed and "If it fails a second time, render the envelope in-prompt" in failed


@pytest.mark.skipif(sys.platform == "win32", reason="runs the step's command through a POSIX shell")
def test_a_rerun_of_step_3_starts_with_no_extraction_file_of_the_old_scope(tmp_path):
    """§4.5 [R] and step 4's [S] run step 3 again: an old extract-added.json or extract-manifest.json
    must not reach the renderer, which takes every extraction file step 3 left."""
    extract = _read(QUICK_EXTRACT)
    first = _section(extract, "### 1. Read the Listing and README", "### 1.5. ")
    block = _bash_block(first, "rm -f")
    assert block == 'rm -f "{run_dir}"/extract*.json\n'
    assert first.index("rm -f") < first.index("{githubFetch}")
    assert "**re-execute step 3 from §1**" in extract
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _run(block, run_dir)  # a first run has nothing to clear
    kept = ["metadata-input.json", "sniff.json", "tree.json"]
    for name in ["extract.json", "extract-added.json", "extract-manifest.json", "extract-module-1.json", *kept]:
        (run_dir / name).write_text("{}", encoding="utf-8")
    _run(block, run_dir)
    assert sorted(p.name for p in run_dir.iterdir()) == kept


def test_each_module_extraction_is_named_by_its_position():
    """A Maven module path (modules/core, ../sibling) or a Gradle name (core:api) cannot name a file."""
    extract, compile_md = _read(QUICK_EXTRACT), _read(COMPILE)
    for text in (extract, compile_md):
        assert "extract-<module>" not in text
        assert "`{run_dir}/extract-module-<n>.json`" in text
    assert "`<n>` counting from 1 in `modules[]` order" in _section(extract, "**Multi-module loop:**", "\n\n")
    assert "of a multi-module build in `<n>` order" in compile_md


def test_a_truncated_listing_is_tried_and_reported():
    extract = _read(QUICK_EXTRACT)
    assert ("When the listing is `truncated` (GitHub cut a very large tree short), a path with no `*` or `?` "
            "that the listing lacks is read anyway") in extract
    report = _section(extract, "### 5. Report Extraction Summary", "### 6. ")
    assert "{If the fetch output's `truncated` was true, add:} - **Listing:** truncated by GitHub" in report


def test_the_snippet_version_is_the_one_metadata_json_gets():
    """The snippet and the headless line name the version the renderer writes, not the manifest's alone."""
    compile_md = _read(COMPILE)
    snippet = _section(compile_md, "### 3. Generate Context Snippet", "### 4. ")
    [rule] = [line for line in snippet.splitlines() if line.startswith("Its `{version}` is the version §4 gives")]
    for needle in ("`{target_version}` when step 1 parsed one from the target",
                   "else the first `version` set in step 3's extraction files", "else `1.0.0`"):
        assert needle in rule, needle
    headless = _section(compile_md, "### 5. Present Compiled Output for Review", "### 6. ")
    assert "metadata.json (version {metadata.version}, confidence {confidence})" in headless


BUILDER_TREE = ["README.md", "package.json", "skills/alpha/SKILL.md", "skills/alpha/assets/module.yaml",
                "skills/beta/SKILL.md", "skills/module-help.csv", "skills/module.yaml", "samples/demo/SKILL.md"]
ALPHA = (b"---\nname: alpha\ndescription: >\n  Builds alpha things.\n  Use when it's needed.\n---\n\n"
         b"# Alpha\n\n---\n\nname: not-frontmatter\n")
MODULE_HELP = (b"module,skill,display-name,menu-code,description,action,args,phase,preceded-by,followed-by\n"
               b"Demo,_meta,,,,,,,,\n"
               b'Demo,alpha,Build Alpha,BA,"Create, edit, or rebuild an alpha.",build,,anytime,,\n')
PYPROJECT = b'[project]\nname = "acme"\nversion = "0.4.0"\ndescription = "Acme\'s tools"\ndependencies = ["attrs"]\n'
INIT_PY = b"def greet(name):\n    return f\"Hi, {name}! It's {'me'}\"\n"
# A description that a single-quoted echo, or a double-quoted shell string, would break or rewrite.
DESCRIPTION = "Builds the module's skills: \"agents\", `$HOME` and it's done."


@pytest.fixture
def raw_github(monkeypatch):
    """A local server standing in for raw.githubusercontent.com: acme/lib at HEAD."""
    import http.server
    import threading
    files: dict[str, bytes] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server's name
            prefix = "/acme/lib/HEAD/"
            body = files.get(self.path[len(prefix):]) if self.path.startswith(prefix) else None
            self.send_response(200 if body is not None else 404)
            self.end_headers()
            self.wfile.write(body if body is not None else b"404: Not Found")

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("SKF_TEST_RAW_ROOT", f"http://127.0.0.1:{server.server_address[1]}")
    yield files
    server.shutdown()


def _run_folder(tmp_path: Path, paths: list[str]) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "tree.json").write_text(json.dumps({"status": "ok", "tree": paths, "truncated": False}),
                                       encoding="utf-8")
    shim = tmp_path / "fetch-shim.py"
    shim.write_text(
        "import importlib.util, os, sys\n"
        f"spec = importlib.util.spec_from_file_location('fetch', {str(GITHUB_FETCH)!r})\n"
        "mod = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(mod)\n"
        "mod.RAW_ROOT = os.environ['SKF_TEST_RAW_ROOT']\nmod._gh_raw = lambda *a: (None, 'no gh in this test')\n"
        "raise SystemExit(mod.main(sys.argv[1:]))\n", encoding="utf-8")
    return run_dir


def _run(block: str, run_dir: Path) -> None:
    """A step's bash block, its helpers run with this interpreter (the raw fetch against the local server)."""
    bash = _tool("bash")
    python = f'"{sys.executable}"'
    script = (block.replace("uv run {githubFetch}", f'{python} "{run_dir.parent / "fetch-shim.py"}"')
              .replace("uv run {skillsModuleHelper}", f'{python} "{SKILLS_MODULE}"')
              .replace("uv run {publicApiExtractor}", f'{python} "{EXTRACTOR}"')
              .replace("uv run {quickMetadataRenderer}", f'{python} "{RENDERER}"')
              .replace("{owner}/{repo}", "acme/lib").replace("{source_ref or HEAD}", "HEAD")
              .replace("{run_dir}", run_dir.as_posix()).replace("{repo_name}", "acme-module"))
    script = re.sub(r' \[--scope-hint "\{scope_hint\}"\]', "", script)
    script = re.sub(r' \[--package "[^"]*"\]', "", script)
    result = subprocess.run([bash, "-c", script], capture_output=True, text=True, check=False)
    assert result.returncode in (0, 3), result.stderr
    assert result.returncode == 0 or '"status": "partial"' not in result.stdout, result.stdout


def _render(run_dir: Path, tmp_path: Path) -> dict:
    """compile §4's staging heredoc and renderer call, filled in, with DESCRIPTION as the description."""
    block = _bash_block(_section(_read(COMPILE), "### 4. Generate Metadata JSON", "### 5. "), "SKF_JSON")
    skf_root = tmp_path / "project" / "_bmad" / "skf"
    skf_root.mkdir(parents=True)
    (skf_root / "VERSION").write_text("3.0.0\n", encoding="utf-8")
    values = {'"{repo_name}"': '"acme-module"', '"<the SKILL.md frontmatter description>"': json.dumps(DESCRIPTION),
              '<"{target_version}" or null>': "null", '"{language}"': '"python"',
              '"{resolved_url}"': '"https://github.com/acme/lib"', '"<path or empty>"': '""',
              '"<source_ref or empty>"': '""', '"<package name or empty>"': '""', '"<semver-range or empty>"': '""',
              '<"{language_hint}" or null>': "null", '<"{scope_hint}" or null>': "null",
              "<the --exports names as a JSON list, or null>": "null", "{project-root}": (tmp_path / "project").as_posix()}
    for placeholder, value in values.items():
        assert placeholder in block, placeholder
        block = block.replace(placeholder, value)
    _run(block, run_dir)
    staged = json.loads((run_dir / "metadata-input.json").read_text(encoding="utf-8"))
    assert staged["description"] == DESCRIPTION
    return json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))


def test_the_unknown_language_branch_asks_the_skills_module_helper():
    """W1 handoff: a Markdown-only skills repository has no language, and step 1 must not halt on it."""
    detect = _section(_read(RESOLVE_TARGET), "### 4. Detect Language", "### 5. ")
    auto = _section(detect, "3. **Auto-pick**", "4. **Multi-language gate**")
    # Step 1 sniffs under the scope hint as step 3 does, so both classify the same folder.
    assert _nested_bash_block(auto, " sniff ") == \
        'uv run {skillsModuleHelper} sniff --tree-file "{run_dir}/tree.json" [--scope-hint "{scope_hint}"]\n'
    assert "Pass `--scope-hint` when `scope_hint` is set, as step 3 does" in auto
    assert ("- **`skills_module` is true**: set `language` to `markdown` and `language_resolution` to `detected`"
            in auto)
    assert auto.index("set `language` to `markdown`") < auto.index("HARD HALT")
    tree = ["README.md", "LICENSE", "skills/docx/SKILL.md", "skills/pdf/SKILL.md"]
    detect_language = _load(SCRIPTS / "skf-detect-language.py", "skf_detect_language_for_quick_contract")
    assert detect_language.detect({"tree": tree})["detected_languages"] == []
    assert _load(SKILLS_MODULE, "skf_skills_module_for_quick_contract").sniff(tree, None, None)["skills_module"]


# --------------------------------------------------------------------------
# skills-module: the shape is library-like and reaches the compiled skill
# --------------------------------------------------------------------------


def test_skills_module_is_a_shape_with_no_gate():
    sniff = _sniff()
    shapes = _section(sniff, "**Classify as one of:**", "\n\n**If ")
    item = _section(shapes, "- **skills-module**", "\n- **library** (default)")
    for phrase in ("`skills_module` is true", "Skill folders alone qualify", "proceed with no gate",
                   "record `repo_shape: skills-module` and `skills_root`",
                   "A library with a manifest and one `skill/SKILL.md` stays a library"):
        assert phrase in item, phrase
    # The rule itself lives in the helper; the step reads its answer.
    for phrase in ("a folder that directly holds `module.yaml` or `module-help.csv`", "when `scope_hint` is set",
                   "Read its answer; do not re-derive it from the listing."):
        assert phrase in sniff, phrase
    assert "**If an awesome-list, docs-site or examples-only shape is detected**" in sniff
    assert "**If a non-library shape is detected**" not in sniff


def test_a_library_run_with_no_exports_names_the_scope_to_rerun_with():
    inventory = _section(_read(QUICK_EXTRACT), "### 4. Build Extraction Inventory", "### 4.5.")
    rule = _section(inventory, "- If the sniff's `suggested_scope` is set", "\n")
    assert "re-run with `--scope-hint {suggested_scope}` (a batch line's `scope={suggested_scope}`)" in rule
    assert "to document them as a skills module." in rule


def test_skills_module_exports_are_skill_names_then_menu_codes():
    text = _read(QUICK_EXTRACT)
    fetch = _section(text, "### 2. Fetch Source Files", "### 3. ")
    assert "the `module-help.csv` directly in the skills root (`<skills root>/module-help.csv`)" in fetch
    parse = _section(text, "### 3. Parse Manifest and Scan Exports", "### 4. ")
    branch = parse[parse.index("**Skills module** (`repo_shape: skills-module`)"):]
    assert "with that `--manifest-file` and no `--entry-file`" in branch
    assert branch.index("one `skill` per skill folder") < branch.index("one `menu-code` per `module-help.csv` row")
    assert "(the `_meta` row and rows with no skill left out)" in branch
    assert "Do not read the `SKILL.md` files or the CSV yourself" in branch
    inventory = _section(text, "### 4. Build Extraction Inventory", "### 4.5.")
    assert "  repo_shape: " in inventory and "  skills_root: " in inventory
    assert ("**Skills module** (`repo_shape: skills-module`): Unless `{overrides.exports}` is set, "
            "Key Exports lists the skills first, each with its description, then the menu codes, "
            "each with its description, display name and the skill it runs") in _read(COMPILE)
    template = _read(TEMPLATE)
    assert "then each menu code with its description, display name and the skill it runs" in template
    assert "`exports` lists the skill names, then the menu codes" in template


def test_extractor_warnings_send_section_3_after_the_module_they_name():
    """W3 handoff: a warning names a statement whose names the entry file alone cannot give."""
    parse = _section(_read(QUICK_EXTRACT), "### 3. Parse Manifest and Scan Exports", "### 4. ")
    [warnings] = [line for line in parse.splitlines() if line.startswith("- `warnings[]`")]
    for form in ("`export * from`", "a star import from the package", "an `__all__` built from another module",
                 "`pub use x::*`", "`module.exports = require(...)`", "an anonymous or conditional export"):
        assert form in warnings, form
    act = _section(parse, "**Act on the statements a warning names**", "\n\n")
    for needle in ("fetch it with §2's call and run the extractor again with it as one more `--entry-file`",
                   "Otherwise read the statement by eye", "`{run_dir}/extract-added.json`"):
        assert needle in act, needle
    assert "`{run_dir}/extract-added.json` when §3 staged it" in _read(COMPILE)


def test_the_scripts_and_assets_note_reads_the_sniff():
    [note] = [line for line in _read(COMPILE).splitlines() if line.startswith("**Scripts & Assets Note**")]
    assert "`{run_dir}/sniff.json`" in note and "`asset_dir_count` is above 0" in note
    sniff = _load(SKILLS_MODULE, "skf_skills_module_for_assets").sniff(["README.md", "src/templates/a.txt"], None, None)
    assert sniff["asset_dir_count"] == 1


def test_metadata_is_rendered_from_files_and_installed_by_the_atomic_writer():
    """W1 re-check determinism-4: no re-typed payload, [E] re-renders, step 5 installs the rendered file."""
    compile_md = _read(COMPILE)
    render = _section(compile_md, "### 4. Generate Metadata JSON", "### 5. ")
    block = _bash_block(render, "SKF_JSON")
    assert block.startswith("cat > \"{run_dir}/metadata-input.json\" <<'SKF_JSON'\n")
    assert block.rstrip("\n").endswith(
        'uv run {quickMetadataRenderer} --input "{run_dir}/metadata-input.json" --extraction "{run_dir}/extract.json" '
        '--skf-root "{project-root}/_bmad/skf" --output "{run_dir}/metadata.json"')
    assert '"exports": <the --exports names as a JSON list, or null>' in block
    assert '"dependencies"' not in block and "skf_version" not in block
    [edit] = [line for line in compile_md.splitlines() if line.startswith("- **IF E**")]
    assert "run §4's renderer command again" in edit and "Do not edit `metadata.json` by hand" in edit
    write = _read(WRITE_AND_VALIDATE)
    assert ("atomicWriteProbeOrder:\n  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'\n"
            "  - '{project-root}/src/shared/scripts/skf-atomic-write.py'\n") in write.split("---\n", 2)[1]
    assert _nested_bash_block(write, "metadata.json") == \
        'uv run {atomicWriteHelper} write --target "{skill_package}/metadata.json" < "{run_dir}/metadata.json"\n'
    assert "Resolve `{version}` ← the `version` of `{run_dir}/metadata.json`" in write
    finalize = _read(FINALIZE)
    removal = _bash_block(finalize, "rmdir")
    assert removal.startswith('case "{run_dir}" in */.skf-run/skf-quick-skill-*) rm -rf "{run_dir}/src" && ')


@pytest.mark.skipif(sys.platform == "win32", reason="runs the step's command through a POSIX shell")
def test_the_run_folder_removal_takes_the_fetched_files_and_nothing_else(tmp_path):
    bash = _tool("bash")
    removal = _bash_block(_read(FINALIZE), "rmdir")
    run_dir = tmp_path / "_bmad-output" / ".skf-run" / "skf-quick-skill-ab12cd34"
    (run_dir / "src" / "skills" / "alpha").mkdir(parents=True)
    for name in ("tree.json", "sniff.json", "warnings.jsonl", "skills-fetch.txt", "src/skills/alpha/SKILL.md"):
        (run_dir / name).write_text("x", encoding="utf-8")
    result = subprocess.run([bash, "-c", removal.replace("{run_dir}", run_dir.as_posix())], capture_output=True,
                            text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert not run_dir.exists()
    other = tmp_path / "elsewhere"
    (other / "src").mkdir(parents=True)
    subprocess.run([bash, "-c", removal.replace("{run_dir}", other.as_posix())], check=False)
    assert (other / "src").is_dir(), "the guard deletes nothing outside a quick-skill run folder"


# --------------------------------------------------------------------------
# #594: the hint flags, the language pick and the hints the retry gates take
# --------------------------------------------------------------------------


SINGLE_TARGET_FLAGS = ("`--language-hint`, `--scope-hint`, `--description` and `--exports` are single-target "
                       "flags: batch mode refuses them.")


def test_the_hint_flags_are_parsed_at_activation():
    skill = _read(SKILL)
    for flag, hint in (("--language-hint <lang>", "language_hint"), ("--scope-hint <path>", "scope_hint")):
        [row] = [line for line in skill.splitlines() if line.startswith(f"   | `{flag}` |")]
        assert f"Sets `{hint}`" in row and "batch mode refuses" not in row
        assert f"{hint} [optional, `{flag.split()[0]}`]" in skill
    assert skill.count(SINGLE_TARGET_FLAGS) == 1
    [overrides] = [line for line in skill.splitlines() if line.startswith("| **Overrides** |")]
    assert "`--language-hint`, `--scope-hint`" in overrides
    accept = _section(_read(RESOLVE_TARGET), "### 1. Accept User Input", "### 1b. ")
    assert ("when the invocation carried a target, take it, with `--language-hint` as `language_hint` and "
            "`--scope-hint` as `scope_hint` when they were passed") in accept
    assert "without the prompt below, in either mode" in accept
    before = _section(_read(BATCH_MODE), "## Before the Batch Starts", "## Input format")
    assert "`--language-hint` and `--scope-hint` are single-target flags too" in before
    codes = _section(_read(HALT_CONTRACT), "## Exit Codes", "## Result Contract")
    [row] = [line for line in codes.splitlines() if line.startswith("| 2 ")]
    assert "`--language-hint` or `--scope-hint` passed with `--batch`" in row
    # No step points at a flag activation does not parse.
    for path in HALT_FILES:
        for flag in re.findall(r"`(--[a-z-]+)", _read(path)):
            if flag.endswith("-hint"):
                assert flag in ("--language-hint", "--scope-hint"), (path.name, flag)


def test_the_multi_language_gate_offers_every_language():
    detect = _section(_read(RESOLVE_TARGET), "### 4. Detect Language", "### 5. ")
    gate = _section(detect, "4. **Multi-language gate**", "\nKeep `language_resolution`")
    assert "Select: [C] Continue with 1 · [2] to [n] Use that language · [A] Abort" in gate
    assert "{and so on, one numbered line per entry of `detected_languages`}" in gate
    [pick] = [line for line in gate.splitlines() if line.strip().startswith("- **IF 2 to n**")]
    assert "set `language` to that entry of `detected_languages`" in pick
    assert 'set `language_resolution: "user-confirmed"`' in pick
    assert "abort and re-run" not in gate
    [gates] = [line for line in _read(SKILL).splitlines() if line.startswith("| **Gates** |")]
    assert "multi-language disambiguation [C/n/A]" in gates


@pytest.mark.parametrize("path,option", [(QUICK_EXTRACT, "- **IF R**"), (COMPILE, "- **IF S**")],
                         ids=["zero-exports-retry", "review-rescope"])
def test_a_new_language_hint_at_a_retry_gate_is_a_hint(path, option):
    """W3 re-check architecture-1: the language a retry gate takes reaches step 3 and the summary as a hint."""
    [line] = [line for line in _read(path).splitlines() if line.startswith(option)]
    assert ("A non-empty new language hint sets `language` to it, `language_resolution` to `hint` and "
            "`detected_languages` to `[]`") in line


def test_a_package_id_on_another_host_tries_the_web_search_first():
    """W3 re-check enhancement-5: a Go module path or a Maven coordinate is searched before the redirect."""
    route = _section(_read(RESOLVE_TARGET), "### 2. Route by Kind", "### 3. ")
    for needle in ("the Go module path `go.uber.org/zap`", "an `unparsed` Maven coordinate `<group>:<artifact>`",
                   "run the web-search step of §3's `fallthrough` branch; show the redirect only when it finds no "
                   "GitHub URL", "`bmad-workflow-builder`"):
        assert needle in route, needle
    parse = _resolver().parse_target
    assert parse("go.uber.org/zap")["kind"] == "other-host"
    assert parse("com.google.guava:guava")["kind"] == "unparsed"


# --------------------------------------------------------------------------
# #609: --description and --exports with --batch halt with exit 2
# --------------------------------------------------------------------------


def test_the_halt_contract_has_the_input_invalid_code():
    text = _read(HALT_CONTRACT)
    codes = _section(text, "## Exit Codes", "## Result Contract")
    [row] = [line for line in codes.splitlines() if line.startswith("| 2 ")]
    for needle in ("input-invalid", "batch mode, before any target runs", "`--description`", "`--exports`",
                   "`--batch`", "`skf-quick-batch.py` missing", "step 1 §1 (a headless run with no target)"):
        assert needle in row, needle
    [row4] = [line for line in codes.splitlines() if line.startswith("| 4 ")]
    assert "batch mode §1 (the batch run folder cannot be written)" in row4
    # The envelope's fields moved from a table here to the JSON Schema.
    schema = json.loads(_read(ENVELOPE_SCHEMA))
    assert "input-invalid" in schema["properties"]["halt_reason"]["enum"]
    assert "input-invalid" in schema["properties"]["error"]["oneOf"][1]["properties"]["code"]["enum"]
    assert "on-activation" in schema["properties"]["phase"]["description"]
    assert ("`on-activation` for a halt before the run starts (SKILL.md On Activation, and batch mode's refusal "
            "of `--description` and `--exports` and of the hint flags)") in text


def test_batch_mode_refuses_the_flags_before_the_batch_starts():
    """SKILL.md On Activation step 5 only routes; batch-mode.md refuses the two flags before anything else."""
    text = _read(SKILL)
    step5 = _section(text, "5. **If `--batch` is set**", "\n\n6. ")
    assert "load and read `references/batch-mode.md` in full before anything else and follow it" in step5
    assert "HARD HALT" not in step5
    batch = _read(BATCH_MODE)
    before = _section(batch, "## Before the Batch Starts", "## Input format")
    assert batch.index("## Before the Batch Starts") < batch.index("## Execution")
    halt = before.index("HARD HALT with **exit code 2 (input-invalid)**")
    assert halt < before.index("Otherwise `--batch` implies `--headless`")
    assert "When any of the four was passed" in before and "before any target runs" in before
    assert '{"phase": "on-activation", "halt_reason": "input-invalid",' in before
    assert '"details": {"flags": [<the flags passed>], "batch_file": "<file>"}' in before
    assert "no batch summary is written" in before
    assert 'set `{headless_mode}` to true (log "headless: coerced by --batch" if it was false)' in before
    # SKILL.md states the refusal once, under the flag table; batch-mode.md enforces it.
    assert text.count("batch mode refuses") == 1 and SINGLE_TARGET_FLAGS in text
    for flag in ("--description", "--exports", "--batch"):
        [row] = [line for line in text.splitlines() if line.startswith(f"   | `{flag} ")]
        assert "refuses" not in row and "exit code 2" not in row, flag


def test_no_file_applies_the_two_flags_to_every_target():
    skill = _read(SKILL)
    batch = _read(BATCH_MODE)
    assert "apply globally to every target" not in skill
    assert "Global overrides apply to every target" not in batch
    [row] = [line for line in skill.splitlines() if line.startswith("   | `--batch <file>`")]
    assert "`--skip-snippet` and `--no-active-pointer` apply to every target in the batch" in row
    assert "`--description` and `--exports` are single-target overrides" in batch
    exit_code = batch[batch.index("## Exit code"):]
    assert ("A batch refused before its first target writes no batch summary. It exits with code `2` when "
            "`--description` or `--exports` was passed with `--batch`") in exit_code
    assert "and with code `4` when §1 cannot write the batch run folder" in exit_code


# --------------------------------------------------------------------------
# #609: the review preview shows one metadata.json line
# --------------------------------------------------------------------------


def test_the_preview_shows_one_metadata_line():
    preview = _section(_read(COMPILE), "### 5. Present Compiled Output for Review", "### 6. ")
    assert "{Display the JSON}" not in preview
    [line] = [line for line in preview.splitlines() if line.startswith("**metadata.json:**")]
    for field in ("version {metadata.version}", "confidence tier {metadata.confidence_tier}",
                  "{metadata.stats.exports_documented} exports documented"):
        assert field in line, field


# --------------------------------------------------------------------------
# #582 and #588: resolve-target reads the target through the resolver, gates
# an ambiguous package name and checks a pinned tag through the probe
# --------------------------------------------------------------------------


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _resolver():
    return _load(RESOLVER, "skf_resolve_package_for_quick_contract")


def _step(start: str, end: str) -> str:
    return _section(_read(RESOLVE_TARGET), start, end)


def test_every_example_the_prompt_lists_is_a_target_the_parser_reads():
    prompt = _step("### 1. Accept User Input", "### 1b. ")
    [line] = [line for line in prompt.splitlines() if line.startswith("Examples: ")]
    examples = re.findall(r"`([^`]+)`", line)
    assert "cognee@0.5.0" in examples and "requests==2.31.0" in examples
    parse = _resolver().parse_target
    for example in examples:
        assert parse(example)["kind"] in ("github", "package"), example
    assert parse("cognee@0.5.0")["target_version"] == "0.5.0"
    pin = parse("requests==2.31.0")
    assert (pin["package_name"], pin["registry"], pin["target_version"]) == ("requests", "pypi", "2.31.0")


def test_the_redirect_examples_parse_as_their_kind():
    route = _step("### 2. Route by Kind", "### 3. ")
    unparsed = route[route.index("- **`unparsed`**"):]
    parse = _resolver().parse_target
    prose = re.findall(r'"((?:I want|build me) [^"]+)"', unparsed)
    assert len(prose) == 2
    for sentence in prose:
        assert parse(sentence)["kind"] == "unparsed", sentence
    wanted = unparsed[unparsed.index("Quick Skill needs a package name"):]
    wanted = wanted[:wanted.index("\n")]
    for example in re.findall(r"`([^`]+)`", wanted):
        assert parse(example)["kind"] in ("github", "package"), example


def test_the_registry_data_holds_only_the_web_search():
    """#599: the resolver owns the target shapes and the registry chain, so the step never
    works them out by hand; registry-resolution.md keeps the judgment the script leaves out."""
    data = _read(REGISTRY_RESOLUTION)
    for heading in ("## Search", "## Pick the Repository", "## Result"):
        assert heading in data, heading
    assert '`"{package_name} github repository"`' in data and "at most 15 seconds" in data
    for stale in ("registry.npmjs.org", "pypi.org/pypi", "crates.io/api", "Target Shapes", "Fallback Chain",
                  "by hand"):
        assert stale not in data, stale
    frontmatter = _read(RESOLVE_TARGET).split("---\n", 2)[1]
    assert "registryResolutionData: 'references/registry-resolution.md'\n" in frontmatter
    registry = _step("### 3. Registry Resolution", "### 3a. ")
    [fallthrough] = [line for line in registry.splitlines() if line.startswith('- **On `status: "fallthrough"`**')]
    assert "Load {registryResolutionData} and run its web search for `{package_name}`." in fallthrough
    assert "§4" not in fallthrough, "the fallback is named by its file, not by a section number"
    # The Go and Maven examples it names parse as the kinds that reach the search.
    parse = _resolver().parse_target
    assert parse("go.uber.org/zap")["kind"] == "other-host"
    assert parse("com.google.guava:guava")["kind"] == "unparsed"


def test_a_missing_helper_halts_instead_of_a_hand_walk():
    """#599: resolve-target keeps no prose fallback for the resolver or the language detector;
    a missing or failing helper halts with exit 3, as a missing GitHub probe does."""
    text = _read(RESOLVE_TARGET)
    for stale in ("by hand", "rule walk documented in the helper's `--help`", "`Cargo.toml` → Rust",
                  "single source of truth"):
        assert stale not in text, stale
    parse = _step("### 1b. Parse the Target", "### 2. ")
    [resolve] = [line for line in parse.splitlines() if line.startswith("**Resolve `{packageResolver}`**")]
    for needle in ("If no candidate exists, or a call to it prints no JSON on stdout, HARD HALT with **exit code 3 "
                   "(resolution-failure)**, in interactive mode too", "`skf-resolve-package.py`",
                   '"details": {"cause": "<package-resolver-missing'):
        assert needle in resolve, needle
    detect = _step("### 4. Detect Language", "### 5. ")
    [delegate] = [line for line in detect.splitlines() if line.startswith("2. **Delegate the rule walk")]
    for needle in ("If no candidate exists, or its call below prints no JSON on stdout, HARD HALT with **exit code 3 "
                   "(resolution-failure)**", "{the call's first stderr line, or with no candidate:",
                   "`skf-detect-language.py`",
                   '"details": {"cause": "<detect-language-missing, or detect-language-error after a call that '
                   'printed no JSON>"}'):
        assert needle in delegate, needle
    codes = _section(_read(HALT_CONTRACT), "## Exit Codes", "## Result Contract")
    [row3] = [line for line in codes.splitlines() if line.startswith("| 3 ")]
    assert "package resolver missing or failing §1b" in row3 and "language detector missing or failing" in row3


@pytest.mark.skipif(sys.platform == "win32", reason="runs the step's heredoc through a POSIX shell")
@pytest.mark.parametrize("target", [
    "requests==2.31",
    "@vercel/og",
    "I'd like a `$HOME` skill, \"please\"",
    "https://github.com/vercel/next.js/tree/canary/packages/next",
], ids=["pypi-pin", "scoped", "quotes-backticks-dollar", "tree-url"])
def test_the_parse_call_hands_the_target_over_unchanged(target):
    bash = _tool("bash")
    block = _bash_block(_step("### 1b. Parse the Target", "### 2. "), "parse-target")
    assert block.startswith("uv run {packageResolver} parse-target <<'SKF_TARGET'\n{target}\nSKF_TARGET\n")
    script = block.replace("uv run {packageResolver}", f'"{sys.executable}" "{RESOLVER}"')
    script = script.replace("{target}", target)
    result = subprocess.run([bash, "-c", script], capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out == _resolver().parse_target(target)
    assert out["input"] == target


def test_every_kind_the_parser_returns_has_a_route():
    route = _step("### 2. Route by Kind", "### 3. ")
    kinds = _resolver().KINDS
    assert set(re.findall(r"\*\*`([a-z-]+)`\*\*", route)) == set(kinds)
    for kind in ("other-host", "local-path", "unparsed"):
        assert f"  - **`{kind}`**" in route, kind
    [gate] = [line for line in route.splitlines() if line.startswith("**GATE [default: HALT]**")]
    assert "exit code 3 (resolution-failure)" in gate and '"details": {"kind": "<kind>"}' in gate


def test_every_status_the_resolver_returns_has_a_branch():
    registry = _step("### 3. Registry Resolution", "### 3a. ")
    for status in _resolver().STATUSES:
        assert f'- **On `status: "{status}"`**' in registry, status
    block = _bash_block(registry, " resolve ")
    assert block == ("uv run {packageResolver} resolve {package_name} --timeout 10 [--registry {registry}] "
                     "[--language \"{language_hint}\"]\n")
    assert "Pass `--registry` when §2 set `registry`, and `--language` when a language hint was given" in registry


def test_a_registry_folder_or_a_tree_url_folder_is_the_default_scope():
    route = _step("### 2. Route by Kind", "### 3. ")
    assert "set `source_ref` ← `ref`, and `scope_hint` ← `subdir` when no scope hint was given" in route
    registry = _step("### 3. Registry Resolution", "### 3a. ")
    assert "when `source_subdir` is set and no scope hint was given, set `scope_hint` ← `source_subdir`" in registry


def test_every_route_names_the_skill_after_the_scripts_skill_name():
    """Step 5 writes the skill folder under `{repo_name}` and validates frontmatter `name`
    against it, so both routes bind it to the script's kebab-case skill_name, while `repo`
    keeps the repository name every `{owner}/{repo}` API path needs."""
    route = _step("### 2. Route by Kind", "### 3. ")
    [github] = [line for line in route.splitlines() if line.startswith("- **`github`**")]
    assert "`repo` ← `repo` and `repo_name` ← `skill_name`" in github
    registry = _step("### 3. Registry Resolution", "### 3a. ")
    [ok] = [line for line in registry.splitlines() if line.startswith('- **On `status: "ok"`**')]
    assert "`repo` ← `repo_name`, `repo_name` ← `skill_name`" in ok
    resolver = _resolver()
    assert resolver.parse_target("https://github.com/vercel/next.js")["skill_name"] == "next-js"
    assert "skill_name" in resolver.__doc__[resolver.__doc__.index("resolve output"):]
    write = _read(QS / "references" / "write-and-validate.md")
    assert "{skills_output_folder}/{repo_name}/{version}/{repo_name}/" in write
    assert "--skill-dir-name {repo_name}" in write


def test_a_found_url_and_a_dist_tag_go_through_the_parser():
    registry = _step("### 3. Registry Resolution", "### 3a. ")
    [fallthrough] = [line for line in registry.splitlines() if line.startswith('- **On `status: "fallthrough"`**')]
    assert "If found, take that URL as the target and go back to §1b." in fallthrough
    parse = _step("### 1b. Parse the Target", "### 2. ")
    assert "A `dist_tag` (an npm dist-tag such as `latest` or `canary`) pins no version" in parse
    assert "or a call to it prints no JSON on stdout" in parse
    resolver = _resolver()
    assert (resolver.parse_target("next@canary")["dist_tag"], resolver.parse_target("next@canary")["target_version"]) \
        == ("canary", None)


def test_an_ambiguous_name_offers_every_candidate_and_headless_keeps_the_pick():
    """The maintainer's resolver decision: interactive runs choose among every candidate,
    headless runs keep the first registry's pick and record also_found_in, never halting."""
    registry = _step("### 3. Registry Resolution", "### 3a. ")
    gate = registry[registry.index("**Ambiguous-name gate**"):registry.index("**If all methods fail")]
    assert "Select: [C] Continue with 1 · [2] to [n] Use that candidate · [U] Use another GitHub URL · " \
           "[X] Cancel and exit" in gate
    assert "then each `also_found_in` entry that has a `resolved_url`, numbered on from 2" in gate
    for option, needle in (("C", 'continue as on `status: "ok"`'), ("2 to n", "`owner` ← its `repo_owner`"),
                           ("U", "go back to §1b"), ("X", "exit code 6 (user-cancelled)")):
        [line] = [line for line in gate.splitlines() if line.startswith(f"- **IF {option}**")]
        assert needle in line, option
    [headless] = [line for line in gate.splitlines() if line.startswith("- **GATE [default: C]**")]
    for needle in ("keep the chain's pick and never halt", '--warning "{warning}"',
                   '"gate": "resolve-target.ambiguous-package"', 'continue as on `status: "ok"`'):
        assert needle in headless, needle
    assert "HARD HALT" not in headless
    resolver = _resolver()
    doc = resolver.__doc__[resolver.__doc__.index("resolve output"):]
    for field in ("also_found_in", "warning"):
        assert f"  {field}:" in doc, field


def test_the_tag_check_reads_the_github_probe_listing():
    text = _read(RESOLVE_TARGET)
    frontmatter = text.split("---\n", 2)[1]
    assert ("githubProbeProbeOrder:\n  - '{project-root}/_bmad/skf/shared/scripts/skf-github-probe.py'\n"
            "  - '{project-root}/src/shared/scripts/skf-github-probe.py'\n") in frontmatter
    check = _step("### 3a. Verify Target Version Tag", "### 4. ")
    assert "gh api" not in check
    block = _bash_block(check, " tags ")
    assert block == ("uv run {githubProbe} tags --repo {owner}/{repo} --version {target_version} "
                     "--name {package_name or repo_name} --limit 5\n")
    probe = _load(GITHUB_PROBE, "skf_github_probe_for_quick_contract")
    for field in ("match", "tags", "nearest"):
        assert field in probe._EMPTY["tags"], field
    assert '- **`status: "ok"` with `match` set**: set `source_ref` ← `match`' in check
    assert '- **`status: "ok"` with `match` null**: the listing lacks the tag.' in check
    assert "{the probe's `nearest`, else its `tags`" in check
    [unavailable] = [line for line in check.splitlines() if line.startswith('- **`status: "unavailable"`')]
    for needle in ("any other exit", "Do not report it missing.", "the probe's `message`",
                   "exit code 3 (resolution-failure)", "probe-error", "`{project-root}/_bmad/skf/shared/scripts/`"):
        assert needle in unavailable, needle


def test_the_contract_lists_the_new_step_1_halts():
    codes = _section(_read(HALT_CONTRACT), "## Exit Codes", "## Result Contract")
    [row3] = [line for line in codes.splitlines() if line.startswith("| 3 ")]
    assert "version tag missing or not checkable §3a" in row3
    assert "ambiguous" not in row3, "a headless run keeps the first registry's pick of an ambiguous name"
    [row6] = [line for line in codes.splitlines() if line.startswith("| 6 ")]
    assert "§3 ([X] at the ambiguous-name gate)" in row6
    [gates] = [line for line in _read(SKILL).splitlines() if line.startswith("| **Gates** |")]
    assert "ambiguous package name [C/n/U/X]" in gates and "headless keeps the first registry's pick" in gates


# --------------------------------------------------------------------------
# #593 and #586: every envelope goes through the shared emitter
# --------------------------------------------------------------------------


def _emitter():
    return _load(EMITTER, "skf_emit_result_envelope_for_quick_contract")


def _schema() -> dict:
    return json.loads(_read(ENVELOPE_SCHEMA))


# A HARD HALT that names its exit code, in either of the two forms the steps use.
HALT_RE = re.compile(r"HARD HALT(?:(?: the workflow)? with \*\*exit code (\d+) \(([a-z-]+)\)\*\*"
                     r"| \(exit code (\d+), ([a-z-]+)\))")
EMIT_HALT = 'emit-halt --workflow skf-quick-skill'
HALT_FILES = [SKILL, *sorted(p for p in (QS / "references").glob("*.md") if p.name != "halt-contract.md")]
# The phase a halt in each file names. batch-mode.md refuses --description and
# --exports for SKILL.md On Activation step 5, before the batch starts.
PHASES = {"SKILL.md": ("on-activation", "<the step's slug>"), "batch-mode.md": ("batch-mode", "on-activation")}
# The stage files a target's HARD HALT can fire in, steps 1 to 6.
STAGES = ("resolve-target.md", "ecosystem-check.md", "quick-extract.md", "compile.md", "write-and-validate.md",
          "finalize.md")


def _halt_sites() -> list[tuple[str, int, str, str]]:
    """(file, exit code, halt_reason, text up to the next halt or heading) for every HARD HALT."""
    sites = []
    for path in HALT_FILES:
        text = _read(path)
        matches = list(HALT_RE.finditer(text))
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            heading = re.search(r"\n#{1,6} ", text[m.end():end])
            if heading:
                end = m.end() + heading.start()
            code = int(m.group(1) or m.group(3))
            sites.append((path.name, code, m.group(2) or m.group(4), text[m.start():end]))
    return sites


def _staged(segment: str, name: str) -> str:
    """The JSON a segment stages as {run_dir}/<name>, inline or through a heredoc.

    A heredoc counts when it writes that file, or, for halt.json, when it pipes the
    payload straight to emit-halt: quick-extract §3 stages its empty extract.json
    envelope through a heredoc too, in the same segment as the extractor's halt.
    """
    inline = re.findall(r"[Ss]tage `(\{.*?\})` as `\{(?:run_dir|batch_dir)\}/" + re.escape(name) + "`", segment)
    heredoc = [payload for opener, payload
               in re.findall(r"([^\n]*)<<'SKF_JSON'\n\s*(\{.*?\})\n\s*SKF_JSON", segment, flags=re.S)
               if f'/{name}"' in opener or (name == "halt.json" and "emit-halt" in opener)]
    found = inline + heredoc
    assert len(found) == 1, f"expected one staged {name}, found {len(found)} in:\n{segment[:300]}"
    return found[0]


def _filled(payload: str) -> dict:
    """The staged JSON with its <...> list and object placeholders made empty."""
    payload = re.sub(r"\[<[^\]]*>\]", "[]", payload)
    payload = re.sub(r"\{<[^}]*>\}", "{}", payload)
    return json.loads(payload)


def test_the_scan_finds_every_hard_halt():
    per_file = {}
    for name, _, _, _ in _halt_sites():
        per_file[name] = per_file.get(name, 0) + 1
    # resolve-target.md gained the step 1 §4 halt for a file listing no probe could read, and the
    # halts for a missing resolver (§1b) and language detector (§4) in place of a by-hand walk;
    # SKILL.md gained the runtime halt for a missing python3 or uv.
    # quick-extract.md and write-and-validate.md gained the halts for a missing shipped helper (#599).
    assert per_file == {"SKILL.md": 3, "batch-mode.md": 3, "compile.md": 1, "ecosystem-check.md": 2,
                        "finalize.md": 1, "quick-extract.md": 5, "resolve-target.md": 12,
                        "write-and-validate.md": 6}
    assert set(per_file) - {"SKILL.md", "batch-mode.md"} == set(STAGES)


def _runtime_halt(segment: str) -> bool:
    """SKILL.md On Activation's halt for a missing python3 or uv, which the emitter cannot run for."""
    return "No envelope is printed: the emitter needs `uv` too." in segment[:600]


def test_a_missing_runtime_halts_before_the_run_folder():
    """W4 hand-off (W3 re-check enhancement-4): without uv no helper and no emitter can run,
    so activation checks for python3 and uv before anything else and halts with exit 3."""
    text = _read(SKILL)
    step1 = _section(text, "1. Read `{project-root}/_bmad/skf/config.yaml`", "\n2. ")
    for needle in ("`command -v python3` and `command -v uv`", "HARD HALT with **exit code 3 (resolution-failure)**",
                   "<https://docs.astral.sh/uv/getting-started/installation/>",
                   "No envelope is printed: the emitter needs `uv` too."):
        assert needle in step1, needle
    assert step1.index("command -v uv") < step1.index("mktemp -d") < step1.index("emit-halt")
    [site] = [s for s in _halt_sites() if s[0] == "SKILL.md" and _runtime_halt(s[3])]
    assert site[1:3] == (3, "resolution-failure")
    assert EMIT_HALT not in site[3][:site[3].index("Then resolve `{emitEnvelopeHelper}`")]
    codes = _section(_read(HALT_CONTRACT), "## Exit Codes", "## Result Contract")
    [row3] = [line for line in codes.splitlines() if line.startswith("| 3 ")]
    assert row3.split("|")[3].strip().startswith("SKILL.md On Activation step 1 (`python3` or `uv` missing)")
    assert ("except SKILL.md On Activation's halt for a missing `python3` or `uv`, which the emitter needs"
            in _read(HALT_CONTRACT))
    [exit_row] = [line for line in text.splitlines() if line.startswith("| **Exit codes** |")]
    assert "except On Activation step 1's check for `python3` and `uv`, which prints none" in exit_row


def test_no_stage_halts_without_an_exit_code():
    """#593: a halt the scan cannot see (no exit code, no emit command) leaves an automator with no result."""
    for path in HALT_FILES:
        uncoded = re.findall(r"[^\n]*\bHALT with(?! \*\*exit code \d+ \([a-z-]+\)\*\*)[^\n]*", _read(path))
        assert uncoded == [], (path.name, uncoded)
    gate = _section(_read(RESOLVE_TARGET), "**GATE [default: use args]**", "### 1b.")
    assert "HARD HALT with **exit code 2 (input-invalid)**" in gate
    assert '"reason": "Headless mode requires a target argument."' in gate


@pytest.mark.parametrize("site", range(33), ids=lambda i: f"halt-{i}")
def test_every_hard_halt_emits_through_the_emitter(site):
    """#593: each HARD HALT carries the inline emit command, and its payload builds the envelope it names,
    except the runtime halt, which no emitter can serve (test_a_missing_runtime_halts_before_the_run_folder)."""
    sites = _halt_sites()
    assert len(sites) == 33
    name, code, reason, segment = sites[site]
    if _runtime_halt(segment):
        assert name == "SKILL.md"
        return
    assert EMIT_HALT in segment and "--target stderr" in segment, (name, reason)
    payload = _filled(_staged(segment, "halt.json"))
    expected = {"not-skf-output", "flat-layout"} if code == 9 else {reason}
    if payload["halt_reason"].startswith("<"):
        assert code == 9, "only the ownership halt leaves its reason to the refusal it runs"
        payload["halt_reason"] = "not-skf-output"
    assert payload["halt_reason"] in expected, (name, payload["halt_reason"])
    assert payload["phase"] in PHASES.get(name, (name[:-len(".md")],)), (name, payload["phase"])
    # A halt stages its details beside halt_reason and reason; the emitter builds error from them.
    assert "error" not in payload, (name, "a hand-typed error object")
    emitter = _emitter()
    schema = json.loads(_read(ENVELOPE_SCHEMA))
    envelope = emitter.build_envelope(schema, payload, halt=True, decisions=[], warnings=[], stamps={
        "timestamp": "2026-10-01T00:00:00Z", "run_id": "ab12cd34", "result_path": None})
    assert emitter.contract_errors(schema, envelope) == [], (name, payload)
    assert (envelope["status"], envelope["exit_code"]) == ("error", code), name
    assert envelope["error"]["code"] == payload["halt_reason"] and envelope["error"]["message"] == payload["reason"]
    assert envelope["error"].get("details") == payload.get("details"), name
    # Result files only beside metadata.json: never at the ownership halt or before step 5 writes.
    writes = '--result-dir "{skill_package}"' in segment
    assert writes == (name in ("write-and-validate.md", "finalize.md") and code != 9), (name, code)


# Each shipped helper a stage runs: its stage, the helper's file, its cause, the fallback that is gone.
SHIPPED_HELPERS = [
    pytest.param("quick-extract.md", "{githubFetch}", "skf-github-fetch.py", "github-fetch-missing",
                 'gh api -H "Accept: application/vnd.github.raw"', id="github-fetch"),
    pytest.param("quick-extract.md", "{skillsModuleHelper}", "skf-skills-module.py", "skills-module-missing",
                 "classifies from the README alone", id="skills-module"),
    pytest.param("quick-extract.md", "{publicApiExtractor}", "skf-extract-public-api.py",
                 "public-api-extractor-missing", "in-prompt per-language regex parsing", id="public-api-extractor"),
    pytest.param("write-and-validate.md", "{atomicWriteHelper}", "skf-atomic-write.py", "atomic-writer-missing",
                 'cp "{run_dir}/metadata.json"', id="atomic-writer"),
    pytest.param("write-and-validate.md", "{frontmatterValidator}", "skf-validate-frontmatter.py",
                 "frontmatter-validator-missing", "skip frontmatter validation", id="frontmatter-validator"),
    pytest.param("write-and-validate.md", "{outputValidator}", "skf-validate-output.py", "output-validator-missing",
                 "skip body/snippet/metadata validation", id="output-validator"),
]


@pytest.mark.parametrize(("name", "placeholder", "script", "cause", "fallback"), SHIPPED_HELPERS)
def test_a_missing_shipped_helper_halts_instead_of_a_fallback(name, placeholder, script, cause, fallback):
    """#599 (W5 hand-off): no stage fetches, parses, copies or skips by hand when a shipped helper is missing;
    it halts with exit 3 as a missing resolver does, naming the helper in its message and its details."""
    text = _read(QS / "references" / name)
    assert fallback not in text, fallback
    [site] = [segment for file, code, reason, segment in _halt_sites()
              if file == name and f'"cause": "{cause}"' in segment]
    assert site.startswith("HARD HALT with **exit code 3 (resolution-failure)**, in interactive mode too")
    assert f"(`{script}`) is missing from `{{project-root}}/_bmad/skf/shared/scripts/`" in site
    assert f"is missing from `{{project-root}}/_bmad/skf/shared/scripts/`, so re-install SKF" in site
    before = text[:text.index(site)]
    resolve = before[before.rindex(f"`{placeholder}`"):]
    assert re.search(r"Resolve (?:\*\*)?`" + re.escape(placeholder) + "`", before), placeholder
    assert "first existing path" in resolve, resolve[:200]
    codes = _section(_read(HALT_CONTRACT), "## Exit Codes", "## Result Contract")
    [row3] = [line for line in codes.splitlines() if line.startswith("| 3 ")]
    assert f"`{script}`" in row3


def test_the_helper_halts_follow_the_runtime_halt_in_the_contract():
    codes = _section(_read(HALT_CONTRACT), "## Exit Codes", "## Result Contract")
    [row3] = [line for line in codes.splitlines() if line.startswith("| 3 ")]
    raised_by = row3.split("|")[3].strip()
    assert raised_by.startswith("SKILL.md On Activation step 1 (`python3` or `uv` missing); a shipped helper missing, "
                                "named in the message and in `details.cause` (step 3: `skf-github-fetch.py`, "
                                "`skf-skills-module.py` §1, `skf-extract-public-api.py` §3; step 5: "
                                "`skf-atomic-write.py` §2, `skf-validate-frontmatter.py` §4 when skill-check is "
                                "unavailable, `skf-validate-output.py` §5)")


def test_the_output_validator_runs_through_uv():
    text = _read(QS / "references" / "write-and-validate.md")
    assert 'uv run {outputValidator} "{skill_package}" --generated-by quick-skill --skip-frontmatter' in text
    assert "python3 {outputValidator}" not in text
    # The description guard keeps its own rule: without the guard, skill-check runs without --fix.
    assert "never run `--fix` unguarded" in text and "description guard unavailable" in text


def test_the_emitter_is_resolved_and_the_run_folder_made_before_the_first_halt():
    text = _read(SKILL)
    step1 = _section(text, "1. Read `{project-root}/_bmad/skf/config.yaml`", "\n2. ")
    for needle in ("`{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py`",
                   "`{project-root}/src/shared/scripts/skf-emit-result-envelope.py`",
                   'mktemp -d "{project-root}/_bmad-output/.skf-run/skf-quick-skill-XXXXXXXX"',
                   "Bind `{run_dir}` ← the path it prints"):
        assert needle in step1, needle
    assert text.index("Bind `{run_dir}`") < text.index("5. **If `--batch` is set**")


def test_the_halt_contract_defines_the_payload_and_the_batch_rule():
    text = _read(HALT_CONTRACT)
    block = _bash_block(text, "emit-halt")
    assert block.startswith("cat > \"{run_dir}/halt.json\" <<'SKF_JSON'\n")
    assert block.endswith('uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" '
                          '--target stderr < "{run_dir}/halt.json"\n')
    assert "`shared/scripts/schemas/skf-quick-skill-result-envelope.v1.json`" in text
    batch = text[text.index("## In `--batch`"):]
    for needle in ("ends the current target, not the batch", "return to `references/batch-mode.md` §3",
                   "control returns there even when the halt message reads as the end of the run",
                   "never exits the process", "under `--fail-fast`"):
        assert needle in batch, needle
    # A halt after a compaction resolves the emitter again from here, in SKILL.md's order.
    contract = _section(text, "## Result Contract on HARD HALT", "```bash")
    paths = re.findall(r"`(\{project-root\}/[^`]+/skf-emit-result-envelope\.py)`", contract)
    assert paths == re.findall(r"`(\{project-root\}/[^`]+/skf-emit-result-envelope\.py)`",
                               _section(_read(SKILL), "1. Read `{project-root}/_bmad/skf/config.yaml`", "\n2. "))
    assert paths == ["{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py",
                     "{project-root}/src/shared/scripts/skf-emit-result-envelope.py"]


@pytest.mark.parametrize("stage", STAGES)
def test_every_stage_carries_the_halt_event_and_the_batch_return(stage):
    """#585: after a compaction a halt site may read only its own file, so each stage's Rules say
    that a halt prints its event and, under --batch, returns to the batch instead of ending the run."""
    rules = _section(_read(QS / "references" / stage), "## Rules\n", "## Steps")
    for needle in ("A HARD HALT prints, after its envelope, this step's `halt` event when `{headless_mode}` is true.",
                   "Under `--batch` it ends only this target: then return to `references/batch-mode.md` §3, even "
                   "when the halt reads as the end of the run (`references/halt-contract.md`)."):
        assert needle in rules, (stage, needle)


def test_the_exit_code_table_is_the_schemas():
    table = _section(_read(HALT_CONTRACT), "## Exit Codes", "## Result Contract")
    rows = dict((int(code), meaning) for code, meaning in re.findall(r"^\| (\d+)\s+\| ([a-z-]+)\s+\|", table, re.M))
    codes = _schema()["$defs"]["skf-envelope"]["const"]["exit_codes"]
    derived = {codes[m]: m for m in rows.values() if m in codes}
    assert {code: meaning for code, meaning in rows.items() if code not in (0, 9)} == derived
    assert codes["not-skf-output"] == codes["flat-layout"] == 9 and rows[9] == "state-conflict"
    assert set(codes) == set(_schema()["properties"]["halt_reason"]["enum"]) - {None}


GATE_RE = re.compile(r"\*\*GATE \[default: ([A-Z])\]\*\*")


def test_every_headless_gate_records_its_decision():
    """SKILL.md's rule: a gate that resolves on its own records the decision the moment it decides."""
    schema = _schema()
    item = schema["properties"]["headless_decisions"]["items"]
    emitter = _emitter()
    recorded = []
    for path in HALT_FILES:
        text = _read(path)
        for m in GATE_RE.finditer(text):
            line = text[m.start():text.index("\n", m.start())]
            decision = _filled(_staged(line, "decision.json"))
            assert 'record --workflow skf-quick-skill --run-dir "{run_dir}" --decision' in line, path.name
            assert decision["default_action"] == decision["taken_action"] == m.group(1), path.name
            assert emitter._validate_against_schema(decision, item) == [], decision
            recorded.append(decision["gate"])
    assert sorted(recorded) == sorted(item["properties"]["gate"]["enum"])
    rules = _section(_read(SKILL), "## Workflow Rules", "## Stages")
    assert 'record --workflow skf-quick-skill --run-dir "{run_dir}" --decision' in rules
    assert "log each auto-decision" not in rules


VALIDATION_ISSUES = '`{"skill_md": <n>, "context_snippet": <n>, "metadata": <n>, "security": <n>}`'


def test_step_5_counts_the_validation_issues_in_the_schema_shape():
    """#586: {validation_issues} is the object the schema requires, counted from the validators' arrays."""
    report = _section(_read(QS / "references" / "write-and-validate.md"), "### 6. Report Validation Results",
                      "### 7. ")
    assert f"`{{validation_issues}}` ← {VALIDATION_ISSUES}" in report
    for count in ("`skill_md` counts skill-check's `diagnostics[]` (without skill-check, the frontmatter "
                  "validator's `issues[]`) plus `validation.skill_md.body[]`",
                  "`context_snippet` counts `validation.context_snippet.issues[]`",
                  "`metadata` counts `validation.metadata.issues[]`", "`security` counts skill-check's `security[]`",
                  "A check that did not run counts 0"):
        assert count in report, count
    finalize = _section(_read(FINALIZE), "### 3. Result Envelope and Result Contract", "### 4. ")
    assert f"`validation_issues` (step 5, the object {VALIDATION_ISSUES})" in finalize
    shape = json.loads(VALIDATION_ISSUES.strip("`").replace("<n>", "0"))
    issues = _schema()["properties"]["summary"]["properties"]["validation_issues"]
    assert list(shape) == issues["required"] and set(shape) == set(issues["properties"])


def _success_payload(section: str) -> str:
    """finalize §3's staged payload, each bare JSON value filled in as a run fills it."""
    # {validation_issues} takes the shape step 5 defines, its counts filled in.
    issues = VALIDATION_ISSUES.strip("`").replace("<n>", "1", 1).replace("<n>", "0")
    sample = {"{export count}": "12", "{quality_score}": "91", "{repo_shape}": "null",
              '"{extraction confidence}"': '"high"', '"{active_pointer}"': '"symlink"',
              "{language_resolution}": '"detected"', "{detected_languages}": '["python"]',
              "{zero_exports_rescue}": "null", "{validation_issues}": issues}
    payload = _staged(section, "result-context.json")
    for placeholder, value in sample.items():
        assert placeholder in payload, placeholder
        payload = payload.replace(placeholder, value)
    return payload


def test_the_success_payload_builds_the_schema_envelope():
    """#586: finalize §3 lists the summary once, and that payload is one the emitter accepts."""
    section = _section(_read(FINALIZE), "### 3. Result Envelope and Result Contract", "### 4. ")
    block = _bash_block(section, " emit ")
    assert block.rstrip("\n").endswith(
        'uv run {emitEnvelopeHelper} emit --workflow skf-quick-skill --run-dir "{run_dir}" '
        '--result-dir "{skill_package}" < "{run_dir}/result-context.json"')
    context = json.loads(_success_payload(section))
    # The result file keeps output-contract-schema.md's record shape: the payload gives the skill and the
    # outputs, and the emitter adds the payload's own status and summary and stamps the rest.
    assert set(context["result_contract"]) == {"skill", "outputs"}
    assert all(set(entry) == {"type", "path"} for entry in context["result_contract"]["outputs"])
    record = _emitter()._result_record(context, {}, "2026-10-01T00:00:00Z", "ab12cd34", [], [])
    assert (record["status"], record["summary"]) == ("success", context["summary"])
    assert "{the same summary object}" not in section
    schema = _schema()
    assert set(context["summary"]) == set(schema["properties"]["summary"]["properties"])
    assert set(context["outputs"]) == set(schema["properties"]["outputs"]["properties"])
    emitter = _emitter()
    envelope = emitter.build_envelope(schema, context, halt=False, decisions=[], warnings=[], stamps={
        "timestamp": "2026-10-01T00:00:00Z", "run_id": "ab12cd34", "result_path": None})
    assert emitter.contract_errors(schema, envelope) == []
    assert (envelope["status"], envelope["exit_code"], envelope["halt_reason"]) == ("success", 0, None)
    assert "result_contract" not in envelope
    # quick-extract records the skills-module shape, which the summary must admit.
    context["summary"]["repo_shape"] = "skills-module"
    shaped = emitter.build_envelope(schema, context, halt=False, decisions=[], warnings=[], stamps={
        "timestamp": "2026-10-01T00:00:00Z", "run_id": "ab12cd34", "result_path": None})
    assert emitter.contract_errors(schema, shaped) == []
    for field in ("quality_score", "confidence", "repo_shape", "language_resolution", "zero_exports_rescue"):
        assert section.count(f"`{field}`") == 1, f"the summary list names {field} once"


def test_every_target_of_a_batch_returns_to_batch_mode():
    """#585: a target's end, success or halt, never ends the batch; the health check runs once."""
    batch = _read(BATCH_MODE)
    record = _section(batch, "### 3. Record the Target", "### 4. ")
    for needle in ("step 6 §4 returns here", "every HARD HALT of steps 1 to 6 returns here",
                   "Control returns here even when the step that ended the target reads as the end of the run",
                   "uv run {quickBatchHelper} record --run-dir \"{batch_dir}\" --batch {batch}"):
        assert needle in record, needle
    summary = _section(batch, "### 4. Batch Summary", "## Batch summary contract")
    assert "execute `{healthCheckStepFile}`: the health check runs once per batch, here" in summary
    frontmatter = batch.split("---\n", 2)[1]
    assert "healthCheckStepFile: 'health-check.md'" in frontmatter
    assert ("quickBatchProbeOrder:\n  - '{project-root}/_bmad/skf/shared/scripts/skf-quick-batch.py'\n"
            "  - '{project-root}/src/shared/scripts/skf-quick-batch.py'\n") in frontmatter
    finalize = _read(FINALIZE)
    chain = finalize[finalize.index("### 4. Chain to Health Check"):]
    assert "return to `references/batch-mode.md` §3 instead of {nextStepFile}" in chain
    assert "control returns there even though this step reads as the end of the run" in chain
    assert "runs once per batch" in _read(HEALTH_CHECK)
    execution = _section(batch, "## Execution", "## Batch summary contract")
    for stale in ("After step 7 completes", "exit the batch loop immediately", "batch result list"):
        assert stale not in batch, stale
    assert "Nothing else carries over from the previous target" in execution


def test_the_batch_survives_a_compaction_and_the_helper_prints_its_events():
    """#587: the loop finds its folder and an ended target again, and no event is typed by hand."""
    batch = _read(BATCH_MODE)
    execution = _section(batch, "## Execution", "### 1. Start the Batch")
    assert ("After a compaction, `{batch_dir}` is the parent folder of the target's `{run_dir}`: the "
            "`{project-root}/_bmad-output/.skf-run/skf-quick-skill-*` folder that holds `batch.jsonl`.") in execution
    take = _section(batch, "### 2. Take the Next Target", "### 3. ")
    assert "the helper printed the target's `start` event on stderr: display it verbatim" in take
    [record] = [line for line in take.splitlines() if line.startswith('- **`"status": "record"`**')]
    assert "go to §3 with that `batch`, never running it again" in record
    for step, command in (("### 3. Record the Target", " record "), ("### 4. Batch Summary", " summarize ")):
        block = _bash_block(_section(batch, step, "\n### " if step.startswith("### 3") else "## Batch summary"),
                            command)
        assert block.rstrip("\n").endswith(" --target stderr"), step
    for line in ("prints the target's `done` or `fail` event on stderr: display it verbatim",
                 "prints the `batch_summary` event on stderr: display it verbatim"):
        assert line in batch, line
    assert "display that line verbatim on stderr" not in batch


def test_batch_start_halts_on_the_reason_the_helper_names():
    """batch-mode.md §1 has one branch per halt_reason skf-quick-batch.py start prints."""
    start = _section(_read(BATCH_MODE), "### 1. Start the Batch", "### 2. ")
    assert "the `halt_reason` of its stderr JSON names the halt" in start
    for reason, code in (("input-invalid", 2), ("write-failure", 4)):
        [branch] = [line for line in start.splitlines() if line.startswith(f"- **`{reason}`**")]
        assert f"HARD HALT with **exit code {code} ({reason})**" in branch, reason
    assert "or no path in `{quickBatchProbeOrder}` exists (an incomplete install)" in start


def test_every_way_out_of_a_step_prints_its_events():
    """Headless events: the [P] path out of an ecosystem match chains with its done and start events,
    and the health check's rule leaves room for its own done event."""
    eco = _read(QS / "references" / "ecosystem-check.md")
    [proceed] = [line for line in eco.splitlines() if line.startswith("- IF P:")]
    assert "print this step's `done` event and step 3's `start` event" in proceed
    [gate] = [line for line in eco.splitlines() if line.startswith("- **GATE [default: P]**")]
    assert gate.endswith("then go on as IF P does, its events included.")
    rules = _section(_read(HEALTH_CHECK), "## Rules\n", "## Steps")
    assert "except the headless `done` event below" in rules and "intervening action" not in rules


def test_finalize_never_writes_the_result_contract_by_hand():
    """determinism-3: with no emitter, the run says the contract was not written instead of typing it."""
    rules = _section(_read(FINALIZE), "## Rules\n", "## Steps")
    assert "Result contract writing is mandatory" not in rules
    assert ("Emit the result envelope and contract through the shared emitter, never by hand; when it is "
            "missing or fails twice, say the contract was not written and go on") in rules


def test_the_batch_exit_code_is_the_highest_failed_code():
    exit_code = _read(BATCH_MODE).split("## Exit code", 1)[1]
    assert "Without `--fail-fast`, the batch runs every target" in exit_code
    assert "otherwise the highest exit code among the failed targets" in exit_code
    assert "the exit code of the first failed target" not in exit_code
    assert "With `--fail-fast`, the batch stops at the first failed target and exits with that target's code" \
        in exit_code


def test_stage_files_carry_their_own_formats():
    """#593: no stage file points at a SKILL.md section that is not there, and the event formats
    live in the files the stages load, not in SKILL.md."""
    skill = _read(SKILL)
    headings = set(re.findall(r"^## (.+)$", skill, flags=re.M))
    for path in (QS / "references").glob("*.md"):
        for section in re.findall(r'SKILL\.md "([^"]+)"', _read(path)):
            assert section in headings, (path.name, section)
    assert '"status":"start"' not in skill and '"status":"halt"' not in skill
    events = _section(_read(HALT_CONTRACT), "## Headless Events", "## In `--batch`")
    for event in ('{"step":N,"name":"<slug>","status":"start"}', '{"step":N,"name":"<slug>","status":"done"}',
                  '{"step":N,"name":"<slug>","status":"halt","exit":<code>}'):
        assert event in events, event
    assert "`references/batch-mode.md` §2 set `target`, `language_hint` and `scope_hint`" in _read(RESOLVE_TARGET)
    assert "a batch line's own `target_version` otherwise stays" not in _read(RESOLVE_TARGET)


# --------------------------------------------------------------------------
# #596: the customization surface reaches the code that owns each rule
# --------------------------------------------------------------------------

CUSTOMIZE = QS / "customize.toml"


def _customize() -> dict:
    return tomllib.loads(_read(CUSTOMIZE))["workflow"]


def _comment_before(key: str) -> str:
    """The comment block directly above `key = ...` in customize.toml."""
    lines = _read(CUSTOMIZE).splitlines()
    [at] = [i for i, line in enumerate(lines) if line.startswith(f"{key} = ")]
    block = []
    for line in reversed(lines[:at]):
        if line.startswith("#"):
            block.append(line.lstrip("# "))
        elif block:
            break
    return " ".join(reversed(block))


def test_registry_resolution_path_is_gone():
    """The resolver hard-codes npm, PyPI and crates.io, so a house-style registry chain changed nothing."""
    assert "registry_resolution_path" not in _customize()
    for path in [SKILL, CUSTOMIZE, *(QS / "references").glob("*.md")]:
        text = _read(path)
        for stale in ("registry_resolution_path", "registryResolutionPath", "registry chain)"):
            assert stale not in text, (path.name, stale)


def test_each_path_scalar_names_the_default_skill_md_binds():
    workflow = _customize()
    step3 = _section(_read(SKILL), "3. **Resolve workflow customization.**", "\n4. ")
    for key, variable in (("skill_template_path", "skillTemplatePath"), ("batch_output_path", "batchOutputPath")):
        default = workflow[key]
        assert default, f"{key} ships its real default, not an empty string"
        assert f"- `{{{variable}}}` ← `workflow.{key}`, else `{default}`" in step3, key
        assert f"Default: {default}" in _comment_before(key), key
    assert (QS / workflow["skill_template_path"]).is_file()
    assert set(workflow) == {"activation_steps_prepend", "activation_steps_append", "persistent_facts",
                             "skill_template_path", "batch_output_path", "on_complete"}


def test_the_template_comment_names_what_a_copy_must_keep():
    """The step 5 validator and the snippet anchors read the template's headings; the renderer ignores it."""
    comment = _comment_before("skill_template_path")
    template = _read(TEMPLATE)
    for heading in ("## SKILL.md Section Structure", "## context-snippet.md Format", "## Overview",
                    "## Description", "## Key Exports", "## Usage Patterns", "## metadata.json Format"):
        assert f"`{heading}`" in comment, heading
        assert f"\n{heading}" in template, heading
    for anchor in ("#key-exports", "#usage-patterns"):
        assert f"`{anchor}`" in comment and f"SKILL.md{anchor}" in template, anchor
    assert "metadata.json is read from a copy only when skf-render-quick-metadata.py is missing or fails twice" \
        in comment
    validator = _load(SCRIPTS / "skf-validate-output.py", "skf_validate_output_for_quick_contract")
    body = validator.validate_body_structure(f"---\nname: x\n---\n{template}")
    assert body == [], "the bundled template carries every section the validator requires"


def test_the_hook_comments_match_when_skill_md_runs_them():
    prepend = _comment_before("activation_steps_prepend")
    assert "SKILL.md On Activation step 3" in prepend and "before the CLI flags are parsed" in prepend
    assert "uv probe" not in prepend
    step3 = _section(_read(SKILL), "3. **Resolve workflow customization.**", "\n4. ")
    assert "Run each `workflow.activation_steps_prepend` entry now, in order." in step3
    assert "Once step 4 has parsed the flags, before step 5 or 6 starts the run, run each " \
           "`workflow.activation_steps_append` entry in order." in step3
    assert "step 4 has parsed the CLI flags" in _comment_before("activation_steps_append")


def test_the_persistent_facts_default_says_how_to_drop_it():
    """#596 decision: a `!` entry in an override drops the default, and SKILL.md honours it."""
    assert _customize()["persistent_facts"] == ["file:{project-root}/**/project-context.md"]
    comment = _comment_before("persistent_facts")
    for needle in ("loads every project-context.md under {project-root}",
                   "set in {project-root}/_bmad/custom/skf-quick-skill.toml:",
                   'persistent_facts = ["!file:{project-root}/**/project-context.md"]'):
        assert needle in comment, needle
    for stale in ("cannot remove it", "add a literal fact"):
        assert stale not in comment, stale
    step3 = _section(_read(SKILL), "3. **Resolve workflow customization.**", "\n4. ")
    assert "an entry prefixed `!` drops each earlier entry it names and loads nothing itself" in step3


def test_the_on_complete_comment_is_the_call_finalize_makes():
    """#596 decision: the hook gets --result-path like the other per-skill workflows, and only when the
    emitter wrote the result file, so it never reads a missing file or an earlier run's -latest copy."""
    comment = _comment_before("on_complete")
    assert "a shell command, not an instruction" in comment
    assert "<on_complete> --result-path=<skill package>/quick-skill-result-latest.json" in comment
    assert "--skill-package" not in _read(CUSTOMIZE) and "--skill-package" not in _read(FINALIZE)
    for needle in ("is skipped when the emitter wrote no result file", "once per target that finishes",
                   "a HARD HALT never runs it", "never fails the workflow"):
        assert needle in comment, needle
    hook = _section(_read(FINALIZE), "**Post-completion hook (optional).**", "In a single-target run")
    assert _bash_block(hook, "{onCompleteCommand}") == (
        "{onCompleteCommand} --result-path={skill_package}/quick-skill-result-latest.json\n")
    assert ("and the emitter wrote the result contract (the line it printed has a non-null `result_path` and no "
            "`result_file_write_failed` warning naming `quick-skill-result-latest.json`)") in hook
    assert ("When the emitter failed twice, no path resolved for `{emitEnvelopeHelper}`, `result_path` is null, or a "
            "`result_file_write_failed` warning names `quick-skill-result-latest.json` (the copy alone failed), "
            "skip the hook and say so") in hook
    assert "Under `--batch` it runs once per target that reaches this section." in hook


def test_the_hook_finds_the_skill_package_from_its_result_path(tmp_path):
    """#596 decision: --result-path names a file inside the skill package, whose `outputs` list the package's
    files (the file holds no `skill_package` key). When only the -latest copy fails, the line keeps its
    result_path and a warning names the copy: the case the hook section skips on."""
    section = _section(_read(FINALIZE), "### 3. Result Envelope and Result Contract", "### 4. ")
    comment = _comment_before("on_complete")
    assert "The result file sits in the skill package" in comment and "skill_package" not in comment
    migration = _read(REPO / "changes" / "quick-on-complete-result-path.yaml").split("\nmigration:", 1)[1]
    assert "the parent of `--result-path`" in migration and "skill_package" not in migration

    def emit(package: Path) -> dict:
        package.mkdir(parents=True, exist_ok=True)
        run_dir = package.parent / "skf-quick-skill-ab12cd34"
        run_dir.mkdir()
        payload = _success_payload(section).replace("{skill_package}", package.as_posix())
        proc = subprocess.run([sys.executable, str(EMITTER), "emit", "--workflow", "skf-quick-skill", "--run-dir",
                               str(run_dir), "--result-dir", str(package)], input=payload.encode("utf-8"),
                              capture_output=True, timeout=60)
        assert proc.returncode == 0, proc.stderr
        [line] = [line for line in proc.stdout.decode("utf-8").splitlines()
                  if line.startswith("SKF_QUICK_SKILL_RESULT_JSON: ")]
        return json.loads(line.split(": ", 1)[1])

    package = tmp_path / "written" / "demo"
    envelope = emit(package)
    assert envelope["result_path"].rsplit("/", 1)[0] == package.as_posix()
    record = json.loads((package / "quick-skill-result-latest.json").read_bytes().decode("utf-8"))
    assert "skill_package" not in record
    assert [entry["path"] for entry in record["outputs"]] == [
        f"{package.as_posix()}/{name}" for name in ("SKILL.md", "context-snippet.md", "metadata.json")]
    # A folder that holds the copy's name: the per-run file is written, the copy is not.
    blocked = tmp_path / "copy-failed" / "demo"
    (blocked / "quick-skill-result-latest.json").mkdir(parents=True)
    envelope = emit(blocked)
    assert envelope["result_path"] is not None
    assert [warning for warning in envelope["warnings"] if warning.startswith("result_file_write_failed: ")
            and "quick-skill-result-latest.json" in warning]


# --------------------------------------------------------------------------
# #599: the ecosystem check asks no registry that does not exist
# --------------------------------------------------------------------------

ECOSYSTEM = QS / "references" / "ecosystem-check.md"


def test_the_ecosystem_check_makes_no_web_search():
    text = _read(ECOSYSTEM)
    steps = text[text.index("## Steps"):]
    assert steps.startswith("## Steps\n\nagentskills.io has no registry API")
    assert "make no query and no web search" in steps and "go on as IF P does" in steps
    for stale in ('"agentskills.io" "{repo_name}" skill', "Authority:** official", "Source:** agentskills.io",
                  "ecosystem_status", "5-second", "timeout", "STEP GOAL", "### "):
        assert stale not in text, stale


def test_the_ecosystem_gate_keeps_its_slug_and_exit_8():
    sites = [(code, reason) for name, code, reason, _ in _halt_sites() if name == "ecosystem-check.md"]
    assert sorted(sites) == [(6, "user-cancelled"), (8, "ecosystem-redirect")]
    text = _read(ECOSYSTEM)
    assert text.count('"phase": "ecosystem-check"') == 2 and text.count('"skill_package": null') == 2
    assert '"gate": "ecosystem-check.ecosystem-match"' in text
    codes = _section(_read(HALT_CONTRACT), "## Exit Codes", "## Result Contract")
    for code in ("6", "8"):
        [row] = [line for line in codes.splitlines() if line.startswith(f"| {code} ")]
        assert "step 2 (" in row and "step 2 §3" not in row, code
    assert "2 `ecosystem-check`" in _read(HALT_CONTRACT)
    [gates] = [line for line in _read(SKILL).splitlines() if line.startswith("| **Gates** |")]
    assert "step 2: ecosystem match [P/I/A] (none until agentskills.io has a registry API)" in gates


# --------------------------------------------------------------------------
# #600: one home per rule in SKILL.md and the stage files
# --------------------------------------------------------------------------


def test_compile_names_the_skill_after_its_folder():
    """W1 re-check leanness-1: the gerund preference could pull `name` off the folder step 5 writes."""
    text = _read(COMPILE)
    [rule] = [line for line in text.splitlines() if line.startswith("- `name` ")]
    assert rule == "- `name` is `{repo_name}`: step 5 writes that folder and validates the name against it."
    assert "gerund" not in text and "that's step 6" not in text
    assert "do not write files to disk (step 5 writes them)" in text
    snippet = _section(text, "### 3. Generate Context Snippet", "### 4. ")
    assert "If the assembled SKILL.md lacks a heading a snippet line anchors to, omit that line." in snippet
    for stale in ("fewer than 5", "Deep-tier", "Step-05 §2 will skip"):
        assert stale not in snippet, stale


def test_compile_shows_its_menu_once():
    text = _read(COMPILE)
    preview = _section(text, "### 5. Present Compiled Output for Review", "### 6. ")
    assert preview.rstrip().endswith('**Extraction confidence:** {confidence}"')
    assert "[Q] quit without writing" not in preview
    assert text.count("**Select:** [C] Continue to Validation") == 1
    gate = text[text.index("#### Gate:"):]
    assert "[E] re-renders" not in gate and "[S] discards" not in gate


def test_step_5_writes_metadata_first_in_its_listed_order():
    write = _section(_read(WRITE_AND_VALIDATE), "### 2. Write Deliverables", "### 3. ")
    assert "File 1" not in write and "File 3" not in write
    order = [write.index(f"{n}. `{{skill_package}}/{name}`") for n, name in
             ((1, "metadata.json"), (2, "SKILL.md"), (3, "context-snippet.md"))]
    assert order == sorted(order)
    assert ('Confirm after each write: "Written: metadata.json" / "Written: SKILL.md" / '
            '"Written: context-snippet.md"') in write


def test_step_5_does_not_retell_its_validators():
    text = _read(WRITE_AND_VALIDATE)
    for stale in ("The validator covers:", "### 6. Security Scan", "npx startup cost", "It checks frontmatter",
                  "skill-check is a file-based CLI", "go back to adjust", "Run [QS] with a different skill name"):
        assert stale not in text, stale
    assert "\n#" not in "\n" + text.split("---\n", 2)[1], "the probe orders carry no comments"
    headings = re.findall(r"^### (\d+)\. ", text, flags=re.M)
    assert headings == [str(n) for n in range(1, 8)], headings
    assert 'log "security scan skipped: skill-check unavailable"' in text
    assert "brief it with `@Ferris BS` and compile it with `@Ferris CS`" in text


def test_finalize_relays_the_flip_helpers_message():
    """W3 re-check leanness-4: the flip's exit 2 also means a held lock, so the halt shows the helper's message."""
    flip = _section(_read(FINALIZE), "### 1. Create Active Pointer", "### 2. ")
    assert _bash_block(flip, "flip-link").startswith("uv run {atomicWriteHelper} flip-link")
    assert "the `message` of the helper's" in flip and "another process holds its lock" in flip
    for stale in ("flock", "rename-over-symlink", "existing path is not a symlink or junction",
                  "Reuse the same values here"):
        assert stale not in flip, stale
    # The exit-code map tells an automator that a held lock also ends in exit 7.
    codes = _section(_read(HALT_CONTRACT), "## Exit Codes", "## Result Contract")
    [row7] = [line for line in codes.splitlines() if line.startswith("| 7 ")]
    assert ("step 6 §1 (the flip helper refused or failed: something that is not a link is at "
            "`{skill_group}/active`, or another process holds its lock)") in row7
    assert "non-link in place" not in row7


def test_skill_md_keeps_one_home_per_rule():
    text = _read(SKILL)
    for stale in ("runs as today", "in parallel (one batched tool-call message", "From preferences:",
                  "write-and-validate §1 runs the inventory's", "-latest.json", "so stage files don't have to repeat"):
        assert stale not in text, stale
    # "step 5" alone names write-and-validate in this table (`--skip-snippet`'s "step 5 §2").
    [batch] = [line for line in text.splitlines() if line.startswith("   | `--batch <file>` |")]
    assert "headless (On Activation step 5);" in batch
    assert "or if `{sidecar_path}/preferences.yaml` sets `headless_mode: true`" in text
    step5 = _section(text, "5. **If `--batch` is set**", "\n\n6. ")
    assert step5.strip() == "5. **If `--batch` is set**, load and read `references/batch-mode.md` in full before " \
                            "anything else and follow it."
