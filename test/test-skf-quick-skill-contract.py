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
holds quotes, backticks and `$`. Every example the step lists goes through
the parser, every kind and status the script returns has a branch, each
route names the skill after the script's skill_name, and the ambiguous-name
gate, the language hint, the web search for a name no registry resolves and
the tag check through skf-github-probe.py are pinned where the step states
them.

Every HARD HALT in SKILL.md and the stage files stages its payload and runs
the shared emitter: inline, or through the standard command its file's
Rules state once (#1173): each payload, filled in, builds an envelope the
skf-quick-skill schema accepts with the exit code the halt names, and no
halt is left without a code. Each headless gate records its auto-decision
under a gate name the schema lists, through the record command its file's
Rules state, finalize's success payload builds a valid envelope with the
summary the schema defines (step 5's validation counts in the schema's
shape), and under --batch every target's end (step 6, and every halt
through its stage's Rules) returns to batch-mode.md, which runs the health
check once. The one halt that emits nothing is activation's check for
python3 and uv, which the emitter itself needs.

customize.toml offers only settings a step reads: each path scalar ships the
default SKILL.md binds, the template comment names the headings the validator
and the snippet anchors need, and the hook comments say when SKILL.md runs
them. The ecosystem check makes no web search while agentskills.io has no
registry API, and keeps its slug; exit 8 and its gate stay reserved. A
missing resolver or language detector halts instead of being worked out by
hand, and so does every other shipped helper a step runs (the GitHub fetch
helper, the skills-module helper, the public-API extractor, the atomic
writer and the two validators): no file is fetched, parsed, copied or left
unchecked by hand (#599).

Step 5 takes the validation verdict from skill-check's JSON, not its exit
code (#885), runs skill-check with --no-security-scan and reads the security
scan as skipped, warn or pass from the JSON skf-security-scan.py prints,
since skill-check 1.2.0 passes none of the scanner's findings on (#892). It
tells a `--fix` rewrite from SKILL.md's hash before and after the call, since
skill-check 1.2.0's JSON lists no fix (#901).

A run loads no text it never acts on (#1173): each stage file states the
standard emit-halt and record commands once, in its Rules; step 2 only
passes through; halt-contract.md's exit-code table keeps Code and Meaning;
the caller contract lives in references/invocation-contract.md and the batch
summary schema, status rule and events in docs/workflows.md; the stages name
only the helper fields they read; and resolve-target §3 holds the web search
registry-resolution.md held.

A run takes each value a helper or a staged file holds from there (#1174):
compile renders metadata.json before the snippet, whose version is that
file's, and halts with exit 3 when the renderer is missing or fails twice;
the extractor writes the empty extraction envelope itself; the SKILL.md
and snippet drafts are staged in the run folder through quoted heredocs
and installed from there by the atomic writer, run here through bash over
a body holding `$HOME`, a backtick, `"` and `\\`; and finalize reports the
version and export count of the installed metadata.json.
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
INVOCATION_CONTRACT = QS / "references" / "invocation-contract.md"
DOCS = REPO / "docs" / "workflows.md"
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


def _paragraph(text: str, start: str) -> str:
    """The one blank-line-separated paragraph of `text` that opens with `start`."""
    found = [p for p in text.split("\n\n") if p.startswith(start)]
    assert len(found) == 1, f"expected one paragraph opening {start!r}, found {len(found)}"
    return found[0]


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
    assert len(calls) == 4, calls
    parser = _load(GITHUB_FETCH, "skf_github_fetch_for_quick_contract")._build_parser()
    for line in calls:
        line = re.sub(r"\[--limit <n>\] \[--exclude <glob>\]\.\.\. <path or glob>\.\.\.", "README.md", line)
        args = line.replace("uv run {githubFetch} ", "").replace("{owner}/{repo}", "acme/lib")
        args = args.replace("{source_ref or HEAD}", "HEAD").replace("{run_dir}", "/tmp/run")
        parsed = parser.parse_args([token.strip('"') for token in re.findall(r'"[^"]*"|\S+', args)])
        assert parsed.tree_file == "/tmp/run/tree.json" and parsed.dest == "/tmp/run/src"


@pytest.mark.skipif(sys.platform == "win32", reason="runs the step's commands through a POSIX shell")
def test_the_skills_module_chain_runs_from_the_listing_to_metadata(tmp_path, raw_github):
    """quick-extract §1 to §3 and compile §3 run as written: the listing, the sniff, the raw
    fetch, the skills-module envelope and the renderer, with a description holding quotes."""
    run_dir = _run_folder(tmp_path, BUILDER_TREE)
    raw_github.update({"README.md": b"# bmad-builder\n", "package.json": b'{"name": "bmad-builder", "main": ""}',
                       "skills/alpha/SKILL.md": ALPHA, "skills/beta/SKILL.md": b"# no frontmatter\n",
                       "skills/module-help.csv": MODULE_HELP})
    extract = _read(QUICK_EXTRACT)
    _run(_bash_block(_section(extract, "### 1. Read the Listing and README", "### 1.5. "), " sniff "), run_dir)
    sniffed = json.loads((run_dir / "sniff.json").read_text(encoding="utf-8"))
    assert (sniffed["skills_root"], sniffed["readme"]) == ("skills", "README.md")
    _run(_bash_block(_section(extract, "### 2. Fetch Source Files", "### 3. "), "skills-fetch.txt"), run_dir)
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


def _entries_step(extract: str, run_dir: Path, language: str) -> dict:
    """§2's entries call and fetch, as written: the extractor finds the entry files in the listing."""
    _run(_bash_block(_section(extract, "### 2. Fetch Source Files", "### 3. "), "--mode entries")
         .replace("<lang>", language), run_dir)
    return json.loads((run_dir / "entries.json").read_text(encoding="utf-8"))


def _extract_step(extract: str, run_dir: Path, language: str, manifest: str | None, entry_files: list[str]) -> dict:
    """§3's extractor call, filled in as the step says: the entries' manifest and each entry file."""
    call = _bash_block(_section(extract, "### 3. Parse Manifest and Scan Exports", "**Multi-module loop:**"),
                       "--manifest-file")
    call = call.replace("<lang>", language)
    call = call.replace("--manifest-file <manifest path>", f"--manifest-file {manifest}" if manifest else "")
    call = call.replace("--entry-file <entry path> [--entry-file <entry path>]...",
                        " ".join(f"--entry-file {path}" for path in entry_files))
    _run(call, run_dir)
    return json.loads((run_dir / "extract.json").read_text(encoding="utf-8"))


@pytest.mark.skipif(sys.platform == "win32", reason="runs the step's commands through a POSIX shell")
@pytest.mark.parametrize(("name", "folder"), [("acme", "acme"), ("Pillow", "PIL")], ids=["acme", "import-name"])
def test_the_library_chain_hands_the_files_to_the_extractor_by_path(tmp_path, raw_github, name, folder):
    """A source file holding an apostrophe reaches the extractor as written (#592), and its entry
    file is the one the extractor finds in the listing, whatever the import name (step 5b
    determinism-1: Pillow's package is PIL)."""
    init = f"src/{folder}/__init__.py"
    run_dir = _run_folder(tmp_path, ["README.md", "pyproject.toml", init, "tests/test_a.py", "docs/conf.py"])
    pyproject = PYPROJECT.replace(b'name = "acme"', f'name = "{name}"'.encode("utf-8"))
    raw_github.update({"README.md": b"# acme\n", "pyproject.toml": pyproject, init: INIT_PY})
    extract = _read(QUICK_EXTRACT)
    first = _section(extract, "### 1. Read the Listing and README", "### 1.5. ")
    _run(_bash_block(first, " sniff "), run_dir)
    assert json.loads((run_dir / "sniff.json").read_text(encoding="utf-8"))["skills_module"] is False
    _run(_bash_block(first, " sniff ").splitlines()[0].replace(" package.json", " pyproject.toml") + "\n", run_dir)
    entries = _entries_step(extract, run_dir, "python")
    assert (entries["manifest"], entries["entry_files"]) == ("pyproject.toml", [init])
    envelope = _extract_step(extract, run_dir, "python", entries["manifest"], entries["entry_files"])
    assert [e["name"] for e in envelope["exports"]] == ["greet"]
    assert (envelope["unlisted"], envelope["followed"]) == ([], [])
    assert (run_dir / "src" / "src" / folder / "__init__.py").read_bytes() == INIT_PY
    metadata = _render(run_dir, tmp_path)
    assert (metadata["exports"], metadata["version"], metadata["source_package"]) == (["greet"], "0.4.0", name)


NODENEXT_FILES = {
    "package.json": b'{"name": "acme", "type": "module", "main": "dist/index.js"}',
    "src/index.ts": b"export * from './core.js';\n",
    "src/core.ts": b"export class Core {}\nexport * from './util/index.js';\n",
    "src/util/index.ts": b"export function helper() {}\nexport const VERSION = '1';\n",
}


@pytest.mark.skipif(sys.platform == "win32", reason="runs the step's commands through a POSIX shell")
def test_the_follow_loop_reads_an_export_star_chain_to_its_end(tmp_path, raw_github):
    """step 5b determinism-2: a NodeNext `export * from './core.js'` chain is followed round by
    round until no module is left to read, by the extractor's --follow in §3's one call (step 5b
    gate run 2 determinism-1): no export comes from the README, and no round is run by hand."""
    run_dir = _run_folder(tmp_path, [*NODENEXT_FILES, "README.md"])
    raw_github.update({**NODENEXT_FILES, "README.md": b"# acme\n"})
    extract = _read(QUICK_EXTRACT)
    _run(_bash_block(_section(extract, "### 1. Read the Listing and README", "### 1.5. "), " sniff "), run_dir)
    entries = _entries_step(extract, run_dir, "ts")
    assert (entries["manifest"], entries["entry_files"]) == ("package.json", ["src/index.ts"])
    parse = _section(extract, "### 3. Parse Manifest and Scan Exports", "### 4. ")
    assert "follow.txt" not in parse and "at most 5 rounds" not in parse and "--follow-file" not in parse
    envelope = _extract_step(extract, run_dir, "ts", entries["manifest"], entries["entry_files"])
    assert envelope["followed"] == ["src/core.ts", "src/util/index.ts"]
    assert (run_dir / "src" / "src" / "util" / "index.ts").read_bytes() == NODENEXT_FILES["src/util/index.ts"]
    assert {e["name"] for e in envelope["exports"]} == {"Core", "helper", "VERSION"}
    assert envelope["unlisted"] == [] and not any("passes on names" in w for w in envelope["warnings"])


def _by_eye_rule(extract: str) -> str:
    """§3's paragraph on the `unlisted[]` records `--follow` left."""
    parse = _section(extract, "### 3. Parse Manifest and Scan Exports", "### 4. ")
    return _section(parse, "**Read the statements `unlisted[]` still names**", "\n\n")


def _star_sentence(record: dict, run_dir: Path) -> str:
    """compile §2's sentence for one `external_stars` record, filled in as the step writes it: the statement as
    the fetched file writes it at the record's line (the record's `statement` drops `type`), and "every type"
    for an `export type *`."""
    assemble = _section(_read(COMPILE), "### 2. Assemble SKILL.md", "### 3. ")
    [rule] = [line for line in assemble.splitlines() if line.startswith("**Stars from other packages**")]
    m = re.search(r'not a list item or table row: "(.*?)" `<source statement>` is ', rule)
    assert m, rule
    for needle in ("`<source statement>` is the statement as the source writes it at `{file}` line {line}, read "
                   "from `{run_dir}/src/{file}` without its closing `;`, not the record's `statement`, which "
                   "writes `export type *` as `export *`.",
                   'When that line is an `export type *`, which passes on only the package\'s types, write '
                   '"every type" for "every name".'):
        assert needle in rule, needle
    sentence = m.group(1)
    source_line = (run_dir / "src" / record["file"]).read_text(encoding="utf-8").splitlines()[record["line"] - 1]
    statement = source_line.strip().removesuffix(";")
    assert "`<source statement>`" in sentence and "every name" in sentence
    sentence = sentence.replace("<source statement>", statement)
    if statement.startswith("export type *"):
        sentence = sentence.replace("every name", "every type")
    for key in ("file", "line", "specifier"):
        assert "{" + key + "}" in sentence, key
        sentence = sentence.replace("{" + key + "}", str(record[key]))
    return sentence


def test_a_star_from_another_package_is_named_not_listed():
    """#958: since #946 Test Skill, like the recipe runner, gives an `export *` or `export type *` from another
    package no name, so each name §3 took for it from the README read as stale, a Medium `stale-documentation`
    gap per name on a correct skill. §3 lists no name for such a record and keeps it for the inventory's
    `external_stars`; compile names the star in one prose sentence and lists none of the package's names. A
    named re-export from another package still counts, and the by-eye rule's pinned wording still reads."""
    extract = _read(QUICK_EXTRACT)
    act = _by_eye_rule(extract)
    for needle in ("A record whose `statement` is an `export * from` another package (its `specifier` is no "
                   "relative path; the extractor writes `export type *` as `export *`) adds no name, from the "
                   "README or anywhere: the recipe runner and Test Skill leave such a star unresolved, so a name "
                   "listed for it reads as stale.",
                   "Keep each such record for §4's `external_stars`, and list names only for the others.",
                   "A named re-export from another package (`export { a, b } from 'pkg'`) is already in `exports[]`.",
                   "`--follow` read every module it could",
                   "read by eye only the `unlisted[]` records left, whose `module_file` is null",
                   "`{run_dir}/extract-added.json`"):
        assert needle in act, needle
    # The exception follows the by-eye listing it narrows and comes before the handoff to §5.
    assert (act.index("`{run_dir}/extract-added.json`") < act.index("adds no name, from the README or anywhere")
            < act.index("Leave the other warnings for §5."))
    inventory = _section(extract, "### 4. Build Extraction Inventory", "### 4.5.")
    lines = inventory.splitlines()
    [stars] = [line for line in lines if line.startswith("  external_stars: ")]
    assert stars == ("  external_stars: [{file, line, statement, specifier}: "
                     "each export * from another package §3 kept]")
    assert lines.index(stars) == lines.index("  exports: [{name, type, brief_description}]") + 1
    assemble = _section(_read(COMPILE), "### 2. Assemble SKILL.md", "### 3. ")
    [rule] = [line for line in assemble.splitlines() if line.startswith("**Stars from other packages**")]
    for needle in ("(`extraction_inventory.external_stars`)", "after the Key Exports list",
                   "one prose sentence per record, not a list item or table row",
                   "List none of that package's names."):
        assert needle in rule, needle
    assert (assemble.index("**Skills module** (`repo_shape: skills-module`)")
            < assemble.index("**Stars from other packages**") < assemble.index("**Scripts & Assets Note**"))


EXTERNAL_STAR_FILES = {
    "package.json": b'{"name": "acme", "main": "dist/index.js"}',
    "src/index.ts": b"export type * from '@vitest/spy';\nexport { z } from 'zod';\nexport function spyOn() {}\n",
}


@pytest.mark.skipif(sys.platform == "win32", reason="runs the step's commands through a POSIX shell")
def test_a_star_from_another_package_reaches_the_skill_as_a_sentence_not_names(tmp_path, raw_github):
    """#958: §1 to §3 run as written on an entry holding `export type * from '@vitest/spy'`, a named re-export
    from `zod` and a local function. The star is the one `unlisted[]` record, §3's rule keeps it for
    `external_stars` and leaves no record to read by eye, so no extract-added.json is staged, and compile §3's
    metadata.json lists the names Test Skill's Quick parser gives for the same file (`z`, `spyOn`; the star test
    in test-skf-test-skill-provenance-paths.py): the documented set is the surface, and nothing reads as stale.
    compile §2's sentence names the statement, its file and line and the package, and none of its names."""
    run_dir = _run_folder(tmp_path, [*EXTERNAL_STAR_FILES, "README.md"])
    raw_github.update({**EXTERNAL_STAR_FILES, "README.md": b"# acme\n"})
    extract = _read(QUICK_EXTRACT)
    _run(_bash_block(_section(extract, "### 1. Read the Listing and README", "### 1.5. "), " sniff "), run_dir)
    entries = _entries_step(extract, run_dir, "ts")
    assert (entries["manifest"], entries["entry_files"]) == ("package.json", ["src/index.ts"])
    envelope = _extract_step(extract, run_dir, "ts", entries["manifest"], entries["entry_files"])
    star = {"file": "src/index.ts", "line": 1, "statement": "export * from '@vitest/spy'",
            "specifier": "@vitest/spy", "module_file": None}
    assert envelope["unlisted"] == [star]
    assert [e["name"] for e in envelope["exports"]] == ["z", "spyOn"]
    assert envelope["followed"] == []
    # §3's rule, as written: an `export * from` whose specifier is no relative path adds no name and is kept.
    act = _by_eye_rule(extract)
    for needle in ("adds no name, from the README or anywhere", "Keep each such record for §4's `external_stars`"):
        assert needle in act, needle
    kept = [r for r in envelope["unlisted"]
            if r["statement"].startswith("export * from ") and not r["specifier"].startswith(".")]
    by_eye = [r for r in envelope["unlisted"] if r not in kept]
    assert (kept, by_eye) == ([star], [])
    # The rule leaves no record to read by eye, so §3 has no name to stage and the renderer reads extract.json alone.
    metadata = _render(run_dir, tmp_path)
    assert metadata["exports"] == [e["name"] for e in envelope["exports"]] == ["z", "spyOn"]
    external_stars = [{key: r[key] for key in ("file", "line", "statement", "specifier")} for r in kept]
    assert [_star_sentence(r, run_dir) for r in external_stars] == [
        "`export type * from '@vitest/spy'` (`src/index.ts` line 1) also exports every type of `@vitest/spy`: "
        "see that package's documentation."]


def test_no_entry_file_is_derived_from_the_package_name():
    """step 5b determinism-1: the table keeps the manifest column, and the entry files come from the listing."""
    text = _read(QUICK_EXTRACT)
    fetch = _section(text, "### 2. Fetch Source Files", "### 3. ")
    assert "| Language | Manifest |\n| --- | --- |\n" in fetch and "Entry-point patterns" not in fetch
    assert _bash_block(fetch, "--mode entries").splitlines() == [
        'uv run {publicApiExtractor} --mode entries --language <lang> --tree-file "{run_dir}/tree.json" '
        '--source-root "{run_dir}/src" [--scope "{scope_hint}"] --fetch-list "{run_dir}/entries.txt" '
        '> "{run_dir}/entries.json"',
        'uv run {githubFetch} --repo {owner}/{repo} --ref {source_ref or HEAD} --tree-file "{run_dir}/tree.json" '
        '--dest "{run_dir}/src" --patterns-file "{run_dir}/entries.txt"']
    assert "pass `--scope \"{scope_hint}\"` to the entries call" in fetch
    assert "Never derive an entry file from the package name yourself" in fetch
    for path in sorted((QS / "references").glob("*.md")):
        assert "{package}" not in _read(path), path.name
    loop = _section(text, "**Multi-module loop:**", "\n\n")
    assert '--scope "<its module_folders[] entry>"' in loop and "`core:api` read as `core/api`" not in loop
    assert "with the rules full mode follows" not in fetch, "the extractor's docstring owns the entry rules"


@pytest.mark.skipif(sys.platform == "win32", reason="runs the step's commands through a POSIX shell")
def test_a_language_with_no_entries_rule_takes_no_entry_file(tmp_path):
    """A language outside the extractor's list exits 1 and writes no fetch list: the step skips the
    fetch, and §3's extractor writes the empty envelope with that call's exit code, no helper text, as its
    reason (#1174)."""
    fetch = _section(_read(QUICK_EXTRACT), "### 2. Fetch Source Files", "### 3. ")
    for needle in ("For a language outside §3's list, or when the entries call exits non-zero",
                   "its `_error` in `{run_dir}/entries.json`; 2 for an input error, its error line on stderr",
                   "take no entry file and skip the fetch",
                   "writes its empty envelope, with the reason `entries call exited <its exit code>` in place of "
                   "`no source file was fetched` when the entries call ran."):
        assert needle in fetch, needle
    run_dir = _run_folder(tmp_path, ["Gemfile", "lib/acme.rb"])
    call = _bash_block(fetch, "--mode entries").splitlines()[0].replace("<lang>", "ruby")
    script = (call.replace("uv run {publicApiExtractor}", f'"{sys.executable}" "{EXTRACTOR}"')
              .replace("{run_dir}", run_dir.as_posix()))
    script = re.sub(r' \[--scope "\{scope_hint\}"\]', "", script)
    result = subprocess.run([_tool("bash"), "-c", script], capture_output=True, text=True, check=False)
    assert result.returncode == 1 and "unknown language" in (run_dir / "entries.json").read_text(encoding="utf-8")
    assert not (run_dir / "entries.txt").exists()
    # Nothing fetched yet, so the fetch folder does not exist: a known language still reads the listing.
    script = script.replace("--language ruby", "--language python")
    result = subprocess.run([_tool("bash"), "-c", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert (run_dir / "entries.txt").read_bytes() == b""


def test_the_summary_names_the_entry_points_not_found():
    summary = _section(_read(QUICK_EXTRACT), "### 5. Report Extraction Summary", "### 6. ")
    assert ("{If `{run_dir}/entries.json` lists `unresolved` entries, add:} - **Entry points not found:**"
            in summary)


@pytest.mark.skipif(sys.platform == "win32", reason="runs the step's commands through a POSIX shell")
def test_a_run_that_fetched_no_source_file_still_reaches_the_zero_exports_gate(tmp_path):
    """No manifest and no entry point (no candidate in the listing, a language with no row, a fetch
    that read none): the extractor is not called with no file, and step 4 still renders metadata.json.
    #1174: the extractor writes the empty envelope (--empty-envelope), and a §3 call that fails still
    writes it (--envelope-on-error), so no step types the envelope or escapes an error line into it."""
    parse = _section(_read(QUICK_EXTRACT), "### 3. Parse Manifest and Scan Exports", "### 4. ")
    rule = _section(parse, "**When §2 fetched neither a manifest nor an entry point**", "\n\n")
    for needle in ("the listing holds no candidate", "the language has no row in §2's table",
                   "do not run that call", "Have the extractor write the empty envelope instead",
                   "§4.5 decides what follows"):
        assert needle in rule, needle
    assert ("With `--envelope-on-error`, a call that exits non-zero (1 for a language quick mode does not parse, 2 "
            "for a file it cannot read) still writes the empty envelope, its one warning the error: go on as with "
            "an empty extraction.") in parse
    assert "Stage it the same way" not in parse and "escaped" not in rule
    for path in sorted(p for p in QS.rglob("*.md")):
        assert not re.search(r"extract[^\"\n]*\.json\" <<'SKF_JSON'", _read(path)), path.name
    # #599: no envelope is parsed in the prompt when the extractor is missing; the step halts instead.
    assert "in-prompt per-language regex parsing" not in parse
    # The call with no file and neither flag exits 2 and leaves its redirect empty, which the renderer refuses.
    called = subprocess.run([sys.executable, str(EXTRACTOR), "--mode", "quick", "--language", "python",
                             "--source-root", str(tmp_path)], capture_output=True, text=True, check=False)
    assert called.returncode == 2 and called.stdout == ""
    run_dir = _run_folder(tmp_path, ["README.md", "docs/guide.md"])
    block = _bash_block(parse, "no source file was fetched")
    assert block == ('uv run {publicApiExtractor} --mode quick --language "{language}" --empty-envelope '
                     '"no source file was fetched" > "{run_dir}/extract.json"\n')
    _run(block.replace("{language}", "markdown"), run_dir)
    envelope = json.loads((run_dir / "extract.json").read_text(encoding="utf-8"))
    assert (envelope["language"], envelope["exports"], envelope["warnings"]) == \
        ("markdown", [], ["no source file was fetched"])
    metadata = _render(run_dir, tmp_path)
    assert (metadata["exports"], metadata["version"], metadata["stats"]["exports_documented"]) == ([], "1.0.0", 0)
    # §3's call, a manifest it cannot read: exit 2, and extract.json holds the envelope the renderer reads.
    call = _bash_block(_section(_read(QUICK_EXTRACT), "### 3. Parse Manifest and Scan Exports",
                                "**Multi-module loop:**"), "--manifest-file")
    assert call.rstrip("\n").endswith('--envelope-on-error > "{run_dir}/extract.json"')
    call = (call.replace("<lang>", "python")
            .replace("--manifest-file <manifest path>", '--manifest-file \'a "b".toml\'')
            .replace(" --entry-file <entry path> [--entry-file <entry path>]...", ""))
    (run_dir / "src").mkdir()
    assert 'error: cannot read --manifest-file a "b".toml' in _run(call, run_dir, codes=(2,))
    envelope = json.loads((run_dir / "extract.json").read_text(encoding="utf-8"))
    assert (envelope["exports"], envelope["unlisted"]) == ([], [])
    [warning] = envelope["warnings"]
    assert warning.startswith('cannot read --manifest-file a "b".toml')
    assert _render(run_dir, tmp_path / "again")["stats"]["exports_documented"] == 0
    render = _section(_read(COMPILE), "### 3. Generate Metadata JSON", "### 4. ")
    failed = _section(render, "If the renderer exits non-zero", "\n\n")
    assert "fix that file once" in failed and "quick-extract §3's `--empty-envelope` call" in failed
    assert ("redirected to that file, with the reason `the renderer could not read <that file's name>`"
            in failed)
    assert "If it fails a second time, HARD HALT with **exit code 3 (resolution-failure)**" in failed
    assert "in-prompt" not in _read(COMPILE)


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
    """The snippet and the headless line name the version the renderer writes, not the manifest's alone.
    #1174: metadata.json is rendered first and the snippet reads its version there, so the model works
    out no precedence chain the renderer applies after it."""
    compile_md = _read(COMPILE)
    assert compile_md.index("### 3. Generate Metadata JSON\n") < compile_md.index("### 4. Generate Context Snippet\n")
    snippet = _section(compile_md, "### 4. Generate Context Snippet", "### 5. ")
    [rule] = [line for line in snippet.splitlines() if line.startswith("Its `{version}` is")]
    assert rule == "Its `{version}` is the `version` of `{run_dir}/metadata.json`, which §3 rendered."
    for stale in ("{target_version}", "extraction files", "`1.0.0`", "manifest"):
        assert stale not in snippet, stale
    render = _section(compile_md, "### 3. Generate Metadata JSON", "### 4. ")
    assert "§4 reads its `version`" in render
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
    # The extractor's --follow fetches through the same helper, loaded beside it.
    (tmp_path / "extract-shim.py").write_text(
        "import importlib.util, os, sys\n"
        f"spec = importlib.util.spec_from_file_location('extract', {str(EXTRACTOR)!r})\n"
        "mod = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(mod)\n"
        "fetch = mod._sibling('skf-github-fetch.py')\nfetch.RAW_ROOT = os.environ.get('SKF_TEST_RAW_ROOT', '')\n"
        "fetch._gh_raw = lambda *a: (None, 'no gh in this test')\n"
        "raise SystemExit(mod.main(sys.argv[1:]))\n", encoding="utf-8")
    return run_dir


def _run(block: str, run_dir: Path, codes: tuple[int, ...] = (0, 3)) -> str:
    """A step's bash block, its helpers run with this interpreter (the raw fetch against the local server);
    returns its stderr."""
    bash = _tool("bash")
    python = f'"{sys.executable}"'
    script = (block.replace("uv run {githubFetch}", f'{python} "{run_dir.parent / "fetch-shim.py"}"')
              .replace("uv run {skillsModuleHelper}", f'{python} "{SKILLS_MODULE}"')
              .replace("uv run {publicApiExtractor}", f'{python} "{run_dir.parent / "extract-shim.py"}"')
              .replace("uv run {quickMetadataRenderer}", f'{python} "{RENDERER}"')
              .replace("{owner}/{repo}", "acme/lib").replace("{source_ref or HEAD}", "HEAD")
              .replace("{run_dir}", run_dir.as_posix()).replace("{repo_name}", "acme-module"))
    script = re.sub(r' \[--scope-hint "\{scope_hint\}"\]', "", script)
    script = re.sub(r' \[--scope "\{scope_hint\}"\]', "", script)
    script = re.sub(r' \[--package "[^"]*"\]', "", script)
    result = subprocess.run([bash, "-c", script], capture_output=True, text=True, check=False)
    assert result.returncode in codes, result.stderr
    assert result.returncode == 0 or '"status": "partial"' not in result.stdout, result.stdout
    return result.stderr


def _render(run_dir: Path, tmp_path: Path) -> dict:
    """compile §3's staging heredoc and renderer call, filled in, with DESCRIPTION as the description."""
    block = _bash_block(_section(_read(COMPILE), "### 3. Generate Metadata JSON", "### 4. "), "SKF_JSON")
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
    # The rule itself lives in the helper; the step reads its answer and names only the fields it reads (#1173).
    assert "Read its answer; do not re-derive it from the listing." in sniff
    assert "this section reads its `root_files` (the files at the repository root), `skills_module` and `skills_root`" \
        in sniff
    doc = " ".join(_load(SKILLS_MODULE, "skf_skills_module_for_rules").__doc__.split())
    for rule in ("A skill folder holds its own SKILL.md.", "A module root is a folder that directly holds module.yaml "
                 "or module-help.csv and sits in no skill folder", "With --scope-hint, that folder is the only "
                 "candidate", "a candidate counts only when it is a module root or the root ships no code"):
        assert rule in doc, rule
    assert "**If an awesome-list, docs-site or examples-only shape is detected**" in sniff
    assert "**If a non-library shape is detected**" not in sniff


def test_a_library_run_with_no_exports_names_the_scope_to_rerun_with():
    inventory = _section(_read(QUICK_EXTRACT), "### 4. Build Extraction Inventory", "### 4.5.")
    rule = _section(inventory, "- If the sniff's `suggested_scope` is set", "\n")
    assert "re-run with `--scope-hint {suggested_scope}` (a batch line's `scope={suggested_scope}`)" in rule
    assert "to document them as a skills module." in rule
    # How the helper picks the folder is its own rule (#1173).
    assert "The helper names" not in rule
    doc = " ".join(_load(SKILLS_MODULE, "skf_skills_module_for_scope").__doc__.split())
    assert "(the module root with the most skill folders, else the folder with the most)" in doc


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
    assert "the paragraph below and §5 read them" in warnings
    # The forms the extractor warns about are its own to list (#1173): the step reads its warnings.
    doc = " ".join(_load(EXTRACTOR, "skf_extract_public_api_for_warnings").__doc__.split())
    for form in ("Warned: `export * from`, `module.exports = require(...)`", "a star import from the package is warned",
                 "a part that is no literal (another module's `__all__`) is warned", "a glob `pub use x::*` is warned",
                 "an `export default` that is anonymous or an expression"):
        assert form in doc, form
    [unlisted] = [line for line in parse.splitlines() if line.startswith("- `unlisted[]`")]
    assert "`{file, line, statement, specifier, module_file}`" in unlisted
    act = _section(parse, "**Read the statements `unlisted[]` still names**", "\n\n")
    for needle in ("`--follow` read every module it could",
                   "read by eye only the `unlisted[]` records left, whose `module_file` is null",
                   "`{run_dir}/extract-added.json`"):
        assert needle in act, needle
    assert "resolve the relative specifier the way the language does" not in parse
    assert "`{run_dir}/extract-added.json` when step 3 §3 staged it" in _read(COMPILE)


def test_the_scripts_and_assets_note_reads_the_sniff():
    [note] = [line for line in _read(COMPILE).splitlines() if line.startswith("**Scripts & Assets Note**")]
    assert "`{run_dir}/sniff.json`" in note and "`asset_dir_count` is above 0" in note
    sniff = _load(SKILLS_MODULE, "skf_skills_module_for_assets").sniff(["README.md", "src/templates/a.txt"], None, None)
    assert sniff["asset_dir_count"] == 1


def test_metadata_is_rendered_from_files_and_installed_by_the_atomic_writer():
    """W1 re-check determinism-4: no re-typed payload, [E] re-renders, step 5 installs the rendered file."""
    compile_md = _read(COMPILE)
    render = _section(compile_md, "### 3. Generate Metadata JSON", "### 4. ")
    block = _bash_block(render, "SKF_JSON")
    assert block.startswith("cat > \"{run_dir}/metadata-input.json\" <<'SKF_JSON'\n")
    assert block.rstrip("\n").endswith(
        'uv run {quickMetadataRenderer} --input "{run_dir}/metadata-input.json" --extraction "{run_dir}/extract.json" '
        '--skf-root "{project-root}/_bmad/skf" --output "{run_dir}/metadata.json"')
    assert '"exports": <the --exports names as a JSON list, or null>' in block
    assert '"dependencies"' not in block and "skf_version" not in block
    [edit] = [line for line in compile_md.splitlines() if line.startswith("- **IF E**")]
    assert "run §3's renderer command again" in edit and "Do not edit `metadata.json` by hand" in edit
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
    # #1174: compile stages the SKILL.md and snippet drafts here too.
    for name in ("tree.json", "sniff.json", "warnings.jsonl", "skills-fetch.txt", "src/skills/alpha/SKILL.md",
                 "SKILL.md", "context-snippet.md"):
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
    contract = _read(INVOCATION_CONTRACT)
    for flag, hint in (("--language-hint <lang>", "language_hint"), ("--scope-hint <path>", "scope_hint")):
        [row] = [line for line in skill.splitlines() if line.startswith(f"   | `{flag}` |")]
        assert f"Sets `{hint}`" in row and "batch mode refuses" not in row
        assert f"{hint} [optional, `{flag.split()[0]}`]" in contract
    assert skill.count(SINGLE_TARGET_FLAGS) == 1
    [overrides] = [line for line in contract.splitlines() if line.startswith("| **Overrides** |")]
    assert "`--language-hint`, `--scope-hint`" in overrides and "see SKILL.md On Activation step 4" in overrides
    accept = _section(_read(RESOLVE_TARGET), "### 1. Accept User Input", "### 1b. ")
    assert ("when the invocation carried a target, take it, with `--language-hint` as `language_hint` and "
            "`--scope-hint` as `scope_hint` when they were passed") in accept
    assert "without the prompt below, in either mode" in accept
    before = _section(_read(BATCH_MODE), "## Before the Batch Starts", "## Input format")
    assert "`--language-hint` and `--scope-hint` are single-target flags too" in before
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
    [gates] = [line for line in _read(INVOCATION_CONTRACT).splitlines() if line.startswith("| **Gates** |")]
    assert "multi-language disambiguation [C/n/A]" in gates


@pytest.mark.parametrize("path,option", [(QUICK_EXTRACT, "- **IF R**"), (COMPILE, "- **IF S**")],
                         ids=["zero-exports-retry", "review-rescope"])
def test_a_new_language_hint_at_a_retry_gate_is_a_hint(path, option):
    """W3 re-check architecture-1: the language a retry gate takes reaches step 3 and the summary as a hint."""
    [line] = [line for line in _read(path).splitlines() if line.startswith(option)]
    assert ("A non-empty new language hint sets `language` to it, `language_resolution` to `hint` and "
            "`detected_languages` to `[]`") in line


def test_the_rescope_option_loads_quick_extract_by_its_references_path():
    """#1112 (quick-skill architecture-1): only a stage's frontmatter keys name a file beside it, and every other
    bare path resolves from the skill root, so `[S]` at the compile review loads quick-extract.md by that path."""
    [line] = [line for line in _read(COMPILE).splitlines() if line.startswith("- **IF S**")]
    assert "then load `references/quick-extract.md` to re-extract" in line


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
    assert row.split("|")[2].strip() == "input-invalid"
    # #1173: each halt says what raises it at its site; the table keeps Code and Meaning.
    raised = sorted((name, _filled(_staged(segment, "halt.json"))["phase"])
                    for name, code, _, segment in _halt_sites() if code == 2)
    assert raised == [("batch-mode.md", "batch-mode"), ("batch-mode.md", "on-activation"),
                      ("resolve-target.md", "resolve-target")]
    [row4] = [line for line in codes.splitlines() if line.startswith("| 4 ")]
    assert row4.split("|")[2].strip() == "write-failure"
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
    # #1173: the refusals say their exit code and that no summary is written where they halt.
    before = _section(batch, "## Before the Batch Starts", "## Input format")
    assert "HARD HALT with **exit code 2 (input-invalid)** before any target runs" in before
    assert "no batch summary is written" in before
    start = _section(batch, "### 1. Start the Batch", "### 2. ")
    assert "no target runs and no batch summary is written" in start
    [write] = [line for line in start.splitlines() if line.startswith("- **`write-failure`**")]
    assert "(the batch run folder cannot be written" in write and "**exit code 4 (write-failure)**" in write


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


def test_several_targets_point_at_batch_mode():
    """#1175 enhancement-5: an input that names several packages or URLs is pointed at --batch, never told it looks
    like a description; a headless run halts with the redirect's first sentence as its reason."""
    route = _step("### 2. Route by Kind", "### 3. ")
    several, otherwise = [line for line in route.splitlines() if line.startswith("  - **`unparsed`**")]
    [redirects] = [line for line in route.splitlines() if line.startswith("- **`other-host`**, **`local-path`**")]
    assert "show the redirect for its kind, then, in interactive mode, wait for new input and go back to §1b" \
        in redirects
    assert several.startswith("  - **`unparsed`** with `targets` set: ")
    assert otherwise.startswith("  - **`unparsed`** otherwise: ")
    parse = _resolver().parse_target
    for example in ("lodash axios zod", "lodash, axios, zod"):
        assert f"`{example}`" in several, example
        parsed = parse(example)
        assert (parsed["kind"], parsed["targets"]) == ("unparsed", ["lodash", "axios", "zod"]), example
    redirect = route[route.index(several):route.index(otherwise)]
    for needle in ('"**Quick Skill compiles one target per run.** Your input names {the number of `targets`} targets '
                   '({the `targets`, comma-separated}).', "run Quick Skill with `--batch <file>`",
                   "Or name the one target to start with.\""):
        assert needle in redirect, needle
    description = route[route.index(otherwise):route.index("**GATE [default: HALT]**")]
    assert "looks like a description" not in redirect and "looks like a description" in description
    prose = re.findall(r'"((?:I want|build me) [^"]+)"', description)
    assert len(prose) == 2
    for sentence in prose:
        assert parse(sentence)["targets"] is None, sentence
    [gate] = [line for line in route.splitlines() if line.startswith("**GATE [default: HALT]**")]
    assert "emit the redirect for the kind (for `unparsed`, the one `targets` selects)" in gate
    halt = _filled(_staged(gate, "halt.json"))
    assert (halt["reason"], halt["details"]) == ("<the redirect's first sentence>", {"kind": "<kind>"})
    assert "  targets:" in _resolver().__doc__
    when = _paragraph(_section(_read(DOCS), "### Quick Skill (QS)", "**Agent:**"), "**When to Use:**")
    assert ("Quick Skill compiles one target per run, so an input that names several packages or URLs, such as "
            "`lodash axios zod`, is pointed at `--batch <file>`.") in when


def test_the_fallthrough_branch_holds_only_the_web_search():
    """#599: the resolver owns the target shapes and the registry chain, so the step never
    works them out by hand; the fallthrough branch keeps the judgment the script leaves out,
    the web search registry-resolution.md held until #1173."""
    registry = _step("### 3. Registry Resolution", "### 3a. ")
    [fallthrough] = [line for line in registry.splitlines() if line.startswith('- **On `status: "fallthrough"`**')]
    for needle in ('Search the web for `"{package_name} github repository"`, spending at most 15 seconds, and read '
                   "the top results for a `github.com/<owner>/<repo>` URL.",
                   "Take a URL only when that repository is the package's source",
                   "(`uber-go/zap` for `go.uber.org/zap`, `google/guava` for `com.google.guava:guava`)",
                   "keep a `/tree/<ref>/<folder>` URL whole when the package is one folder of a larger repository.",
                   "If web search also finds no such URL in those 15 seconds, HARD HALT below."):
        assert needle in fallthrough, needle
    for stale in ("registry.npmjs.org", "pypi.org/pypi", "crates.io/api", "by hand", "{registryResolutionData}"):
        assert stale not in fallthrough, stale
    assert "registryResolutionData" not in _read(RESOLVE_TARGET).split("---\n", 2)[1]
    assert "`src/skf-quick-skill/references/resolve-target.md` §3" in _resolver().__doc__
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


def _options(text: str) -> dict:
    """Each `- **IF ...**` and `- **GATE [default: ...]**` bullet of `text`, at any indent, by its label."""
    found = {}
    for line in text.splitlines():
        m = re.match(r"\s*- \*\*(IF [^*]+|GATE \[default: [A-Z]+\])\*\*", line)
        if m:
            assert m.group(1) not in found, m.group(1)
            found[m.group(1)] = line
    return found


def test_the_missing_tag_gate_offers_the_nearest_tags():
    """#1175 enhancement-3: a pinned version no tag names offers the probe's nearest tags, the default branch or a
    cancel in an interactive run; a headless run, and a listing no probe could read, still halt with exit 3."""
    check = _step("### 3a. Verify Target Version Tag", "### 4. ")
    gate = _section(check, '- **`status: "ok"` with `match` null**', '- **`status: "unavailable"`')
    assert ('{the probe\'s `nearest`, else its `tags`, one numbered line each, or "(none: the repo has no tags)"}'
            in gate)
    assert ("Select: [1] to [n] Build from that tag · [D] Drop the version and build from {`source_ref` when set, "
            "else the default branch} · [X] Cancel and exit") in gate
    assert "With no tag listed, offer only [D] and [X]." in gate
    options = _options(gate)
    assert list(options) == ["IF 1 to n", "IF D", "IF X", "GATE [default: HALT]"]
    assert "set `source_ref` ← that tag" in options["IF 1 to n"] and "clear `target_version`" in options["IF 1 to n"]
    assert "clear `target_version` and keep `source_ref` (a `/tree/` URL's ref, else unset)" in options["IF D"]
    for option in ("IF 1 to n", "IF D"):
        assert "Proceed to §4." in options[option] and "HALT" not in options[option], option
    assert "HARD HALT with **exit code 6 (user-cancelled)**" in options["IF X"]
    cancel = _filled(_staged(options["IF X"], "halt.json"))
    assert (cancel["phase"], cancel["halt_reason"], cancel["skill_package"]) == ("resolve-target", "user-cancelled",
                                                                                 None)
    headless = options["GATE [default: HALT]"]
    for needle in ("in headless mode, show the message without its Select line",
                   '"Re-run with one of these tags, or omit the version to auto-detect from the default branch."',
                   "HARD HALT with **exit code 3 (resolution-failure)**"):
        assert needle in headless, needle
    halt = _filled(_staged(headless, "halt.json"))
    assert halt["reason"] == "Tag {target_version} not found in {owner}/{repo}."
    assert halt["details"] == {"requested_version": "{target_version}", "available_tags": []}
    [unavailable] = [line for line in check.splitlines() if line.startswith('- **`status: "unavailable"`')]
    assert "Select:" not in unavailable and "HARD HALT with **exit code 3 (resolution-failure)**" in unavailable
    assert ("A listing no probe could read halts in interactive mode too: only a listing that lacks the tag offers "
            "the choice.") in check
    assert "do not re-prompt" not in check
    [gates] = [line for line in _read(INVOCATION_CONTRACT).splitlines() if line.startswith("| **Gates** |")]
    assert "missing version tag [n/D/X] (headless halts with exit 3)" in gates
    [row1] = [line for line in _read(SKILL).splitlines() if line.startswith("| 1 | Resolve Target |")]
    assert row1.endswith("| Conditional (no target, an ambiguous one, or a missing tag) |")
    when = _paragraph(_section(_read(DOCS), "### Quick Skill (QS)", "**Agent:**"), "**When to Use:**")
    # [D] keeps a /tree/ URL's ref (IF D), so the docs name that branch beside the default one.
    assert ("an interactive run lists the nearest tags and offers to build from one of them, to drop the version and "
            "build from the default branch (or from the branch a `/tree/` URL names), or to cancel; a headless run "
            "stops with exit `3` (`resolution-failure`)") in when
    # The other user-doc copies of the rule no longer say that every run stops.
    how = _read(REPO / "docs" / "how-it-works.md")
    assert ("When it doesn't, an interactive run lists the nearest tags and offers to build from one of them, to drop "
            "the version or to cancel, and a headless run stops.") in how and "stops if it doesn't" not in how
    concepts = _read(REPO / "docs" / "concepts.md")
    assert ("If no tag matches, Quick Skill lists the tags it found and offers to build from one of them, to drop the "
            "version or to cancel (a headless run stops)") in concepts
    assert "Quick Skill stops and lists the tags" not in concepts


def test_the_new_step_1_halts_name_their_codes():
    """#1173: the halt sites, not a Raised by column, say what each step 1 halt raises."""
    check = _step("### 3a. Verify Target Version Tag", "### 4. ")
    tag_halts = [(code, reason) for name, code, reason, segment in _halt_sites()
                 if name == "resolve-target.md" and segment in check]
    # #1175: a missing tag offers the nearest tags; its [X] cancels, and a headless run still halts with exit 3.
    assert tag_halts == [(6, "user-cancelled"), (3, "resolution-failure"), (3, "resolution-failure")]
    registry = _step("### 3. Registry Resolution", "### 3a. ")
    gate = registry[registry.index("**Ambiguous-name gate**"):registry.index("**If all methods fail")]
    [cancel] = [line for line in gate.splitlines() if line.startswith("- **IF X**")]
    assert "HARD HALT with **exit code 6 (user-cancelled)**" in cancel
    [headless] = [line for line in gate.splitlines() if line.startswith("- **GATE [default: C]**")]
    assert "HARD HALT" not in headless, "a headless run keeps the first registry's pick of an ambiguous name"
    [gates] = [line for line in _read(INVOCATION_CONTRACT).splitlines() if line.startswith("| **Gates** |")]
    assert "ambiguous package name [C/n/U/X]" in gates and "headless keeps the first registry's pick" in gates


# --------------------------------------------------------------------------
# #593 and #586: every envelope goes through the shared emitter
# --------------------------------------------------------------------------


def _emitter():
    return _load(EMITTER, "skf_emit_result_envelope_for_quick_contract")


def _schema() -> dict:
    return json.loads(_read(ENVELOPE_SCHEMA))


# SKILL.md On Activation step 1: the runtime check, the config, the run folder and the helpers.
STEP_1 = "1. **Check the runtime, then load the config and the helpers.**"
# A HARD HALT that names its exit code, in either of the two forms the steps use.
HALT_RE = re.compile(r"HARD HALT(?:(?: the workflow)? with \*\*exit code (\d+) \(([a-z-]+)\)\*\*"
                     r"| \(exit code (\d+), ([a-z-]+)\))")
EMIT_HALT = 'emit-halt --workflow skf-quick-skill'
# The standard commands a site that names none of its own takes from its file's Rules (#1173).
EMIT_COMMAND = ('uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" '
                '--target stderr < "{run_dir}/halt.json"')
RECORD_COMMAND = ('uv run {emitEnvelopeHelper} record --workflow skf-quick-skill --run-dir "{run_dir}" '
                  '--decision < "{run_dir}/decision.json"')
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


def _rules(name: str) -> str:
    """The rules every site of a HALT_FILES file follows: SKILL.md's Workflow Rules, a stage's ## Rules."""
    if name == "SKILL.md":
        return _section(_read(SKILL), "## Workflow Rules", "## Stages")
    return _section(_read(QS / "references" / name), "## Rules\n", "## Steps")


def _staged(segment: str, name: str) -> str:
    """The JSON a segment stages as {run_dir}/<name>, inline or through a heredoc.

    A heredoc counts when it writes that file, or, for halt.json, when it pipes the
    payload straight to emit-halt: compile §3 stages metadata-input.json through a
    heredoc in the same segment as the halt for a missing renderer.
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
    # SKILL.md gained the runtime halt for a missing python3 or uv, then the halts for a config the
    # preflight cannot load and for a missing helper of any stage (#1117).
    # quick-extract.md and write-and-validate.md gained the halts for a missing shipped helper (#599), and
    # write-and-validate.md the one for a missing validation summarizer (#1120).
    # batch-mode.md gained the halts for a failing next, a second failing record and a failing summarize (#903).
    # ecosystem-check.md lost its two, which no input reached until agentskills.io has a registry API (#1173).
    # compile.md gained the halts for a metadata renderer that is missing or fails twice (#1174).
    # resolve-target.md gained the [X] cancel of the missing-tag gate (#1175).
    assert per_file == {"SKILL.md": 5, "batch-mode.md": 6, "compile.md": 3, "finalize.md": 1,
                        "quick-extract.md": 5, "resolve-target.md": 13, "write-and-validate.md": 7}
    assert set(per_file) - {"SKILL.md", "batch-mode.md"} == set(STAGES) - {"ecosystem-check.md"}


def _runtime_halt(segment: str) -> bool:
    """SKILL.md On Activation's halt for a missing python3 or uv, which the emitter cannot run for."""
    return "No envelope is printed: the emitter needs `uv` too." in segment[:600]


def test_a_missing_runtime_halts_before_the_run_folder():
    """W4 hand-off (W3 re-check enhancement-4): without uv no helper and no emitter can run,
    so activation checks for python3 and uv before anything else and halts with exit 3."""
    text = _read(SKILL)
    step1 = _section(text, STEP_1, "\n2. ")
    for needle in ("`command -v python3` and `command -v uv`", "HARD HALT with **exit code 3 (resolution-failure)**",
                   "<https://docs.astral.sh/uv/getting-started/installation/>",
                   "No envelope is printed: the emitter needs `uv` too."):
        assert needle in step1, needle
    assert step1.index("command -v uv") < step1.index("emit-halt") < step1.index("mktemp -d")
    [site] = [s for s in _halt_sites() if s[0] == "SKILL.md" and _runtime_halt(s[3])]
    assert site[1:3] == (3, "resolution-failure")
    assert EMIT_HALT not in site[3][:site[3].index("Then resolve `{emitEnvelopeHelper}`")]
    assert ("except SKILL.md On Activation's halt for a missing `python3` or `uv`, which the emitter needs"
            in _read(HALT_CONTRACT))
    [exit_row] = [line for line in _read(INVOCATION_CONTRACT).splitlines() if line.startswith("| **Exit codes** |")]
    assert "except SKILL.md On Activation step 1's check for `python3` and `uv`, which prints none" in exit_row


def test_no_stage_halts_without_an_exit_code():
    """#593: a halt the scan cannot see (no exit code, no emit command) leaves an automator with no result."""
    for path in HALT_FILES:
        uncoded = re.findall(r"[^\n]*\bHALT with(?! \*\*exit code \d+ \([a-z-]+\)\*\*)[^\n]*", _read(path))
        assert uncoded == [], (path.name, uncoded)
    gate = _section(_read(RESOLVE_TARGET), "**GATE [default: use args]**", "### 1b.")
    assert "HARD HALT with **exit code 2 (input-invalid)**" in gate
    assert '"reason": "Headless mode requires a target argument."' in gate


@pytest.mark.parametrize("site", range(40), ids=lambda i: f"halt-{i}")
def test_every_hard_halt_emits_through_the_emitter(site):
    """#593: each HARD HALT runs the emitter, and its payload builds the envelope it names, except the runtime
    halt, which no emitter can serve (test_a_missing_runtime_halts_before_the_run_folder). #1173: a site that
    names no command of its own stages `{run_dir}/halt.json` for the standard command its file's Rules state."""
    sites = _halt_sites()
    assert len(sites) == 40
    name, code, reason, segment = sites[site]
    if _runtime_halt(segment):
        assert name == "SKILL.md"
        return
    if EMIT_HALT in segment:
        assert "--target stderr" in segment, (name, reason)
    else:
        assert f"`{EMIT_COMMAND}`" in _rules(name), (name, reason)
        assert re.search(r"[Ss]tage `\{.*?\}` as `\{run_dir\}/halt\.json`", segment), (name, reason)
        if name == "SKILL.md":
            # SKILL.md's Workflow Rules hold the command only in the cancel-line bullet, with no rule that a
            # staged halt runs it, so a SKILL.md site names that bullet's command itself.
            assert "emit it with the cancel-line rule's command (Workflow Rules)" in segment, reason
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
    # #1174: without the renderer compile would render metadata.json in the prompt, as it did before.
    pytest.param("compile.md", "{quickMetadataRenderer}", "skf-render-quick-metadata.py",
                 "quick-metadata-renderer-missing", "in-prompt", id="quick-metadata-renderer"),
    pytest.param("write-and-validate.md", "{atomicWriteHelper}", "skf-atomic-write.py", "atomic-writer-missing",
                 'cp "{run_dir}/metadata.json"', id="atomic-writer"),
    pytest.param("write-and-validate.md", "{frontmatterValidator}", "skf-validate-frontmatter.py",
                 "frontmatter-validator-missing", "skip frontmatter validation", id="frontmatter-validator"),
    pytest.param("write-and-validate.md", "{outputValidator}", "skf-validate-output.py", "output-validator-missing",
                 "skip body/snippet/metadata validation", id="output-validator"),
    # #1120: without the summarizer the step would count the issues by hand, as it did before.
    pytest.param("write-and-validate.md", "{validationSummaryHelper}", "skf-summarize-validation.py",
                 "validation-summarizer-missing", "`skill_md` counts skill-check's `diagnostics[]`",
                 id="validation-summarizer"),
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


def test_the_activation_halts_name_their_codes_in_order():
    """#1173: the halt sites, not a Raised by column, say what SKILL.md On Activation step 1 raises: exit 3 for a
    missing runtime and a config the preflight cannot load, exit 4 for the run folder, exit 3 for a missing
    helper of any stage."""
    step1 = _section(_read(SKILL), STEP_1, "\n2. ")
    activation = [(code, reason, segment) for name, code, reason, segment in _halt_sites()
                  if name == "SKILL.md" and segment[:200] in step1]
    expected = [(3, "**Quick Skill needs `{the missing tool}`"), (3, "**Quick Skill cannot load its config.**"),
                (4, "**Quick Skill cannot start: the run folder could not be created.**"),
                (3, "**Quick Skill cannot start: SKF helpers are missing.**")]
    assert [code for code, _, _ in activation] == [code for code, _ in expected]
    for (_, reason, segment), (code, message) in zip(activation, expected):
        assert reason == ("write-failure" if code == 4 else "resolution-failure")
        assert segment.index(message) < 120, message


def test_the_output_validator_runs_through_uv():
    text = _read(QS / "references" / "write-and-validate.md")
    assert 'uv run {outputValidator} "{skill_package}" --generated-by quick-skill --skip-frontmatter' in text
    assert "python3 {outputValidator}" not in text
    # The description guard keeps its own rule: without the guard, skill-check runs without --fix.
    assert "never run `--fix` unguarded" in text and "description guard unavailable" in text


def test_the_emitter_is_resolved_and_the_run_folder_made_before_the_first_halt():
    text = _read(SKILL)
    step1 = _section(text, STEP_1, "\n2. ")
    for needle in ("`{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py`",
                   "`{project-root}/src/shared/scripts/skf-emit-result-envelope.py`",
                   'mktemp -d "{project-root}/_bmad-output/.skf-run/skf-quick-skill-XXXXXXXX"',
                   "Bind `{run_dir}` ← the path it prints"):
        assert needle in step1, needle
    assert text.index("Bind `{run_dir}`") < text.index("5. **If `--batch` is set**")


# --------------------------------------------------------------------------
# #1117: activation loads the config through skf-preflight.py and resolves
# every stage's helpers once, into {run_dir}/helpers.json, before any stage loads
# --------------------------------------------------------------------------

PREFLIGHT = SCRIPTS / "skf-preflight.py"
CONFIG_CALL = 'uv run {preflightHelper} "{project-root}" --allow-missing-sidecar\n'
HELPERS_CALL = ('uv run {preflightHelper} "{project-root}" --allow-missing-sidecar --helpers "{skill-root}" '
                '> "{run_dir}/helpers.json"\n')
HELPERS_RULE = ("- Bind each `{<stem>}` or `{<stem>Helper}` this step runs ← `helpers.<stem>` in the `helpers.json` "
                "SKILL.md On Activation step 1 wrote: in `{run_dir}`, or under `--batch` in the batch folder that holds "
                "it, the parent folder of `{run_dir}`. Take the first existing path in the `<stem>ProbeOrder` array "
                "above only when that file holds no `<stem>`. Each step below that resolves a helper from its probe "
                "order binds it by this rule; its halt or fallback for a helper with no path still applies, and fires "
                "only when neither the file nor the probe order names a path that exists, as when the helper was "
                "removed after activation.")


def _probe_stems() -> dict[str, set[str]]:
    """Each stage file's `<stem>ProbeOrder` stems."""
    return {md.name: set(re.findall(r"^([A-Za-z]+)ProbeOrder:", _read(md), re.M))
            for md in sorted((QS / "references").glob("*.md"))}


def _run_call(block: str, project: Path, run_dir: Path, config: Path) -> subprocess.CompletedProcess:
    """A documented preflight call, run by bash with this repository's script and a config path."""
    command = (block.strip().replace("uv run {preflightHelper}", f'"{sys.executable}" "{PREFLIGHT.as_posix()}"')
               .replace("{project-root}", project.as_posix()).replace("{skill-root}", QS.as_posix())
               .replace("{run_dir}", run_dir.as_posix()))
    command = command.replace(" --allow-missing-sidecar", f' --allow-missing-sidecar --config-path "{config.as_posix()}"')
    return subprocess.run(["bash", "-c", command], capture_output=True, text=True, timeout=60)


def test_activation_runs_both_pre_passes_before_a_stage_loads():
    """The config pre-pass comes before the run folder, the helpers pre-pass after it, and both
    before batch-mode.md or resolve-target.md loads; no config file is read by hand."""
    text = _read(SKILL)
    step1 = _section(text, STEP_1, "\n2. ")
    assert _nested_bash_block(step1, "--allow-missing-sidecar\n") == CONFIG_CALL
    assert _nested_bash_block(step1, "--helpers") == HELPERS_CALL
    assert ("`{preflightHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-preflight.py`, else "
            "`{project-root}/src/shared/scripts/skf-preflight.py` (the first that exists)") in step1
    config, helpers = text.index(CONFIG_CALL), text.index(HELPERS_CALL)
    assert text.index("command -v uv") < config < text.index("mktemp -d") < text.index("Bind `{run_dir}`") < helpers
    assert helpers < text.index("5. **If `--batch` is set**") < text.index("6. Load, read the full file, and then "
                                                                           "execute `references/resolve-target.md`")
    assert "Read `{project-root}/_bmad/skf/config.yaml`" not in text
    assert ("bind `project_name`, `user_name`, `communication_language` and `document_output_language` from its "
            "`config`, and `output_folder`, `skills_output_folder`, `forge_data_folder` and `sidecar_path` from "
            "`config.<name>_resolved`") in step1


@pytest.mark.skipif(sys.platform == "win32", reason="runs the step's commands through a POSIX shell")
def test_the_config_pre_pass_gives_every_value_step_1_and_2_bind(tmp_path):
    step1 = _section(_read(SKILL), STEP_1, "\n2. ")
    config = tmp_path / "config.yaml"
    config.write_text("project_name: demo\nuser_name: Ada\nskills_output_folder: skills\nforge_data_folder: fd\n"
                      "output_folder: out\nsidecar_path: sc\n", encoding="utf-8")
    (tmp_path / "sc").mkdir()
    (tmp_path / "sc" / "preferences.yaml").write_text("headless_mode: true\n", encoding="utf-8")
    done = _run_call(_nested_bash_block(step1, "--allow-missing-sidecar\n"), tmp_path, tmp_path, config)
    assert done.returncode == 0, done.stdout + done.stderr
    out = json.loads(done.stdout)
    for name in ("project_name", "user_name", "communication_language", "document_output_language"):
        assert f"`{name}`" in step1 and name in out["config"], name
    for name in ("output_folder", "skills_output_folder", "forge_data_folder", "sidecar_path"):
        assert Path(out["config"][f"{name}_resolved"]).is_absolute(), name
    assert out["config"]["skills_output_folder_resolved"] == str(tmp_path.resolve() / "skills")
    assert out["derived"]["headless_mode"] is True
    step2 = _section(_read(SKILL), "2. **Resolve `{headless_mode}`**", "\n\n3. ")
    assert "`derived.headless_mode`" in step2 and "`--headless` or `-H`" in step2


@pytest.mark.skipif(sys.platform == "win32", reason="runs the step's commands through a POSIX shell")
def test_a_preferences_file_that_does_not_load_is_named_and_the_run_goes_on(tmp_path):
    """#1117 review 1: a preferences.yaml that is there but does not parse gives `status` `ok` with
    `sidecar.preferences_error`; step 1 names it in one line, as Setup item 4 and Ferris do, and
    goes on with the defaults, so `derived.headless_mode` is false."""
    step1 = _section(_read(SKILL), STEP_1, "\n2. ")
    assert ("With `sidecar.preferences_error` (a `preferences.yaml` that is there but does not load), go on with "
            "the defaults and display that error in one line; `derived.headless_mode` is then false, so only "
            "`--headless` or `-H` makes the run headless.") in step1
    # The sentence sits with the config bindings, before the config halt and the run folder.
    assert (step1.index("from `config.<name>_resolved`") < step1.index("`sidecar.preferences_error`")
            < step1.index("**Quick Skill cannot load its config.**") < step1.index("mktemp -d"))
    config = tmp_path / "config.yaml"
    config.write_text("project_name: demo\nsidecar_path: sc\n", encoding="utf-8")
    (tmp_path / "sc").mkdir()
    (tmp_path / "sc" / "preferences.yaml").write_text("headless_mode: [true\n", encoding="utf-8")
    done = _run_call(_nested_bash_block(step1, "--allow-missing-sidecar\n"), tmp_path, tmp_path, config)
    assert done.returncode == 0, done.stdout + done.stderr
    out = json.loads(done.stdout)
    assert out["status"] == "ok"
    assert out["sidecar"]["preferences_error"] and "preferences.yaml" in out["sidecar"]["preferences_error"]
    assert out["derived"]["headless_mode"] is False


def test_a_missing_batch_helper_stops_at_activation_with_exit_3():
    """#1117 review 1: `skf-quick-batch.py` is in the activation's helpers map, so a run that starts
    without it stops at SKILL.md On Activation step 1 with exit 3; batch mode's exit 2 stays only for
    a batch helper gone after activation."""
    start = _section(_read(BATCH_MODE), "### 1. Start the Batch", "### 2. ")
    [refused] = [line for line in start.splitlines() if line.startswith("- **`input-invalid`**")]
    assert ("or no path in `{quickBatchProbeOrder}` exists (an incomplete install): HARD HALT with **exit code 2 "
            "(input-invalid)**") in refused
    batch = _paragraph(_read(DOCS), "**Batch mode (`--batch <file>`).**")
    assert ("or `3` when it stops as it starts, on a missing `uv` or `python3`, a config it cannot load or a missing "
            "helper, `skf-quick-batch.py` included") in batch
    assert "quickBatch" in _probe_stems()["batch-mode.md"]


@pytest.mark.skipif(sys.platform == "win32", reason="runs the step's commands through a POSIX shell")
def test_the_helpers_pre_pass_maps_every_stage_helper(tmp_path):
    """Run as written against this repository, the pre-pass writes one key for every stem the stages
    declare, plus the customization resolver step 3 runs, each an existing file."""
    config = tmp_path / "config.yaml"
    config.write_text(f"sidecar_path: {(tmp_path / 'sc').as_posix()}\n", encoding="utf-8")
    done = _run_call(HELPERS_CALL, REPO, tmp_path, config)
    assert done.returncode == 0, done.stderr
    helpers = json.loads(_read(tmp_path / "helpers.json"))["helpers"]
    stems = set().union(*_probe_stems().values())
    # No fixed count: a stage that gains a probe order (#1120) needs no edit here.
    assert stems and "resolveCustomization" not in stems
    assert sorted(helpers) == sorted(stems | {"resolveCustomization"})
    for stem, path in helpers.items():
        assert path and Path(path).is_file(), stem


@pytest.mark.skipif(sys.platform == "win32", reason="runs the step's commands through a POSIX shell")
def test_a_missing_helper_halts_at_activation_with_exit_3(tmp_path):
    """The pre-pass exits 1 naming each missing helper, and the halt it stages builds an exit-3
    envelope whose details name them, before any stage loads."""
    [site] = [segment for file, code, reason, segment in _halt_sites()
              if file == "SKILL.md" and '"cause": "helpers-missing"' in segment]
    assert site.startswith("HARD HALT with **exit code 3 (resolution-failure)**")
    assert '`"details": {"cause": "preflight-error"}` when the file holds no JSON' in site
    assert "{the `error` in `{run_dir}/helpers.json`, which names each missing helper" in site
    # #1173: the cancel-line rule states the command once; this halt names it instead of restating it.
    assert "and emit it with the cancel-line rule's command (Workflow Rules)." in site and EMIT_HALT not in site
    [cancel] = [line for line in _rules("SKILL.md").splitlines() if line.startswith("- **Universal cancel-line")]
    assert f"`{EMIT_COMMAND}`" in cancel
    payload = _filled(_staged(site, "halt.json"))
    assert payload == {"phase": "on-activation", "halt_reason": "resolution-failure",
                       "reason": "Quick Skill cannot start: SKF helpers are missing.", "skill_package": None,
                       "details": {"cause": "helpers-missing", "missing": []}}
    # A project with no SKF scripts: every helper is missing.
    config = tmp_path / "config.yaml"
    config.write_text(f"sidecar_path: {(tmp_path / 'sc').as_posix()}\n", encoding="utf-8")
    done = _run_call(HELPERS_CALL, tmp_path, tmp_path, config)
    assert done.returncode == 1
    out = json.loads(_read(tmp_path / "helpers.json"))
    assert out["code"] == "HELPERS_MISSING" and "skf-resolve-package.py" in out["helpers_missing"]
    payload["details"]["missing"] = out["helpers_missing"]
    schema = _schema()
    envelope = _emitter().build_envelope(schema, payload, halt=True, decisions=[], warnings=[], stamps={
        "timestamp": "2026-11-12T00:00:00Z", "run_id": "ab12cd34", "result_path": None})
    assert _emitter().contract_errors(schema, envelope) == []
    assert (envelope["status"], envelope["exit_code"]) == ("error", 3)
    assert envelope["error"]["details"]["missing"] == out["helpers_missing"]


def test_a_config_the_preflight_cannot_load_halts_before_the_run_folder():
    [site] = [segment for file, code, reason, segment in _halt_sites()
              if file == "SKILL.md" and "**Quick Skill cannot load its config.**" in segment]
    assert site.startswith("HARD HALT with **exit code 3 (resolution-failure)**")
    assert "{its `error`, else its first stderr line, else: SKF's preflight (`skf-preflight.py`) is missing" in site
    assert "--run-dir" not in site[:site.index("Then create the run folder")]
    payload = _filled(_staged(site, "halt.json"))
    assert payload["details"]["cause"].startswith("<its code, preflight-missing with no path, or preflight-error")
    # preflight's error names an absolute path, so only the display quotes it: the payload's reason is typed text.
    assert payload["reason"] == "Quick Skill cannot load its config."
    assert "The payload's `reason` is the message's first sentence alone" in site


def test_the_run_folder_halt_stages_a_reason_it_wrote():
    [site] = [segment for file, code, reason, segment in _halt_sites()
              if file == "SKILL.md" and "**Quick Skill cannot start: the run folder could not be created.**" in segment]
    payload = _filled(_staged(site, "halt.json"))
    assert (payload["halt_reason"], payload["reason"]) == (
        "write-failure", "Quick Skill cannot start: the run folder could not be created.")
    assert "that stderr line again in the display alone" in site


def test_every_stage_binds_its_helpers_from_helpers_json():
    """Each stage that declares a probe order reads the activation's map first; its own halts stay."""
    declaring = {name for name, stems in _probe_stems().items() if stems}
    assert declaring == {"resolve-target.md", "quick-extract.md", "compile.md", "write-and-validate.md",
                         "finalize.md", "batch-mode.md"}
    for name in sorted(declaring - {"batch-mode.md"}):
        rules = _section(_read(QS / "references" / name), "## Rules\n", "## Steps")
        assert rules.count(HELPERS_RULE) == 1, name
    execution = _section(_read(BATCH_MODE), "## Execution", "### 1. Start the Batch")
    assert ("Bind `{quickBatchHelper}` ← `helpers.quickBatch` in `{batch_dir}/helpers.json`, which SKILL.md On "
            "Activation step 1 wrote; take the first existing path in `{quickBatchProbeOrder}` only when that file "
            "holds no `quickBatch`.") in execution
    assert "Resolve `{quickBatchHelper}` from `{quickBatchProbeOrder}`" not in execution


def test_the_halt_contract_defines_the_payload_and_the_batch_rule():
    text = _read(HALT_CONTRACT)
    block = _bash_block(text, "emit-halt")
    assert block.startswith("cat > \"{run_dir}/halt.json\" <<'SKF_JSON'\n")
    assert block.endswith('uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" '
                          '--target stderr < "{run_dir}/halt.json"\n')
    assert "`shared/scripts/schemas/skf-quick-skill-result-envelope.v1.json`" in text
    # A halt whose emitter fails twice, or has no path, still shows its message (#1173's matrix: a Rules-command site).
    assert ("If it exits non-zero, fix `halt.json` once (its `message` names the problem) and run it again; if it "
            "still fails, or no path resolved for `{emitEnvelopeHelper}`, display the halt message alone.") in text
    batch = text[text.index("## In `--batch`"):]
    for needle in ("ends the current target, not the batch", "return to `references/batch-mode.md` §3",
                   "control returns there even when the halt message reads as the end of the run",
                   "never exits the process", "under `--fail-fast`"):
        assert needle in batch, needle
    # A halt after a compaction resolves the emitter again from here, in SKILL.md's order.
    contract = _section(text, "## Result Contract on HARD HALT", "```bash")
    paths = re.findall(r"`(\{project-root\}/[^`]+/skf-emit-result-envelope\.py)`", contract)
    assert paths == re.findall(r"`(\{project-root\}/[^`]+/skf-emit-result-envelope\.py)`",
                               _section(_read(SKILL), STEP_1, "\n2. "))
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


# Gates the schema keeps for a step that raises none yet (#1173).
RESERVED_GATES = {"ecosystem-check.ecosystem-match"}


def test_every_headless_gate_records_its_decision():
    """SKILL.md's rule: a gate that resolves on its own records the decision the moment it decides. #1173: the
    gate stages `{run_dir}/decision.json` and its file's Rules run the standard record command on it."""
    schema = _schema()
    item = schema["properties"]["headless_decisions"]["items"]
    emitter = _emitter()
    recorded = []
    for path in HALT_FILES:
        text = _read(path)
        for m in GATE_RE.finditer(text):
            line = text[m.start():text.index("\n", m.start())]
            decision = _filled(_staged(line, "decision.json"))
            assert "record --workflow" not in line, (path.name, "the Rules state the command once")
            assert f"`{RECORD_COMMAND}`" in _rules(path.name), path.name
            assert decision["default_action"] == decision["taken_action"] == m.group(1), path.name
            assert emitter._validate_against_schema(decision, item) == [], decision
            recorded.append((decision["gate"], m.group(1)))
    # The overwrite gate has two defaults: Y over a quick skill, N over another generator's build.
    gates = set(item["properties"]["gate"]["enum"])
    assert RESERVED_GATES < gates and "reserved" in item["properties"]["gate"]["description"]
    assert sorted({gate for gate, _ in recorded}) == sorted(gates - RESERVED_GATES)
    assert sorted(default for gate, default in recorded if gate == "write-and-validate.overwrite") == ["N", "Y"]
    assert len(recorded) == len(gates - RESERVED_GATES) + 1
    rules = _section(_read(SKILL), "## Workflow Rules", "## Stages")
    assert 'record --workflow skf-quick-skill --run-dir "{run_dir}" --decision' in rules
    assert "log each auto-decision" not in rules


VALIDATION_ISSUES = '`{"skill_md": <n>, "context_snippet": <n>, "metadata": <n>, "security": <n>}`'


SUMMARIZER = SCRIPTS / "skf-summarize-validation.py"
SUMMARY_PROBE = ["{project-root}/_bmad/skf/shared/scripts/skf-summarize-validation.py",
                 "{project-root}/src/shared/scripts/skf-summarize-validation.py"]
SUMMARY_CALL = ('uv run {validationSummaryHelper} --skill-check "{run_dir}/skill-check.json" '
                '--frontmatter "{run_dir}/frontmatter.json" --output "{run_dir}/output.json" '
                '--security "{run_dir}/security.json" --skill-dir "{skill_package}" '
                '> "{run_dir}/validation-summary.json"\n')


def test_step_5_counts_the_validation_issues_in_the_schema_shape():
    """#586, #1120: {validation_issues} is the object the schema requires, and {quality_score} skill-check's score,
    both taken from the summarizer §6 runs over the four outputs the validators saved, every flag passed; the step
    keeps no rule for the score or the counts, and finalize copies both values from that file."""
    text = _read(WRITE_AND_VALIDATE)
    frontmatter = text.split("---\n", 2)[1]
    assert "validationSummaryProbeOrder:\n" + "".join(f"  - '{path}'\n" for path in SUMMARY_PROBE) in frontmatter
    report = _section(text, "### 6. Report Validation Results", "### 7. ")
    assert _bash_block(report, "{validationSummaryHelper}") == SUMMARY_CALL
    assert report.index("Resolve `{validationSummaryHelper}` ← first existing path in `{validationSummaryProbeOrder}`") \
        < report.index("HARD HALT") < report.index(SUMMARY_CALL)
    assert "Pass every flag on every path: a file no check wrote counts nothing." in report
    assert ("Bind `{quality_score}` ← `quality_score` (skill-check's score for this skill, null when skill-check did "
            "not validate it or reported no score) and `{validation_issues}` ← `validation_issues` from "
            "`{run_dir}/validation-summary.json`.") in report
    assert ("list the entries of that file's `issues.skill_md`, `issues.context_snippet`, `issues.metadata` and "
            "`issues.security`") in report
    # Each validator saves its stdout where the summarizer reads it.
    four = _section(text, "### 4. Validate SKILL.md via skill-check", "### 5. ")
    five = _section(text, "### 5. Validate Body, Snippet, and Metadata", "### 6. ")
    assert _bash_block(four, "{frontmatterValidator}") == (
        'uv run {frontmatterValidator} "{skill_package}/SKILL.md" --skill-dir-name {repo_name} '
        '> "{run_dir}/frontmatter.json"\n')
    assert _bash_block(five, "{outputValidator}") == (
        'uv run {outputValidator} "{skill_package}" --generated-by quick-skill --skip-frontmatter '
        '> "{run_dir}/output.json"\n')
    # No score rule and no counting rule is left in the step.
    for stale in ("relativePath", "skillId", "scores[].score", "counts skill-check's", "counts `validation.",
                  "A check that did not run counts 0", "**Parse the JSON in", "Record each issue as a validation issue",
                  "Set `validation_result`"):
        assert stale not in text, stale
    finalize = _section(_read(FINALIZE), "### 3. Result Envelope and Result Contract", "### 4. ")
    assert ("`quality_score` and `validation_issues` (the two values of `{run_dir}/validation-summary.json`, step 5 "
            f"§6, copied as they are there: a number or null, and the object {VALIDATION_ISSUES})") in finalize
    shape = json.loads(VALIDATION_ISSUES.strip("`").replace("<n>", "0"))
    issues = _schema()["properties"]["summary"]["properties"]["validation_issues"]
    assert list(shape) == issues["required"] and set(shape) == set(issues["properties"])
    # Step 6 §3's summary also carries the outcome §4 binds, so the closing sentence names it with the other two.
    assert ("Step 6 §3's summary carries `{quality_score}`, `{validation_issues}` and `{security_result}`."
            in report)
    assert '"security_result": "{security_result}"' in finalize


def _success_payload(section: str, quality_score: str = "91", issues: str | None = None) -> str:
    """finalize §3's staged payload, each bare JSON value filled in as a run fills it."""
    # {validation_issues} takes the shape step 5 defines, its counts filled in.
    issues = issues or VALIDATION_ISSUES.strip("`").replace("<n>", "1", 1).replace("<n>", "0")
    sample = {"{exports_documented}": "12", "{quality_score}": quality_score, "{repo_shape}": "null",
              '"{extraction confidence}"': '"high"', '"{active_pointer}"': '"symlink"',
              "{language_resolution}": '"detected"', "{detected_languages}": '["python"]',
              "{zero_exports_rescue}": "null", "{validation_issues}": issues,
              # #902: the outcome step 5 binds when no SNYK_TOKEN lets the scan run
              '"{security_result}"': '"skipped"'}
    payload = _staged(section, "result-context.json")
    for placeholder, value in sample.items():
        assert placeholder in payload, placeholder
        payload = payload.replace(placeholder, value)
    return payload


@pytest.mark.skipif(sys.platform == "win32", reason="runs the step's command through a POSIX shell")
@pytest.mark.parametrize("build", ["scores", "qualityScore", "stopped"])
def test_the_summary_call_fills_the_success_payload(tmp_path: Path, build: str):
    """#1120: §6's call, run by bash as written over saved validator outputs, writes the two values finalize §3
    copies, and the envelope they build carries them. An older skill-check build that prints only a top-level
    `qualityScore` reaches `summary.quality_score`; a skill-check that stopped leaves it null and the frontmatter
    validator's issues count, as the frontmatter path does."""
    report = _section(_read(WRITE_AND_VALIDATE), "### 6. Report Validation Results", "### 7. ")
    package = tmp_path / "skills" / "demo" / "1.0.0" / "demo"
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text("---\nname: demo\ndescription: Demo. Use when testing.\n---\n# Demo\n",
                                      encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    diagnostic = {"ruleId": "body.max_lines", "severity": "warn", "message": "long", "file": "x", "line": 3}
    checked = {"summary": {"skillCount": 1, "errorCount": 0, "warningCount": 1}, "diagnostics": [diagnostic]}
    if build == "scores":
        checked["scores"] = [{"skillId": "x/y", "relativePath": "skills/demo/1.0.0/demo/SKILL.md", "score": 86}]
    elif build == "qualityScore":
        checked["qualityScore"] = 72
    text = "Error: unknown option '--fix'\n" if build == "stopped" else json.dumps(checked) + "\nWrote r.json\n"
    (run_dir / "skill-check.json").write_text(text, encoding="utf-8")
    if build == "stopped":
        (run_dir / "frontmatter.json").write_text(json.dumps({"status": "fail", "issues": [
            {"severity": "high", "field": "name", "message": "a"}, {"severity": "low", "field": "x", "message": "b"}]}),
            encoding="utf-8")
    (run_dir / "output.json").write_text(json.dumps({"validation": {
        "skill_md": {"frontmatter": {"skipped": "--skip-frontmatter"}, "body": []},
        "context_snippet": {"issues": [{"severity": "low", "field": "length", "message": "short"}]},
        "metadata": {"issues": []}}}), encoding="utf-8")
    # No security.json: a scan that wrote nothing counts nothing.
    command = (_bash_block(report, "{validationSummaryHelper}").strip()
               .replace("uv run {validationSummaryHelper}", f'"{sys.executable}" "{SUMMARIZER.as_posix()}"')
               .replace("{run_dir}", run_dir.as_posix()).replace("{skill_package}", package.as_posix()))
    done = subprocess.run(["bash", "-c", command], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    summary = json.loads(_read(run_dir / "validation-summary.json"))
    expected = {"scores": (86, 1), "qualityScore": (72, 1), "stopped": (None, 2)}[build]
    assert (summary["quality_score"], summary["validation_issues"]["skill_md"]) == expected
    assert summary["validation_issues"] | {"skill_md": 0} == {"skill_md": 0, "context_snippet": 1, "metadata": 0,
                                                               "security": 0}
    section = _section(_read(FINALIZE), "### 3. Result Envelope and Result Contract", "### 4. ")
    context = json.loads(_success_payload(section, json.dumps(summary["quality_score"]),
                                          json.dumps(summary["validation_issues"])))
    schema = _schema()
    emitter = _emitter()
    envelope = emitter.build_envelope(schema, context, halt=False, decisions=[], warnings=[], stamps={
        "timestamp": "2026-11-13T00:00:00Z", "run_id": "ab12cd34", "result_path": None})
    assert emitter.contract_errors(schema, envelope) == []
    assert envelope["summary"]["quality_score"] == expected[0]
    assert envelope["summary"]["validation_issues"] == summary["validation_issues"]


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
    # #902: the scan's outcome is one of the schema's three values, never a near miss or null
    assert envelope["summary"]["security_result"] == "skipped"
    for value in ("pass", "warn", "passed", "SKIP", None):
        wrong = {**context, "summary": {**context["summary"], "security_result": value}}
        built = emitter.build_envelope(schema, wrong, halt=False, decisions=[], warnings=[], stamps={
            "timestamp": "2026-10-01T00:00:00Z", "run_id": "ab12cd34", "result_path": None})
        assert bool(emitter.contract_errors(schema, built)) == (value not in ("pass", "warn")), value
    # quick-extract records the skills-module shape, which the summary must admit.
    context["summary"]["repo_shape"] = "skills-module"
    shaped = emitter.build_envelope(schema, context, halt=False, decisions=[], warnings=[], stamps={
        "timestamp": "2026-10-01T00:00:00Z", "run_id": "ab12cd34", "result_path": None})
    assert emitter.contract_errors(schema, shaped) == []
    for field in ("quality_score", "confidence", "repo_shape", "language_resolution", "zero_exports_rescue",
                  "security_result"):
        assert section.count(f"`{field}`") == 1, f"the summary list names {field} once"
    assert "`security_result` (step 5 §4: `pass`, `warn` or `skipped`)" in section


def test_a_scan_that_could_not_run_reaches_the_printed_line(tmp_path):
    """#902: finalize §3's payload, filled with the `skipped` step 5 binds without SNYK_TOKEN, makes `emit` print a
    line whose summary carries it, as the result file does; a value outside the schema's three stops `emit`."""
    section = _section(_read(FINALIZE), "### 3. Result Envelope and Result Contract", "### 4. ")
    package = tmp_path / "skills" / "demo" / "1.0.0" / "demo"
    package.mkdir(parents=True)
    payload = _success_payload(section).replace("{skill_package}", package.as_posix())

    def emit(text: str, run: str) -> subprocess.CompletedProcess:
        run_dir = tmp_path / f"skf-quick-skill-{run}"
        run_dir.mkdir()
        return subprocess.run([sys.executable, str(EMITTER), "emit", "--workflow", "skf-quick-skill", "--run-dir",
                               str(run_dir), "--result-dir", str(package)], input=text.encode("utf-8"),
                              capture_output=True, timeout=60)

    proc = emit(payload, "ab12cd34")
    assert proc.returncode == 0, proc.stderr
    [line] = [line for line in proc.stdout.decode("utf-8").splitlines()
              if line.startswith("SKF_QUICK_SKILL_RESULT_JSON: ")]
    assert '"security_result":"skipped"' in line
    assert json.loads(line.split(": ", 1)[1])["summary"]["security_result"] == "skipped"
    record = json.loads((package / "quick-skill-result-latest.json").read_bytes().decode("utf-8"))
    assert record["summary"]["security_result"] == "skipped"
    refused = emit(payload.replace('"security_result": "skipped"', '"security_result": "passed"'), "ef56gh78")
    assert refused.returncode == 1 and "security_result" in refused.stderr.decode("utf-8")


def test_every_target_of_a_batch_returns_to_batch_mode():
    """#585: a target's end, success or halt, never ends the batch; the health check runs once."""
    batch = _read(BATCH_MODE)
    record = _section(batch, "### 3. Record the Target", "### 4. ")
    for needle in ("step 6 §4 returns here", "every HARD HALT of steps 1 to 6 returns here",
                   "Control returns here even when the step that ended the target reads as the end of the run",
                   "uv run {quickBatchHelper} record --run-dir \"{batch_dir}\" --batch {batch}"):
        assert needle in record, needle
    summary = batch[batch.index("### 4. Batch Summary"):]
    assert "execute `{healthCheckStepFile}`: the health check runs once per batch, here" in summary
    # #1113: a batch target binds no result line, so a line an earlier workflow of the session bound is cleared first.
    empty = "Then bind `{result_envelope_line}` empty, so the health check shows no line an earlier workflow"
    assert summary.index(empty) < summary.index("load, read in full and execute `{healthCheckStepFile}`")
    frontmatter = batch.split("---\n", 2)[1]
    assert "healthCheckStepFile: 'health-check.md'" in frontmatter
    assert ("quickBatchProbeOrder:\n  - '{project-root}/_bmad/skf/shared/scripts/skf-quick-batch.py'\n"
            "  - '{project-root}/src/shared/scripts/skf-quick-batch.py'\n") in frontmatter
    finalize = _read(FINALIZE)
    chain = finalize[finalize.index("### 4. Chain to Health Check"):]
    assert "return to `references/batch-mode.md` §3 instead of {nextStepFile}" in chain
    assert "control returns there even though this step reads as the end of the run" in chain
    assert "runs once per batch" in _read(HEALTH_CHECK)
    execution = batch[batch.index("## Execution"):]
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
        section = _section(batch, step, "\n### ") if step.startswith("### 3") else batch[batch.index(step):]
        block = _bash_block(section, command)
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


def test_a_bad_batch_line_is_refused_at_start(tmp_path, capsys):
    """#1175 enhancement-4: a line with a word that is no modifier refuses the batch at §1, with exit 2 and before
    any target runs, instead of taking the line whole as a target that fails when the batch reaches it."""
    batch = _read(BATCH_MODE)
    grammar = _section(batch, "## Input format", "## Execution")
    for needle in ("A word that starts with `#` after the target opens a comment that runs to the end of the line.",
                   "Any other word after the target refuses the whole batch at §1: no target runs, and the helper's "
                   "message names each such line, the first five with their fault, and gives the fix."):
        assert needle in grammar, needle
    assert "taken whole as the target" not in grammar
    start = _section(batch, "### 1. Start the Batch", "### 2. ")
    [branch] = [line for line in start.splitlines() if line.startswith("- **`input-invalid`**")]
    assert "(a batch file it cannot read, a line with a word that is no modifier, or a run folder that holds " \
           "another batch)" in branch
    assert "HARD HALT with **exit code 2 (input-invalid)**" in branch
    assert _filled(_staged(branch, "halt.json"))["phase"] == "batch-mode"
    helper = _load(SCRIPTS / "skf-quick-batch.py", "skf_quick_batch_for_quick_contract")
    file = tmp_path / "targets.txt"
    file.write_text("lodash scope=src/ # the core\nzod lang=javascript\n", encoding="utf-8")
    assert helper.main(["start", str(file), "--run-dir", str(tmp_path / "run")]) == 1
    refusal = json.loads(capsys.readouterr().err)
    assert _schema()["$defs"]["skf-envelope"]["const"]["exit_codes"][refusal["halt_reason"]] == 2
    assert "line 2: `lang=javascript` after the target `zod`" in refusal["message"]
    assert not (tmp_path / "run").exists()
    paragraph = _paragraph(_read(DOCS), "**Batch mode (`--batch <file>`).**")
    for needle in ("`#` comments (a whole line, or the rest of a line after its target)",
                   "A batch refused before its first target, such as one whose file has a word that is no modifier "
                   "after a line's target, writes no summary and exits `2`"):
        assert needle in paragraph, needle


def test_a_failing_batch_helper_call_halts_the_batch():
    """#903: a failing next, a second failing record and a failing summarize each end the batch with exit 4 and a
    batch-mode halt line, as Create Skill's batch does, instead of no halt line or the same target over again."""
    batch = _read(BATCH_MODE)
    sections = {
        "next": _section(batch, "### 2. Take the Next Target", "### 3. "),
        "record": _section(batch, "### 3. Record the Target", "### 4. "),
        "summarize": batch[batch.index("### 4. Batch Summary"):],
    }
    sites = [site for site in _halt_sites() if site[0] == "batch-mode.md"]
    opener = "uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --target stderr <<'SKF_JSON'"
    for command, section in sections.items():
        [(_, code, reason, segment)] = [site for site in sites if site[3] in section]
        assert (code, reason) == (4, "write-failure"), command
        payload = _filled(_staged(segment, "halt.json"))
        assert (payload["phase"], payload["halt_reason"], payload["skill_package"]) == (
            "batch-mode", "write-failure", None), command
        assert payload["reason"] == "The batch stopped: <its message, one line>", command
        assert "details" not in payload, command
        # Nothing to stage in: the emitter reads the heredoc, with no --run-dir.
        [line] = [line for line in segment.splitlines() if "<<'SKF_JSON'" in line]
        assert line == opener, command
        [halt] = [line for line in section.splitlines() if "HARD HALT with **exit code 4 (write-failure)**" in line]
        assert 'display "**The batch stopped:** {its `message`}" and HARD HALT' in halt, command
        assert "the health check does not run" in halt, command
        assert halt.index("HARD HALT") < halt.index("the health check does not run"), command
    take = sections["next"]
    assert take.index('- **`"status": "done"`**') < take.index("HARD HALT with **exit code 4")
    assert ("If it exits non-zero (the target's run folder cannot be created, or the batch file is gone or "
            "unreadable), the batch cannot go on") in take
    record = sections["record"]
    assert "record again, then go back to §2" not in batch
    assert "stage the payload the target ended with and record again, once." in record
    assert ("If it exits non-zero a second time (the batch file cannot be written, or the staged `halt.json` is not "
            "JSON or names a `halt_reason` that maps to no exit code)") in record
    # The halt ends the batch, not the target: going back to §2 would hand the same target back for ever.
    assert ("This halt ends the batch, not only the target: do not go back to §2, which would hand the same target "
            "back") in record
    assert record.index("record again, once") < record.index("HARD HALT with **exit code 4")
    summary = sections["summarize"]
    assert ("If `summarize` exits non-zero (a target is still pending, or the batch file is gone or unreadable), it "
            "wrote no summary file") in summary
    assert summary.index("The batch ends with the event's `exit_code`.") < summary.index("HARD HALT with **exit")
    assert ("When an earlier `summarize` already printed the `batch_summary` event (a compaction came before the "
            "health check), that event stays the batch's result. Emit") in summary
    contract = _read(HALT_CONTRACT)
    assert "or `batch-mode` for batch mode §1 to §4.\n" in contract
    in_batch = contract.split("## In `--batch`", 1)[1]
    assert ("A batch mode §2 to §4 halt ends the run too and writes no batch summary, though a `batch_summary` "
            "event an earlier `summarize` already printed stays the batch's result; the targets recorded before it "
            "keep the `done` and `fail` events they printed.") in in_batch
    assert ("batch-mode for a batch that cannot start or go on (batch mode sections 1 to 4)"
            in _schema()["properties"]["phase"]["description"])
    docs = _paragraph(_read(DOCS), "**Batch mode (`--batch <file>`).**")
    assert ("A batch whose helper cannot hand out or record a target, or cannot summarize the batch, stops with exit "
            "`4` and a `batch-mode` halt line and skips the health check; a `batch_summary` event it already printed "
            "stays its result.") in docs


def test_every_way_out_of_a_step_prints_its_events():
    """Headless events: step 2's pass-through chains with its done and start events (#1173: it has no gate),
    and the health check's one paragraph leaves room for its own done event (#1114)."""
    eco = _read(QS / "references" / "ecosystem-check.md")
    [proceed] = [line for line in eco.splitlines() if line.startswith("- IF P:")]
    assert "print this step's `done` event and step 3's `start` event" in proceed
    assert eco.rstrip("\n").endswith(proceed) and "GATE" not in eco
    relay = _read(HEALTH_CHECK)
    assert ("When `{headless_mode}` is true, print this step's `done` event (`references/halt-contract.md`) "
            "first. Load `{nextStepFile}`, read it fully, then execute it. Apart from that event, do nothing "
            "else here") in relay
    assert "intervening action" not in relay


def test_finalize_never_writes_the_result_contract_by_hand():
    """determinism-3: with no emitter, the run says the contract was not written instead of typing it."""
    rules = _section(_read(FINALIZE), "## Rules\n", "## Steps")
    assert "Result contract writing is mandatory" not in rules
    assert ("Emit the result envelope and contract through the shared emitter, never by hand; when it is "
            "missing or fails twice, say the contract was not written and go on") in rules


def test_the_batch_exit_code_is_the_highest_failed_code():
    """#1173: the docs' batch paragraph states the exit rule batch-mode.md's Exit code section held."""
    exit_code = _paragraph(_read(DOCS), "**Batch mode (`--batch <file>`).**")
    assert ("Without `--fail-fast` the batch runs every target, whatever an earlier target's outcome, and exits with "
            "the highest exit code among its failed targets (`0` when none failed)") in exit_code
    assert "the exit code of the first failed target" not in exit_code
    assert "`--fail-fast` stops it at the first failed target and exits with that target's code" in exit_code
    assert "## Exit code" not in _read(BATCH_MODE)


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
    """The step 5 validator and the snippet anchors read the template's headings; the renderer ignores it.
    #1174: no step reads the template's metadata.json section, since a missing renderer halts."""
    comment = _comment_before("skill_template_path")
    template = _read(TEMPLATE)
    for heading in ("## SKILL.md Section Structure", "## context-snippet.md Format", "## Overview",
                    "## Description", "## Key Exports", "## Usage Patterns"):
        assert f"`{heading}`" in comment, heading
        assert f"\n{heading}" in template, heading
    for anchor in ("#key-exports", "#usage-patterns"):
        assert f"`{anchor}`" in comment and f"SKILL.md{anchor}" in template, anchor
    assert "metadata.json" not in comment and "fails twice" not in comment
    # After the JSON block, which test-skf-validate-output.py reads right below the heading.
    section = template[template.index("\n## metadata.json Format\n"):]
    assert ("\n```\n\nDocumentation only: no step reads this section. Step 4 writes `metadata.json` with "
            "`skf-render-quick-metadata.py`, which sets these fields, and stops when that renderer is missing or "
            "fails twice.") in section
    # #1108: a bare path resolves from the skill root, which every update overwrites.
    assert ("Default: assets/skill-template.md, a path from the skill root. Keep a house-style copy outside the "
            "skill folder, which every update overwrites, and name it as {project-root}/<path to the copy>."
            ) in " ".join(comment.split())
    validator = _load(SCRIPTS / "skf-validate-output.py", "skf_validate_output_for_quick_contract")
    body = validator.validate_body_structure(f"---\nname: x\n---\n{template}")
    assert body == [], "the bundled template carries every section the validator requires"


def test_the_hook_comments_match_when_skill_md_runs_them():
    prepend = _comment_before("activation_steps_prepend")
    assert "SKILL.md On Activation step 3" in prepend and "before the CLI flags are parsed" in prepend
    assert "uv probe" not in prepend
    step3 = _section(_read(SKILL), "3. **Resolve workflow customization.**", "\n4. ")
    assert "Run each `workflow.activation_steps_prepend` entry now, in order." in step3
    # #1111: every step number says whether it is an On Activation step or a stage.
    assert "Once On Activation step 4 has parsed the flags, before On Activation step 5 or 6 starts the run, " \
           "run each `workflow.activation_steps_append` entry in order." in step3
    append = _comment_before("activation_steps_append")
    assert "SKILL.md On Activation step 4 has parsed the CLI flags" in append
    assert "before stage 1 (references/resolve-target.md)" in append


def test_the_persistent_facts_default_says_how_to_drop_it():
    """#596 decision: a `!` entry in an override drops the default, which the customization helper applies (#1106)."""
    assert _customize()["persistent_facts"] == ["file:{project-root}/**/project-context.md"]
    comment = _comment_before("persistent_facts")
    for needle in ("loads every project-context.md under {project-root}",
                   "set in {project-root}/_bmad/custom/skf-quick-skill.toml:",
                   'persistent_facts = ["!file:{project-root}/**/project-context.md"]'):
        assert needle in comment, needle
    for stale in ("cannot remove it", "add a literal fact"):
        assert stale not in comment, stale
    step3 = _section(_read(SKILL), "3. **Resolve workflow customization.**", "\n4. ")
    assert "`--facts` has applied each `!` entry, which drops each earlier entry it names" in step3


def test_the_on_complete_comment_is_the_call_finalize_makes():
    """#596 decision: the hook gets --result-path like the other per-skill workflows, and only when the
    emitter wrote the result file, so it never reads a missing file or an earlier run's -latest copy."""
    comment = _comment_before("on_complete")
    assert "a shell command, not an instruction" in comment
    assert '<on_complete> --result-path="<skill package>/quick-skill-result-latest.json"' in comment
    assert "--skill-package" not in _read(CUSTOMIZE) and "--skill-package" not in _read(FINALIZE)
    for needle in ("is skipped when the emitter wrote no result file", "once per target that finishes",
                   "a HARD HALT never runs it", "never fails the workflow"):
        assert needle in comment, needle
    hook = _section(_read(FINALIZE), "**Post-completion hook (optional).**", "In a single-target run")
    assert _bash_block(hook, "{onCompleteCommand}") == (
        '{onCompleteCommand} --result-path="{skill_package}/quick-skill-result-latest.json"\n')
    assert ("and the emitter wrote the result contract (the line it printed has a non-null `result_path` and no "
            "`result_file_write_failed` warning naming `quick-skill-result-latest.json`)") in hook
    assert ("When the emitter failed twice, no path resolved for `{emitEnvelopeHelper}`, `result_path` is null, or a "
            "`result_file_write_failed` warning names `quick-skill-result-latest.json` (the copy alone failed), "
            "skip the hook and say so") in hook
    assert "Under `--batch` it runs once per target that reaches this section." in hook
    # #1109: the hook runs from the project root with a 60s timeout, and a timeout is a logged failure.
    assert ("Run it from `{project-root}` with a 60s timeout. Log success or failure, a timeout counting as a "
            "failure, but never fail the workflow on a hook error") in hook
    assert "Step 6 runs it from {project-root}, with a 60s timeout, once the success envelope is printed" in comment


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


def test_the_ecosystem_check_keeps_its_slug_and_reserves_exit_8():
    """#1173: no input reaches step 2's [P]/[I]/[A] gate until agentskills.io has a registry API, so the step
    keeps only its pass-through; its slug stays, and exit 8 and the gate stay reserved in the contract."""
    assert [site for site in _halt_sites() if site[0] == "ecosystem-check.md"] == []
    text = _read(ECOSYSTEM)
    steps = text[text.index("## Steps"):]
    for stale in ("HALT", "GATE", "[I] Install", "Once a registry API lists", "exit code"):
        assert stale not in steps, stale
    assert "GATE" not in text
    contract = _read(HALT_CONTRACT)
    codes = _section(contract, "## Exit Codes", "## Result Contract")
    [row8] = [line for line in codes.splitlines() if line.startswith("| 8 ")]
    assert row8.split("|")[2].strip() == "ecosystem-redirect"
    assert ("Exit 8 (`ecosystem-redirect`) is reserved, as is the `ecosystem-check.ecosystem-match` gate: step 2 "
            "raises neither until agentskills.io has a registry API.") in codes
    assert "2 `ecosystem-check`" in contract
    schema = _schema()
    assert schema["$defs"]["skf-envelope"]["const"]["exit_codes"]["ecosystem-redirect"] == 8
    assert "ecosystem-redirect 8 (reserved until agentskills.io has a registry API)" in \
        schema["properties"]["exit_code"]["description"]
    [gates] = [line for line in _read(INVOCATION_CONTRACT).splitlines() if line.startswith("| **Gates** |")]
    assert "step 2" not in gates and "ecosystem" not in gates
    [row2] = [line for line in _read(SKILL).splitlines() if line.startswith("| 2 | Ecosystem Check |")]
    assert row2 == "| 2 | Ecosystem Check | references/ecosystem-check.md | Yes |"


# --------------------------------------------------------------------------
# #600: one home per rule in SKILL.md and the stage files
# --------------------------------------------------------------------------


def test_compile_names_the_skill_after_its_folder():
    """W1 re-check leanness-1: the gerund preference could pull `name` off the folder step 5 writes."""
    text = _read(COMPILE)
    [rule] = [line for line in text.splitlines() if line.startswith("- `name` ")]
    assert rule == "- `name` is `{repo_name}`: step 5 writes that folder and validates the name against it."
    assert "gerund" not in text and "that's step 6" not in text
    # #1174: the drafts are staged in the run folder, which step 5 installs from.
    [focus] = [line for line in _rules("compile.md").splitlines() if line.startswith("- Focus only on")]
    assert focus == ("- Focus only on assembling the three output documents: write them only into `{run_dir}` "
                     "(step 5 installs them)")
    assert "do not write files to disk" not in text
    snippet = _section(text, "### 4. Generate Context Snippet", "### 5. ")
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
    assert "the security scan at the end of section 4 still runs" in text
    assert "brief it with `@Ferris BS` and compile it with `@Ferris CS`" in text


SCAN_CALL = 'uv run {securityScanHelper} run --package "{skill_package}" > "{run_dir}/security.json"\n'


def test_step_5_reads_the_security_scan_from_the_helper():
    """#892: skill-check 1.2.0 passes none of the scanner's findings on, so skill-check runs with
    `--no-security-scan` and `skf-security-scan.py` runs the scan, whether or not skill-check ran. Its JSON binds
    `{security_result}` and the note, each finding is a validation issue, and §6 shows and counts them."""
    text = _read(WRITE_AND_VALIDATE)
    four = _section(text, "### 4. Validate SKILL.md via skill-check", "### 5. ")
    rule = _section(four, "**Read the JSON, not the exit code.**", "\n")
    assert ("exits 1 when `summary.errorCount` is above 0, or when `--strict` or `--fail-on-warning` is passed and "
            "`summary.warningCount` is above 0 (this call passes neither), so `summary.errorCount` alone is the "
            "validation verdict.") in rule
    assert "`--no-security-scan` keeps the security scan out of this call" in rule
    # The scan closes §4, after the frontmatter validator a run without skill-check takes.
    assert four.index("**If skill-check is not available**") < four.index("**Security scan.**")
    scan = four[four.index("**Security scan.**"):]
    assert scan.startswith("**Security scan.** Run it whether or not skill-check ran.")
    assert _bash_block(scan, "{securityScanHelper}") == SCAN_CALL
    for needle in ("Bind `{security_result}` ← its `security_result` (`pass`, `warn` or `skipped`) and "
                   "`{security_note}` ← its `note` in `{run_dir}/security.json`, whose `findings[]` §6 lists as "
                   "advisory validation issues: security findings do not block output",
                   "when the file holds no JSON object, bind `skipped` and `skf-security-scan.py printed no result`",
                   'For `skipped`, log "security scan skipped: {security_note}" in the validation results.',
                   "When no `{securityScanProbeOrder}` path exists, bind `{security_result}` ← `skipped` and "
                   "`{security_note}` ← `skf-security-scan.py missing`",
                   "rely on the JSON it prints, never on an exit code"):
        assert needle in scan, needle
    # §3's skip binds nothing: the scan still runs.
    three = _section(text, "### 3. ", "### 4. ")
    assert "the security scan at the end of section 4 still runs" in three and "security_result" not in three
    report = _section(text, "### 6. Report Validation Results", "### 7. ")
    assert "**Security:** {security_result}\n{`{security_note}`, then each §4 security finding}\n" in report
    assert "`issues.security`" in report and '--security "{run_dir}/security.json"' in report
    # The old reading of skill-check's stderr tail is gone, and no note names an issue number.
    for stale in ("finding code", "skill-check.stderr` and the exit code", "security[]", "#892", "mcp-scan"):
        assert stale not in text, stale
    # The score clause renders only with a score, never as "null/100".
    assert ("**SKILL.md:** {pass/issues found}{ (quality score: {quality_score}/100), only when `{quality_score}` is "
            "not null}\n") in report
    assert "if skill-check was available" not in report
    assert "{pass/warn/skipped}" not in text


def test_step_5_captures_skill_check_and_reads_a_run_with_no_json():
    """#885 reviews 1 and 2: stdout, stderr and the exit code are read apart, the guard restores whatever
    skill-check exits, even when the shell tool stops the block, and a run whose stdout does not
    start with JSON did not validate."""
    four = _section(_read(WRITE_AND_VALIDATE), "### 4. Validate SKILL.md via skill-check", "### 5. ")
    capture = '> "{run_dir}/skill-check.json" 2> "{run_dir}/skill-check.stderr"'
    call = _bash_block(four, "npx skill-check check").splitlines()[2]
    assert call == (f'npx skill-check check "{{skill_package}}" --fix --format json --no-security-scan {capture}; '
                    'echo "skill-check exited $?"')
    assert "then run the five commands in order. `verify-restore` runs whatever skill-check exits" in four
    stopped = _section(four, '**If no "skill-check exited" line came back**', "\n")
    for needle in ("the shell tool stopped the block before skill-check finished",
                   "run the `verify-restore` command on its own before reading `{run_dir}/skill-check.json`",
                   "so a description `--fix` rewrote is restored, then run the second `hash` command."):
        assert needle in stopped, needle
    assert four.index("```bash") < four.index(stopped) < four.index("**Guard outputs.**")
    fallback = _section(four, "**If no `{descriptionGuardProbeOrder}` path exists**", "\n")
    assert f"with the same capture (`{capture}`, its exit code noted)" in fallback
    # stdout can carry a "Wrote <path>" line after the JSON; §6's summarizer reads the object at its start (#1120).
    no_json = _section(four, "**If `{run_dir}/skill-check.json` does not start with a JSON object**", "\n")
    for needle in ("skill-check stopped before it validated (exit 2 on a config, option or plugin error)",
                   'log "skill-check failed: {the stderr line that names the cause, or its last line}" and run the '
                   "frontmatter validator below, as when skill-check is not available",
                   "Otherwise skill-check validated, even when its stdout goes on after the JSON (a `Wrote <path>` "
                   "line when the project config sets a report path): §6 reads the score and the remaining "
                   "diagnostics from that JSON."):
        assert needle in no_json, needle
    assert "keep `{quality_score}` null" not in four and "**Parse the JSON in" not in four
    assert four.index(no_json) < four.index("**If skill-check is not available**")


HASH_PROBE = ["{project-root}/_bmad/skf/shared/scripts/skf-hash-content.py",
              "{project-root}/src/shared/scripts/skf-hash-content.py"]


def test_step_5_tells_a_fix_from_the_file_hash():
    """#901: skill-check 1.2.0's JSON has no `fixed[]`, so two `hash` lines open and close the guarded block,
    their files in the run folder, and a changed or unhashed SKILL.md is noted for §6 but counted nowhere."""
    text = _read(WRITE_AND_VALIDATE)
    assert "fixed[]" not in text
    frontmatter = text.split("---\n", 2)[1]
    assert "hashContentProbeOrder:\n" + "".join(f"  - '{path}'\n" for path in HASH_PROBE) in frontmatter
    four = _section(text, "### 4. Validate SKILL.md via skill-check", "### 5. ")
    assert "`{hashContentHelper}` ← first existing path in `{hashContentProbeOrder}`" in four
    lines = _bash_block(four, "npx skill-check check").splitlines()
    assert len(lines) == 5
    hash_call = 'uv run {hashContentHelper} hash "{skill_package}/SKILL.md" > "{run_dir}/skill-md-hash-%s.json"'
    assert (lines[0], lines[-1]) == (hash_call % "before", hash_call % "after")
    assert " capture " in lines[1] and " verify-restore " in lines[3]
    note = _section(four, "**Rewrite note.**", "\n")
    for needle in ("Bind `{skill_md_changed}` ← true when the `content_hash` in `{run_dir}/skill-md-hash-before.json` "
                   "differs from the one in `{run_dir}/skill-md-hash-after.json`, taken after the last `verify-restore`",
                   "run the second `hash` command again after a `verify-restore` re-run",
                   # Not hashed: no helper, or a file with no hash, is a change nobody saw, said so, acted on alike.
                   "When no `{hashContentProbeOrder}` path exists (leave both `hash` commands out) or either file holds "
                   "no `content_hash`, SKILL.md was not hashed: bind `{skill_md_changed}` ← true as well.",
                   'record the validation note "skill-check --fix rewrote SKILL.md", or "SKILL.md may have been '
                   'rewritten (not hashed) by skill-check --fix" when it was not hashed, which §6 lists with the '
                   "auto-fixed issues",
                   # Guard missing: skill-check runs without `--fix`, so nothing is hashed and nothing noted.
                   "the guard below is missing), `--fix` did not run: hash nothing and bind `{skill_md_changed}` ← "
                   "false."):
        assert needle in note, needle
    assert four.index("**Guard outputs.**") < four.index(note) < four.index("**If no `{descriptionGuardProbeOrder}`")
    unguarded = _section(four, "**If no `{descriptionGuardProbeOrder}` path exists**", "\n")
    assert "hash" not in unguarded
    report = _section(text, "### 6. Report Validation Results", "### 7. ")
    assert ("{list the auto-fixed issues: the §4 rewrite note when `{skill_md_changed}` is true, and the §4 "
            "description-guard note when the guard restored the description}") in report
    assert ('List beside them the notes §4 recorded, which count nothing: the rewrite note, the guard note, '
            '"skill-check failed", "description guard unavailable" and the guard\'s high-severity issues.') in report


def test_finalize_relays_the_flip_helpers_message():
    """W3 re-check leanness-4: the flip's exit 2 also means a held lock, so the halt shows the helper's message."""
    flip = _section(_read(FINALIZE), "### 1. Create Active Pointer", "### 2. ")
    assert _bash_block(flip, "flip-link").startswith("uv run {atomicWriteHelper} flip-link")
    assert "the `message` of the helper's" in flip and "another process holds its lock" in flip
    for stale in ("flock", "rename-over-symlink", "existing path is not a symlink or junction",
                  "Reuse the same values here"):
        assert stale not in flip, stale
    # The halt site tells an automator that a held lock also ends in exit 7 (#1173: no Raised by column).
    [(_, code, reason, segment)] = [site for site in _halt_sites() if site[0] == "finalize.md"]
    assert (code, reason) == (7, "finalize-blocked") and segment in flip
    assert ("(something that is not a link is at `{skill_group}/active`, or another process holds its lock)"
            in segment)
    assert "non-link in place" not in segment


def test_the_active_pointer_gate_keeps_another_generators_build():
    """#1175 enhancement-1: step 5 binds the version `active` names, and finalize asks before it moves `active` off
    another workflow's build; a headless run keeps it, records `finalize.active-pointer` and reports
    `kept-prior-active`."""
    assert "`{prior_active_version}` ← `write_check.marked_active_version`" in _read(WRITE_AND_VALIDATE)
    flip = _section(_read(FINALIZE), "### 1. Create Active Pointer", "### 2. ")
    order = [flip.index(needle) for needle in ("**If `{overrides.no_active_pointer}` is true**",
                                               "When step 5 §1 bound `{prior_active_version}` and it is neither "
                                               "`{version}` nor `active`",
                                               "Select: [F] Point it at this quick skill · [K] Keep it",
                                               "**Resolve `{atomicWriteHelper}`**")]
    assert order == sorted(order), "--no-active-pointer, then the gate, then the helper"
    for needle in ("bind `{prior_generator}` ← `generated_by` and `{prior_tier}` ← `confidence_tier` of "
                   "`{skill_group}/{prior_active_version}/{repo_name}/metadata.json` (each null when absent)",
                   "When `{prior_generator}` is not `quick-skill`",
                   "**`{skill_group}/active` points at the `{prior_generator}` build of v{prior_active_version} "
                   "({prior_tier}).**",
                   'say "an SKF build" in place of "the `{prior_generator}` build" when `{prior_generator}` is null',
                   # The package is written by now, so the universal cancel's "No files were written" would be false.
                   "The package is already written, so `cancel`, `exit` or `:q` at this question keeps the pointer as "
                   "**IF K** does."):
        assert needle in flip, needle
    options = _options(flip)
    assert list(options) == ["IF F", "IF K", "GATE [default: K]"]
    assert "go on to the flip below" in options["IF F"]
    for needle in ('log "Active pointer: kept on v{prior_active_version}."', "set `{active_pointer}` to "
                   "`kept-prior-active`", "with the active-pointer line omitted from the completion summary and the "
                   "outputs payload"):
        assert needle in options["IF K"], needle
    headless = options["GATE [default: K]"]
    assert "if `{headless_mode}` is true, keep it as **IF K** does and record the decision" in headless
    decision = _filled(_staged(headless, "decision.json"))
    assert (decision["gate"], decision["default_action"], decision["taken_action"]) == ("finalize.active-pointer",
                                                                                      "K", "K")
    assert set(decision["evidence"]) == {"prior_active_version", "prior_generator"}
    schema = _schema()
    assert "kept-prior-active" in schema["properties"]["summary"]["properties"]["active_pointer"]["enum"]
    gates = schema["properties"]["headless_decisions"]["items"]["properties"]["gate"]["enum"]
    assert "finalize.active-pointer" in gates
    section = _section(_read(FINALIZE), "### 3. Result Envelope and Result Contract", "### 4. ")
    context = json.loads(_success_payload(section).replace('"active_pointer": "symlink"',
                                                           '"active_pointer": "kept-prior-active"'))
    del context["outputs"]["active_pointer"]
    emitter = _emitter()
    envelope = emitter.build_envelope(schema, context, halt=False, decisions=[decision], warnings=[], stamps={
        "timestamp": "2026-11-13T00:00:00Z", "run_id": "ab12cd34", "result_path": None})
    assert emitter.contract_errors(schema, envelope) == []
    assert envelope["summary"]["active_pointer"] == "kept-prior-active"
    summary = _section(_read(FINALIZE), "### 2. Display Completion Summary", "### 3. ")
    assert "- `{skill_group}/active` -> `{version}` (omit this line when §1 flipped no pointer)" in summary
    # test-skill and export-skill read the version `active` names, so the summary says which one that is.
    assert ("{If §1 set `{active_pointer}` to `kept-prior-active`, add:} **Active:** still points at "
            "v{prior_active_version}, the version test-skill and export-skill read; re-run Quick Skill and answer F "
            "to move it to v{version}.") in summary
    [row6] = [line for line in _read(SKILL).splitlines() if line.startswith("| 6 | Finalize |")]
    assert row6 == "| 6 | Finalize | references/finalize.md | Conditional (`active` on another workflow's build) |"
    [row] = [line for line in _read(INVOCATION_CONTRACT).splitlines() if line.startswith("| **Gates** |")]
    assert row.endswith("; step 6: active pointer [F/K] (when `active` names another workflow's build; headless "
                        "keeps it) |")
    [no] = [line for line in _overwrite().splitlines() if line.startswith("**GATE [default: N]**")]
    assert ("to keep it, give the quick skill another version (`@Ferris QS <package>@<version>`): when `active` names "
            "another workflow's build, that run moves it only if you answer F, and a headless run keeps it.") in no
    safety = next(line for line in _section(_read(DOCS), "### Quick Skill (QS)", "**Agent:**").splitlines()
                  if line.startswith("**Safety:**"))
    for needle in ("(`[F]`) or keep it (`[K]`)", "a headless run keeps it", "`finalize.active-pointer`",
                   "`kept-prior-active`", "so a `forge-quick` chain then tests and exports that other build, not the "
                   "quick skill"):
        assert needle in safety, needle
    # A pipeline runs QS headless and hands TS and EX the skill name alone, so they act on the kept build.
    [row] = [line for line in _read(REPO / "src" / "shared" / "references" / "pipeline-contracts.md").splitlines()
             if line.startswith("| QS | TS |")]
    assert "QS keeps it there (`summary.active_pointer` `kept-prior-active`) and TS tests that build" in row
    assert "so `forge-quick` on such a skill tests and exports that build, not the quick skill" in _read(DOCS)
    # The cancel rule and the writers' list name this question's exception.
    [cancel] = [line for line in _rules("SKILL.md").splitlines() if line.startswith("- **Universal cancel-line")]
    assert cancel.endswith("Step 6 §1 comes after the write: a cancel there keeps the pointer, as its [K] does.")
    [writer] = [line for line in _read(REPO / "src" / "knowledge" / "version-paths.md").splitlines()
                if line.startswith("6. Create or update the `active` symlink")]
    assert writer.endswith("(QS asks first when `active` names another workflow's build, and a headless run keeps "
                           "it there)")


@pytest.mark.parametrize("generator, asks", [("create-skill", True), ("quick-skill", False)])
def test_the_active_pointer_question_reads_the_build_active_names(tmp_path, generator, asks):
    """#1175: the write check names the version `active` points at, and the metadata.json finalize §1 reads beside
    it names its generator: a Create Skill build there is asked about, a quick skill is moved as before."""
    skills = tmp_path / "skills"
    built = skills / "cognee" / "2.0.0" / "cognee"
    built.mkdir(parents=True)
    (built / "metadata.json").write_text(json.dumps({"generated_by": generator, "confidence_tier": "Forge"}),
                                         encoding="utf-8")
    atomic = _load(SCRIPTS / "skf-atomic-write.py", "skf_atomic_write_for_active_gate")
    atomic._create_symlink_or_junction("2.0.0", skills / "cognee" / "active")
    inventory = _load(SCRIPTS / "skf-skill-inventory.py", "skf_skill_inventory_for_active_gate")
    check = inventory.write_check(skills, "cognee", "1.0.0", None)
    assert (check["verdict"], check["marked_active_version"]) == ("ok", "2.0.0")
    flip = _section(_read(FINALIZE), "### 1. Create Active Pointer", "### 2. ")
    [path] = re.findall(r"of `(\{skill_group\}/\{prior_active_version\}/\{repo_name\}/metadata\.json)`", flip)
    path = path.replace("{skill_group}", (skills / "cognee").as_posix()).replace("{repo_name}", "cognee")
    metadata = json.loads(Path(path.replace("{prior_active_version}", check["marked_active_version"]))
                          .read_text(encoding="utf-8"))
    assert (metadata["generated_by"] != "quick-skill") == asks
    assert metadata["confidence_tier"] == "Forge"


def test_the_active_pointer_question_skips_a_real_active_folder(tmp_path):
    """#1175 review: a real `active/` folder holding a marked package is reported as "active", not a version, so
    finalize §1 asks nothing about it and the flip refuses it with exit 7, as before the question existed."""
    package = tmp_path / "skills" / "cognee" / "active" / "cognee"
    package.mkdir(parents=True)
    (package / "metadata.json").write_text(json.dumps({"generated_by": "create-skill"}), encoding="utf-8")
    inventory = _load(SCRIPTS / "skf-skill-inventory.py", "skf_skill_inventory_for_real_active")
    check = inventory.write_check(tmp_path / "skills", "cognee", "1.0.0", None)
    assert (check["verdict"], check["marked_active_version"]) == ("ok", "active")
    flip = _section(_read(FINALIZE), "### 1. Create Active Pointer", "### 2. ")
    assert ("When step 5 §1 bound `{prior_active_version}` and it is neither `{version}` nor `active` (a real folder "
            "there, which the flip below refuses), bind") in flip
    assert "When a real folder is at `{skill_group}/active`" in flip


def test_skill_md_keeps_one_home_per_rule():
    text = _read(SKILL)
    for stale in ("runs as today", "in parallel (one batched tool-call message", "From preferences:",
                  "write-and-validate §1 runs the inventory's", "-latest.json", "so stage files don't have to repeat"):
        assert stale not in text, stale
    # "step 5" alone names write-and-validate in this table (`--skip-snippet`'s "step 5 §2").
    [batch] = [line for line in text.splitlines() if line.startswith("   | `--batch <file>` |")]
    assert "headless (On Activation step 5);" in batch
    assert ("or if step 1's preflight gave `derived.headless_mode` true (`headless_mode: true` in "
            "`{sidecar_path}/preferences.yaml`)") in text
    assert "or if `{sidecar_path}/preferences.yaml` sets `headless_mode: true`" not in text
    step5 = _section(text, "5. **If `--batch` is set**", "\n\n6. ")
    assert step5.strip() == "5. **If `--batch` is set**, load and read `references/batch-mode.md` in full before " \
                            "anything else and follow it."


# --------------------------------------------------------------------------
# step 5b enhancement-2: the overwrite gate names the build it replaces and
# never replaces another generator's package unasked
# --------------------------------------------------------------------------


def _overwrite() -> str:
    return _section(_read(WRITE_AND_VALIDATE), "If `{skill_package}/metadata.json` exists, confirm",
                    "A `{skill_package}` without `metadata.json`")


def test_the_overwrite_question_names_the_build_from_the_write_check():
    text = _read(WRITE_AND_VALIDATE)
    assert ("`{existing_generator}` ← `write_check.version_generated_by` and `{existing_tier}` ← "
            "`write_check.version_confidence_tier`") in text
    gate = _overwrite()
    assert ("It holds a `{existing_generator}` build ({existing_tier}); overwriting replaces it whole with a "
            "community quick skill") in gate
    assert "Overwrite will replace the prior compiled output" not in gate
    assert "**GATE [default: Y]** when `{existing_generator}` is `quick-skill` or null" in gate
    [no] = [line for line in gate.splitlines() if line.startswith("**GATE [default: N]**")]
    assert "for any other `{existing_generator}`" in no and "then halt as **If user selects N** does" in no
    assert "a headless run never replaces another workflow's build" in no and "interactively and answer Y" in no
    assert 'leave out " ({existing_tier})" when only `{existing_tier}` is null' in gate
    halt = _staged(_section(gate, "- **If user selects N:**", "**GATE [default: Y]**"), "halt.json")
    assert _filled(halt)["details"] == {"existing_generator": "{existing_generator}"}
    summary = _section(_read(FINALIZE), "### 2. Display Completion Summary", "### 3. ")
    assert "{If step 5 §1 set `{replaced_build}`, add:} **Replaced:** the `{replaced_build}` build" in summary
    assert "`{forge_data_folder}/{repo_name}/{version}/`, is left in place" in summary
    docs = _read(REPO / "docs" / "workflows.md")
    safety = _section(docs, "### Quick Skill (QS)", "**Agent:**")
    safety = next(line for line in safety.splitlines() if line.startswith("**Safety:** Writes a version only"))
    assert "exit `5` (`overwrite-cancelled`)" in safety and "`error.details.existing_generator`" in safety


@pytest.mark.skipif(sys.platform == "win32", reason="runs the step's command through a POSIX shell")
def test_a_yes_over_another_generator_replaces_the_package_whole(tmp_path):
    """The guarded removal clears create-skill's leftovers and nothing outside the version package."""
    block = _nested_bash_block(_overwrite(), "rm -rf")
    assert block.startswith('case "{skill_package}" in */{repo_name}/{version}/{repo_name})')
    skills = tmp_path / "skills"
    package = skills / "cognee" / "1.0.0" / "cognee"
    for rel in ("SKILL.md", "metadata.json", "extraction-rules.yaml", "references/api.md"):
        (package / rel).parent.mkdir(parents=True, exist_ok=True)
        (package / rel).write_bytes(b"x")
    (skills / "cognee" / "0.9.0").mkdir(parents=True)
    bash = _tool("bash")

    def run(path: Path) -> None:
        script = (block.replace("{skill_package}", path.as_posix()).replace("{repo_name}", "cognee")
                  .replace("{version}", "1.0.0"))
        subprocess.run([bash, "-c", script], check=True, capture_output=True, timeout=60)

    run(package)
    assert package.is_dir() and list(package.iterdir()) == []
    assert (skills / "cognee" / "0.9.0").is_dir()
    run(skills / "cognee")  # not a version package: the guard removes nothing
    assert (skills / "cognee" / "0.9.0").is_dir()


# --------------------------------------------------------------------------
# step 5b enhancement-1: a headless single-target run ends on its envelope
# --------------------------------------------------------------------------


def test_a_headless_run_hands_its_envelope_line_to_the_health_check():
    envelope = _section(_read(FINALIZE), "### 3. Result Envelope and Result Contract", "### 4. ")
    for needle in ("In a headless single-target run, bind `{result_envelope_line}` ← that line and do not "
                   "display it here", "the shared health check displays it verbatim as the run's last line",
                   "Otherwise (an interactive run, or a `--batch` target) display it verbatim as its own line",
                   "leave `{result_envelope_line}` empty"):
        assert needle in envelope, needle
    relay = _read(HEALTH_CHECK)
    assert "step 6 §3 bound `{result_envelope_line}` to the `SKF_QUICK_SKILL_RESULT_JSON` line" in relay
    shared = _read(REPO / "src" / "shared" / "health-check.md")
    assert "may bind `{result_envelope_line}`" in shared
    docs = _read(REPO / "docs" / "workflows.md")
    final = next(line for line in docs.splitlines()
                 if line.startswith("Setup is not the only workflow whose result line is the run's final message"))
    assert "Quick Skill (one target, not `--batch`)" in final and "`SKF_QUICK_SKILL_RESULT_JSON`" in final


# --------------------------------------------------------------------------
# #1173: a run loads no text it never acts on
# --------------------------------------------------------------------------

# How often each file states each standard command: once in each stage file's Rules, once in SKILL.md's Workflow
# Rules (the cancel-line and headless bullets) and once at batch-mode.md's one standard site; every other site
# names its own command (a `--result-dir` or `{batch_dir}` variant, or a heredoc with no run folder).
STANDARD_COMMAND_HOMES = {
    EMIT_COMMAND: {"SKILL.md": 1, "batch-mode.md": 1, "compile.md": 1, "quick-extract.md": 1, "resolve-target.md": 1,
                   "write-and-validate.md": 1},
    RECORD_COMMAND: {"SKILL.md": 1, "compile.md": 1, "finalize.md": 1, "quick-extract.md": 1,
                     "resolve-target.md": 1, "write-and-validate.md": 1},
}
RULES_STAGES = ("compile.md", "quick-extract.md", "resolve-target.md", "write-and-validate.md")


def test_each_file_states_each_standard_command_once():
    files = [SKILL, *sorted((QS / "references").glob("*.md"))]
    for command, homes in STANDARD_COMMAND_HOMES.items():
        counts = {path.name: _read(path).count(f"`{command}`") for path in files}
        assert {name: n for name, n in counts.items() if n} == homes, command
    for name in RULES_STAGES:
        [bullet] = [line for line in _rules(name).splitlines() if line.startswith("- A HARD HALT stages")]
        assert bullet.startswith(f"- A HARD HALT stages the payload its site gives as `{{run_dir}}/halt.json` and "
                                 f"runs `{EMIT_COMMAND}`, unless its site names its own command, and a headless gate "
                                 f"stages the decision its site gives as `{{run_dir}}/decision.json` and runs "
                                 f"`{RECORD_COMMAND}`. A HARD HALT prints, after its envelope, this step's `halt` "
                                 "event"), name
    rules = _rules("SKILL.md")
    [cancel] = [line for line in rules.splitlines() if line.startswith("- **Universal cancel-line affordance**")]
    [record] = [line for line in rules.splitlines() if line.startswith("- If `{headless_mode}` is true, auto-proceed")]
    assert f"`{EMIT_COMMAND}`" in cancel and f"`{RECORD_COMMAND}`" in record
    before = _section(_read(BATCH_MODE), "## Before the Batch Starts", "## Input format")
    assert f"`{EMIT_COMMAND}`" in before


def test_skill_md_points_to_the_contract_it_no_longer_holds():
    text = _read(SKILL)
    assert "\n| **" not in text and len(text) < 14000
    section = _section(text, "## Invocation Contract\n", "## On Activation")
    assert section.split("\n\n")[1] == (
        "Headless callers and pipelines: the inputs, flags, gates, outputs, exit codes and the "
        "`SKF_QUICK_SKILL_RESULT_JSON` and `--batch` reading rules live in `references/invocation-contract.md`. "
        "Interactive runs do not need it.")
    contract = _read(INVOCATION_CONTRACT)
    assert contract.startswith("# Invocation Contract: skf-quick-skill\n\nThe inputs, flags, gates, outputs, exit "
                               "codes and result-reading rules of `skf-quick-skill`, for headless callers and "
                               "pipelines. Interactive runs do not need this file.\n\n| Aspect | Detail |\n")
    rows = [line.split("|")[1].strip() for line in contract.splitlines() if line.startswith("| **")]
    assert rows == ["**Inputs**", "**Overrides**", "**Gates**", "**Outputs**", "**Headless**", "**Exit codes**"]


def test_the_exit_code_table_keeps_code_and_meaning():
    contract = _read(HALT_CONTRACT)
    codes = _section(contract, "## Exit Codes", "## Result Contract")
    rows = [line for line in codes.splitlines() if line.startswith("|")]
    assert len(rows) == 11 and all(line.count("|") == 3 for line in rows), rows
    for stale in ("Raised by", "compacted away"):
        assert stale not in contract, stale
    assert _paragraph(contract, "The exit-code map") == ("The exit-code map, the envelope every HARD HALT emits, the "
                                                         "headless progress events and the `--batch` rule.")


def test_batch_mode_keeps_only_what_the_batch_does():
    """The summary schema, the status rule, the events and the reading rules are the caller's (docs/workflows.md
    and references/invocation-contract.md); the helper computes them, so batch-mode.md does not carry them."""
    batch = _read(BATCH_MODE)
    for moved in ("**Reading a batch.**", "## Batch summary contract", "## Headless events", "## Exit code",
                  "`status` resolves as:"):
        assert moved not in batch, moved
    docs = _read(DOCS)
    summary = _paragraph(docs, "**Batch summary file.**")
    assert ("the batch helper (`skf-quick-batch.py summarize`) writes the batch summary to "
            "`quick-skill-batch-{YYYYMMDD-HHmmss}.json` in `batch_output_path` (default "
            "`{skills_output_folder}/_batch/`; a Quick Skill setting, see [Customizing a Workflow]"
            "(#customizing-a-workflow))") in summary
    events = _paragraph(docs, "**Batch events.**")
    assert ("the batch helper prints a target's `start` event when it hands the target out (`next`), its `done` "
            "or `fail` event when it records the outcome (`record`) and one final `batch_summary` event "
            "(`summarize`), on stderr") in events
    assert "and `{batch_dir}` the batch's run folder, `_bmad-output/.skf-run/skf-quick-skill-*`" in events
    # The Batch mode paragraph points at the summary file paragraph, which names the batch_output_path setting.
    assert "(**Batch summary file** below)" in _paragraph(docs, "**Batch mode (`--batch <file>`).**")
    # The contract names where the batch reading rules it does not hold live.
    assert "Quick Skill's **Batch mode**, **Batch summary file** and **Batch events** paragraphs and " \
           "**Reading the result lines**" in _read(INVOCATION_CONTRACT)
    assert docs.index("**Batch mode (`--batch <file>`).**") < docs.index("**Batch summary file.**") \
        < docs.index("**Batch events.**") < docs.index("**Exception: `/skf-brief-skill`")
    assert "Full input grammar in [`src/skf-quick-skill/references/batch-mode.md`]" in docs


def test_no_file_names_the_registry_data_file():
    assert not (QS / "references" / "registry-resolution.md").exists()
    for path in [*sorted(p for p in QS.rglob("*") if p.is_file()), RESOLVER]:
        text = _read(path)
        for stale in ("registry-resolution", "registryResolution"):
            assert stale not in text, (path.name, stale)


def test_the_stages_name_only_the_helper_fields_they_read():
    assert "module.yaml" not in _sniff()
    parse = _section(_read(QUICK_EXTRACT), "### 3. Parse Manifest and Scan Exports", "### 4. ")
    assert "pub use" not in parse and "`extra`" not in parse
    assert ("The helper writes JSON to `{run_dir}/extract.json`: §4 builds the inventory from its `package_name`, "
            "`version`, `description`, `exports[]` and `dependencies[]`, and the paragraphs below read:") in parse
    detect = _section(_read(RESOLVE_TARGET), "### 4. Detect Language", "### 5. ")
    delegate = _section(detect, "2. **Delegate the rule walk", "3. **Auto-pick**")
    assert "folder depth" not in delegate and "detection_source" not in delegate
    assert ("Read its `language` and `detected_languages`: `detected_languages[0]` is the helper's pick, `language`, "
            "and the list holds every other language a manifest or the source files name.") in delegate


# --------------------------------------------------------------------------
# #1174: each value a helper or a staged file holds is taken from there
# --------------------------------------------------------------------------


def test_a_renderer_that_fails_twice_halts_with_its_error_on_screen_only():
    """determinism-3: a renderer that still fails after one fix halts with exit 3, in interactive mode too,
    instead of rendering metadata.json in the prompt. Its error line can name an absolute path, so the staged
    reason is one the step wrote and the line is shown on screen only (headless-gate-convention.md)."""
    render = _section(_read(COMPILE), "### 3. Generate Metadata JSON", "### 4. ")
    failed = _section(render, "If the renderer exits non-zero", "\n\n")
    [site] = [segment for name, code, reason, segment in _halt_sites()
              if name == "compile.md" and '"cause": "quick-metadata-renderer-error"' in segment]
    assert site.startswith("HARD HALT with **exit code 3 (resolution-failure)**, in interactive mode too")
    assert site.strip() in failed and failed.index("fix that file once") < failed.index(site.strip())
    assert ("**Cannot render `metadata.json` for `{repo_name}`.** SKF's quick metadata renderer "
            "(`skf-render-quick-metadata.py`) failed twice: {its error line}.\"") in site
    assert _filled(_staged(site, "halt.json")) == {
        "phase": "compile", "halt_reason": "resolution-failure",
        "reason": "Cannot render metadata.json for {repo_name}.", "skill_package": None,
        "details": {"cause": "quick-metadata-renderer-error"}}
    assert site.rstrip().endswith("the error line, which can name an absolute path, is shown on screen only.")


def test_finalize_reports_the_version_and_export_count_metadata_json_holds():
    """determinism-2: the summary and the result envelope give the version and the export count of the
    metadata.json step 5 installed, and no step keeps a count of its own; compile's headless line reads the
    rendered file too."""
    finalize = _read(FINALIZE)
    for stale in ("{export count}", "{count}", "{export_count}"):
        assert stale not in finalize, stale
    summary = _section(finalize, "### 2. Display Completion Summary", "### 3. ")
    assert summary.split("\n\n")[1] == (
        "Bind `{exports_documented}` ← `stats.exports_documented` of `{skill_package}/metadata.json`, the file "
        "step 5 installed, whose `version` is `{version}` (§1): the summary and §3 report both from that file, "
        "never a count of their own.")
    assert "**Skill:** {repo_name} v{version}\n" in summary
    assert "**Exports documented:** {exports_documented}\n" in summary
    assert "`{version}` is the `version` of the `metadata.json` step 5 installed" in finalize
    envelope = _section(finalize, "### 3. Result Envelope and Result Contract", "### 4. ")
    payload = _staged(envelope, "result-context.json")
    assert '"version": "{version}",' in payload and '"exports_documented": {exports_documented},' in payload
    assert ("`version` (`{skill_package}/metadata.json`'s, §2), `language`, `exports_documented` (that file's "
            "`stats.exports_documented`, §2)") in envelope
    headless = _section(_read(COMPILE), "### 5. Present Compiled Output for Review", "### 6. ")
    assert "SKILL.md ({section_count} sections, {metadata.stats.exports_documented} exports)" in headless
    for path in sorted(p for p in QS.rglob("*") if p.is_file()):
        text = _read(path)
        for stale in ("in-prompt", "do not write files to disk", "{export count}", "{export_count}"):
            assert stale not in text, (path.name, stale)


ATOMIC_WRITE = SCRIPTS / "skf-atomic-write.py"
# Drafts a double-quoted shell string or an unquoted heredoc would rewrite: `$HOME`, `$(...)`, a backtick,
# `"`, `\` and a line ending in `\`.
SKILL_DRAFT = ("---\nname: acme\ndescription: Reads `$HOME` and \"quoted\" paths like C:\\x\\y. It's $(echo no).\n"
               "---\n\n# acme\n\n```bash\necho \"$HOME\" `pwd` \\\n  done\n```")
SNIPPET_DRAFT = "[acme v0.4.0]|root: skills/acme/\n|api: run(\"$HOME\"), `tick`, C:\\x\\"


@pytest.mark.skipif(sys.platform == "win32", reason="runs the step's commands through a POSIX shell")
def test_the_drafts_are_staged_in_the_run_folder_and_installed_as_written(tmp_path):
    """enhancement-2: compile §2 and §4 write the SKILL.md and snippet drafts through quoted heredocs, the preview,
    [E] and a revision work on those files, and step 5 §2 installs all three files with the atomic writer,
    metadata.json first: the installed bytes are the staged bytes. [S] deletes the drafts and nothing else."""
    bash = _tool("bash")
    compile_md = _read(COMPILE)
    skill_block = _bash_block(_section(compile_md, "### 2. Assemble SKILL.md", "### 3. "), "SKF_SKILL_MD")
    assert skill_block == "cat > \"{run_dir}/SKILL.md\" <<'SKF_SKILL_MD'\n<the assembled SKILL.md>\nSKF_SKILL_MD\n"
    snippet = _section(compile_md, "### 4. Generate Context Snippet", "### 5. ")
    snippet_block = _bash_block(snippet, "SKF_SNIPPET")
    assert snippet_block == ("cat > \"{run_dir}/context-snippet.md\" <<'SKF_SNIPPET'\n<the context snippet>\n"
                             "SKF_SNIPPET\n")
    assert "skip generation, write no `{run_dir}/context-snippet.md`" in snippet
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text('{"name": "acme", "version": "0.4.0"}\n', encoding="utf-8")
    package = tmp_path / "skills" / "acme" / "0.4.0" / "acme"

    def run(block: str) -> None:
        script = (block.replace("uv run {atomicWriteHelper}", f'"{sys.executable}" "{ATOMIC_WRITE.as_posix()}"')
                  .replace("{run_dir}", run_dir.as_posix()).replace("{skill_package}", package.as_posix()))
        done = subprocess.run([bash, "-c", script], capture_output=True, text=True, check=False)
        assert done.returncode == 0, done.stderr

    run(skill_block.replace("<the assembled SKILL.md>", SKILL_DRAFT))
    run(snippet_block.replace("<the context snippet>", SNIPPET_DRAFT))
    assert (run_dir / "SKILL.md").read_bytes() == (SKILL_DRAFT + "\n").encode("utf-8")
    assert (run_dir / "context-snippet.md").read_bytes() == (SNIPPET_DRAFT + "\n").encode("utf-8")
    write = _section(_read(WRITE_AND_VALIDATE), "### 2. Write Deliverables", "### 3. ")
    installs = _bash_blocks(write)
    names = ["metadata.json", "SKILL.md", "context-snippet.md"]
    assert installs == [f'uv run {{atomicWriteHelper}} write --target "{{skill_package}}/{name}" < '
                        f'"{{run_dir}}/{name}"\n' for name in names]
    assert "2. `{skill_package}/SKILL.md`: installed from `{run_dir}/SKILL.md`, which step 4 §2 staged" in write
    assert ("3. `{skill_package}/context-snippet.md`: installed from `{run_dir}/context-snippet.md`, which step 4 §4 "
            "staged") in write
    for block in installs:
        run(block)
    for name in names:
        assert (package / name).read_bytes() == (run_dir / name).read_bytes(), name
    [rule] = [line for line in _rules("write-and-validate.md").splitlines() if line.startswith("- Install exactly")]
    assert rule == "- Install exactly the files step 4 staged: do not modify content during writing or after validation"
    # The preview, [E] and a free-form revision read and write the drafts on disk.
    preview = _section(compile_md, "### 5. Present Compiled Output for Review", "### 6. ")
    assert "{Display `{run_dir}/SKILL.md` as it is on disk}" in preview
    assert "{Display `{run_dir}/context-snippet.md`}" in preview
    menu = compile_md.splitlines()
    [edit] = [line for line in menu if line.startswith("- **IF E**")]
    assert ("Write `{run_dir}/SKILL.md` again through §2's quoted heredoc with the new frontmatter "
            "`description`") in edit
    assert "re-render the §5 preview from the files" in edit
    [other] = [line for line in menu if line.startswith("- **IF Any other**")]
    assert ("write the changed draft, `{run_dir}/SKILL.md` or `{run_dir}/context-snippet.md`, again through its "
            "quoted heredoc, then re-render the §5 preview from the files") in other
    # [S] deletes the drafts before the re-extraction, which compiles new ones.
    [rescope] = [line for line in menu if line.startswith("- **IF S**")]
    rm = re.search(r"delete the drafts \(`(rm -f [^`]+)`\), then load `references/quick-extract.md`", rescope)
    assert rm, rescope
    run(rm.group(1))
    assert sorted(p.name for p in run_dir.iterdir()) == ["metadata.json"]
