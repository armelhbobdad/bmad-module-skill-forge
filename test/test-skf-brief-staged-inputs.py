#!/usr/bin/env python3
"""skf-brief-skill hands repositories, files and payloads to its helpers by file.

#592 (brief part): step 1 §1 creates a run folder. Step 2 lists the
repository into it once (skf-github-probe.py tree, or git ls-files for a
local folder), and the workspace detector, the tree snapshot, the language
detector, the export parser and step 3's scope-type recommender read that
listing and the files fetched beside it, never a list or a file typed into
a command, so a tree of any size reaches them whole and a source file with
an apostrophe reaches the parser as it is. The JSON payloads the steps hand
the validators and the writers are staged there through quoted heredocs,
the [auto] path writes from the upstream brief file itself, and a cancel
removes the folder.

#582 (brief part): the target prompt reads the target with
skf-resolve-package.py parse-target --local-first, so a path on disk is a
local path whatever its shape, and a package name goes through its
resolve. #587 (brief part): the draft checkpoint follows the accepted
description and step 3's scope, and a draft that holds the scope resumes at
step 4. #584 (brief part): step 3's tier-A list comes from the recipe
runner's re-export targets. #603: a docs-only target skips step 2's
repository analysis and reaches step 5 with the language `documentation`.

Step 5b gate run 2: step 2 and step 3 read a GitHub repository through
skf-github-fetch.py, which needs gh only for a private repository, so a
public one is briefed without gh (enhancement-1); step 2 finds the entry
files with the extractor's entries mode and follows the modules an
`export *` names, and step 3 counts the exports from the result
(determinism-1); and a ratify run skips the overwrite gate only when it
writes back to the brief it read (architecture-1).

Step 5b gate run 3 (determinism-3): step 5 writes a ratified brief from the
brief file with a staged patch of the fields steps 3 and 4 can change
(--base-brief, --patch-file), so the fields no step changes, the
amendments log among them, are never retyped; only a derive run stages the
flat payload.

No test runs the step prose, so these checks pin it, and they run the
commands it documents against the helpers, with the fetch helper reading
from a local folder where a command reads GitHub.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO / "src" / "skf-brief-skill"
REFERENCES = SKILL_DIR / "references"
SCRIPTS = REPO / "src" / "shared" / "scripts"
SKILL_MD = SKILL_DIR / "SKILL.md"
GATHER_INTENT = REFERENCES / "gather-intent.md"
INVOCATION_CONTRACT = REFERENCES / "invocation-contract.md"
HEADLESS_ARGS = REFERENCES / "headless-args.md"
RATIFY = REFERENCES / "gather-intent-ratify.md"
ANALYZE_TARGET = REFERENCES / "analyze-target.md"
SCOPE_DEFINITION = REFERENCES / "scope-definition.md"
AUTO_BRIEF = REFERENCES / "step-auto-brief.md"
AUTO_VALIDATE = REFERENCES / "step-auto-validate.md"
WRITE_BRIEF = REFERENCES / "write-brief.md"
DRAFT_CHECKPOINT = REFERENCES / "draft-checkpoint.md"
QMD_REGISTRATION = REFERENCES / "qmd-collection-registration.md"
VERSION_RESOLUTION = REFERENCES / "version-resolution.md"

BASH = shutil.which("bash")
GIT = shutil.which("git")
# The documented blocks are POSIX shell; on Windows `bash` may be WSL's launcher.
POSIX_BASH = BASH is not None and sys.platform != "win32"
needs_bash = pytest.mark.skipif(not POSIX_BASH, reason="runs the documented block in a POSIX bash")

HEREDOC_RE = re.compile(r"<<'(?P<tag>[A-Z_]+)'\n(?P<body>.*?)\n(?P=tag)\n", re.DOTALL)
# A fenced bash block, at any indent (a block inside a list item is indented).
BASH_BLOCK_RE = re.compile(r"^(?P<indent>[ \t]*)```bash\n(?P<body>.*?)^(?P=indent)```", re.DOTALL | re.M)
STAGE_RE = re.compile(r'cat > "\{run_dir\}/(?P<file>[a-z-]+\.json)" <<\'SKF_JSON\'')


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    """The text under the heading line that starts with `heading`, up to the next heading of the same or a
    higher level."""
    match = re.compile(rf"^{re.escape(heading)}[^\n]*\n", re.M).search(text)
    assert match, heading
    level = len(heading) - len(heading.lstrip("#"))
    end = re.compile(rf"^#{{1,{level}}} ", re.M).search(text, match.end())
    return text[match.start():end.start() if end else len(text)]


def _blocks(text: str, needle: str) -> list[str]:
    """The ```bash blocks of `text` that hold `needle`, without the indent of their list item."""
    blocks = []
    for match in BASH_BLOCK_RE.finditer(text):
        indent = len(match.group("indent"))
        body = "".join(line[indent:] for line in match.group("body").splitlines(keepends=True))
        if needle in body:
            blocks.append(body)
    return blocks


def _script(name: str) -> str:
    return f'"{sys.executable}" "{(SCRIPTS / name).as_posix()}"'


def _bash(script: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([BASH, "-c", script], capture_output=True, text=True, encoding="utf-8",
                          timeout=120, check=False, cwd=cwd)


def _run(script: str, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], input=stdin, capture_output=True,
                          text=True, encoding="utf-8", timeout=120, check=False)


def _write_tree(root: Path, files: dict[str, str]) -> Path:
    """Write `files` (repo path -> text) under `root` as bytes, so they keep LF line ends on Windows."""
    for rel, content in files.items():
        path = root.joinpath(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))
    return root


def _probe_listing(paths: list[str], truncated: bool = False) -> str:
    """A listing shaped like skf-github-probe.py tree output."""
    return json.dumps({"status": "ok", "cause": None, "message": None, "repo": "o/r", "gh": "ok", "via": "gh",
                       "ref": "main", "tree": paths, "count": len(paths), "truncated": truncated})


def _fetch_shim(tmp_path: Path, served: Path) -> str:
    """The command that stands in for `uv run {githubFetchHelper}`: skf-github-fetch.py itself, its raw read
    served from `served` (o/r at main, laid out like the repository) and no gh, as on a machine without it."""
    shim = tmp_path / "fetch-shim.py"
    shim.write_bytes((
        "import importlib.util, sys\nfrom pathlib import Path\n"
        f"spec = importlib.util.spec_from_file_location('fetch', {str(SCRIPTS / 'skf-github-fetch.py')!r})\n"
        "mod = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(mod)\n"
        f"served = Path({str(served)!r})\n"
        "def _raw(owner, repo, ref, path):\n"
        "    file = served.joinpath(*path.split('/'))\n"
        "    if (owner, repo, ref) == ('o', 'r', 'main') and file.is_file():\n"
        "        return file.read_bytes(), ''\n"
        "    return None, 'HTTP 404'\n"
        "mod._raw = _raw\nmod._gh_raw = lambda *a: (None, 'gh is not installed')\n"
        "raise SystemExit(mod.main(sys.argv[1:]))\n").encode("utf-8"))
    return f'"{sys.executable}" "{shim.as_posix()}"'


def _extract_shim(tmp_path: Path, served: Path) -> str:
    """The command that stands in for `uv run {extractPublicApiHelper}`: skf-extract-public-api.py itself, the
    fetch helper its --follow loads beside it reading from `served` as _fetch_shim's does."""
    shim = tmp_path / "extract-shim.py"
    shim.write_bytes((
        "import importlib.util, sys\nfrom pathlib import Path\n"
        f"spec = importlib.util.spec_from_file_location('extract', {str(SCRIPTS / 'skf-extract-public-api.py')!r})\n"
        "mod = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(mod)\n"
        "fetch = mod._sibling('skf-github-fetch.py')\n"
        f"served = Path({str(served)!r})\n"
        "def _raw(owner, repo, ref, path):\n"
        "    file = served.joinpath(*path.split('/'))\n"
        "    if (owner, repo, ref) == ('o', 'r', 'main') and file.is_file():\n"
        "        return file.read_bytes(), ''\n"
        "    return None, 'HTTP 404'\n"
        "fetch._raw = _raw\nfetch._gh_raw = lambda *a: (None, 'gh is not installed')\n"
        "raise SystemExit(mod.main(sys.argv[1:]))\n").encode("utf-8"))
    return f'"{sys.executable}" "{shim.as_posix()}"'


def _fill_github(block: str, run_dir: Path, fetch: str) -> str:
    return (block.replace("{run_dir}", run_dir.as_posix()).replace("{owner}/{repo}", "o/r")
            .replace("{analysis_ref}", "main").replace("uv run {githubFetchHelper}", fetch))


def _json_objects(text: str) -> list:
    """Every JSON value a block printed, in order (a helper line or an indented object each)."""
    decoder, values, at = json.JSONDecoder(), [], 0
    while text[at:].strip():
        value, end = decoder.raw_decode(text, at + len(text[at:]) - len(text[at:].lstrip()))
        values.append(value)
        at = end
    return values


# --------------------------------------------------------------------------
# The run folder
# --------------------------------------------------------------------------


@needs_bash
def test_step_one_creates_the_run_folder(tmp_path):
    section = _section(_read(GATHER_INTENT), "### 1. Discover Forge Tier")
    [block] = _blocks(section, "mktemp -d")
    forge = tmp_path / "forge-data"
    block = block.replace("{forge_data_folder}", forge.as_posix()).replace("{project-root}", tmp_path.as_posix())
    proc = _bash(block)
    assert proc.returncode == 0, proc.stderr
    run_dir = Path(proc.stdout.strip())
    assert run_dir.is_dir() and run_dir.parent == tmp_path / "_bmad-output" / ".skf-run"
    assert run_dir.name.startswith("skf-brief-skill-")
    assert forge.is_dir() and not (forge / ".skf-write-probe").exists()
    assert "Bind `{run_dir}` ← the path the last command prints." in section


@needs_bash
def test_the_run_folder_is_removed_once_the_brief_is_written(tmp_path):
    """write-brief.md and the [auto] approve path remove the run folder, and only it."""
    [first] = _blocks(_section(_read(WRITE_BRIEF), "### 7. Chain to Health Check"), "rm -rf")
    [second] = _blocks(_section(_read(AUTO_VALIDATE), "### 3. Envelope, Hook and Chain"), "rm -rf")
    assert first == second
    root = tmp_path / "_bmad-output" / ".skf-run"
    run_dir = root / "skf-brief-skill-abc12345"
    (run_dir / "files").mkdir(parents=True)
    other = tmp_path / "keep"
    other.mkdir()
    for target in (other, run_dir):
        proc = _bash(first.replace("{run_dir}", target.as_posix()).replace("{project-root}", tmp_path.as_posix()))
        assert proc.returncode == 0, proc.stderr
    assert other.is_dir() and not run_dir.exists()


CANCEL_FILES = (GATHER_INTENT, RATIFY, SCOPE_DEFINITION, REFERENCES / "confirm-brief.md")


def test_every_cancel_removes_the_run_folder_before_it_stops():
    """An [X] cancel ends the run: it removes the run folder with step 5's guarded command, and claims no longer
    that nothing was written (step 1 created the folder, and a draft may be saved)."""
    [removal] = _blocks(_section(_read(WRITE_BRIEF), "### 7. Chain to Health Check"), "rm -rf")
    command = f"`{removal.strip()}`"
    sites = 0
    for path in CANCEL_FILES:
        for line in _read(path).splitlines():
            if '`halt_reason: "user-cancelled"`' in line:
                sites += 1
                assert command in line and line.index(command) < line.index("HALT"), f"{path.name}: {line[:80]}"
                assert "non-destructive" not in line.lower() and "no files have been written" not in line
    # step 1 §3.1 and §8, the ratify menu's [X], step 4 §5 (step 3 has no menu of its own: #599)
    assert sites == 4, sites


def test_no_brief_step_types_a_payload_into_an_echo():
    for path in sorted(SKILL_DIR.rglob("*.md")):
        assert "echo '" not in _read(path), path.name


@pytest.mark.parametrize("path", [
    pytest.param(HEADLESS_ARGS, id="headless-args"),
    pytest.param(AUTO_BRIEF, id="step-auto-brief"),
    pytest.param(WRITE_BRIEF, id="write-brief"),
    pytest.param(QMD_REGISTRATION, id="qmd-collection-registration"),
    pytest.param(DRAFT_CHECKPOINT, id="draft-checkpoint"),
])
def test_staged_payloads_are_quoted_heredocs_a_helper_reads(path):
    """A payload is written to the run folder through a quoted, unindented heredoc, then a helper reads the file:
    redirected into it (its output may go to another file of the run folder) or named by a --*-file flag."""
    text = _read(path)
    staged = STAGE_RE.findall(text)
    assert staged, path.name
    for name in staged:
        assert f'\nSKF_JSON\n' in text
        staged_file = rf'"\{{run_dir\}}/{re.escape(name)}"'
        assert re.search(rf'^uv run \{{[A-Za-z]+\}} [^\n]*(?:< |--[a-z-]+-file ){staged_file}'
                         rf'(?: > "\{{run_dir\}}/[a-z-]+\.json")?$', text, re.M), name
    # the heredoc's reason is stated once, where step 1 creates the run folder
    assert "needs no escaping" not in text or path == GATHER_INTENT, path.name


def test_every_heredoc_delimiter_starts_its_line():
    """A heredoc ends only at a delimiter line with no indent, so no documented heredoc sits in an indented block."""
    for path in sorted(REFERENCES.glob("*.md")):
        text = _read(path)
        for match in re.finditer(r"<<'([A-Z_]+)'", text):
            assert re.search(rf"^{match.group(1)}$", text[match.end():], re.M), f"{path.name}: {match.group(1)}"


# --------------------------------------------------------------------------
# Step 2 lists the repository once, through the probe
# --------------------------------------------------------------------------


def test_step_two_lists_the_repository_through_the_probe():
    """The listing goes to the run folder through --out, and the step branches on the line the probe prints,
    which holds every field but the paths, so no listing of any size is read into the conversation."""
    section = _section(_read(ANALYZE_TARGET), "### 1. Resolve Target Location")
    [call] = [line for line in section.splitlines() if line.startswith("uv run {githubProbeHelper} tree")]
    assert call == ('uv run {githubProbeHelper} tree --repo "{owner}/{repo}" --ref "{analysis_ref}" '
                    '--out "{run_dir}/tree.json"')
    assert "--out" in _run("skf-github-probe.py", "tree", "--help").stdout
    assert "Branch on that line." in section and "Read the fields" not in section
    assert "gh auth status" not in section and "git/trees" not in section and "git/refs/tags" not in section
    assert "base64" not in _read(ANALYZE_TARGET) and "base64" not in _read(VERSION_RESOLUTION)
    assert "`truncated`" in section
    # a missing probe halts with an envelope like any listing failure
    [missing] = [line for line in section.splitlines() if line.startswith("- **No candidate path, or no JSON**")]
    assert '`halt_reason: "target-inaccessible"`' in missing
    # every cause the probe reports is classified
    causes = re.search(r"^CAUSES = \(([^)]*)\)", _read(SCRIPTS / "skf-github-probe.py"), re.M).group(1)
    for cause in re.findall(r'"([a-z-]+)"', causes):
        assert f"`{cause}`" in section, cause
    for line in section.splitlines():
        if "`gh-missing` or `gh-unauthenticated`" in line:
            assert '`halt_reason: "gh-auth-failed"`' in line
        if "`repo-not-found`, `no-access` or `ref-not-found`" in line:
            assert '`halt_reason: "target-inaccessible"`' in line


def test_a_target_version_resolves_to_a_tag_through_validate_pins():
    text = _read(ANALYZE_TARGET)
    [call] = [line.strip() for line in text.splitlines() if line.strip().startswith("uv run {validatePinsHelper}")]
    assert '--pin "{target_version}"' in call and "--format tag" in call
    proc = _run("skf-validate-pins.py", "--help")
    for flag in re.findall(r"(--[a-z-]+)", call):
        assert flag in proc.stdout, flag
    # the ratify rule resolves its implicit version the same way, not by a prose tag match
    rules = _section(text, "## Rules")
    assert "it matches the tag" not in rules and "resolves it to a tag the same way" in rules
    assert "skf-validate-pins.py" in _read(VERSION_RESOLUTION)
    # an exit 1 with no suggestions may be a listing that failed, so its warning claims no missing tag
    [empty] = [line for line in text.splitlines() if "Exit 1 with an empty `suggestions`" in line]
    assert "Could not find or list the tags" in empty
    # the latest release of a JavaScript source is still read from the releases API, which knows when there is none
    [js] = [line for line in _read(VERSION_RESOLUTION).splitlines() if line.startswith("- **JavaScript")]
    assert "releases/latest" in js and "validatePinsHelper" not in js


def _git(*args: str, cwd: Path) -> str:
    """Run git without the user's configuration (a signing or hook setting would break the fixture's commits)."""
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
           "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run([GIT, *args], cwd=cwd, capture_output=True, text=True, check=True, env=env).stdout


@pytest.mark.skipif(not POSIX_BASH or GIT is None, reason="runs the documented listing in a POSIX bash with git")
def test_a_local_listing_leaves_out_the_run_folders(tmp_path):
    """Listing the project root itself, through git or find, never lists the run folder the listing is written to."""
    section = _section(_read(ANALYZE_TARGET), "### 1. Resolve Target Location")
    [git_listing] = _blocks(section, "ls-files")
    [find_listing] = re.findall(r'`(\(cd "\{source_path\}" && find [^`]*)`', section)
    for listing, in_git in ((git_listing, True), (find_listing, False)):
        project = _write_tree(tmp_path / f"project-{in_git}", {"src/a.ts": "export const a = 1;\n",
                                                                "_bmad-output/notes.md": "notes\n"})
        if in_git:
            _git("init", "-q", cwd=project)
        run_dir = project / "_bmad-output" / ".skf-run" / "skf-brief-skill-abc12345"
        _write_tree(run_dir, {"files/package.json": "{}\n"})
        proc = _bash(listing.replace("{source_path}", project.as_posix()).replace("{run_dir}", run_dir.as_posix()))
        assert proc.returncode == 0, proc.stderr
        listed = (run_dir / "tree.json").read_text(encoding="utf-8").splitlines()
        assert sorted(line.removeprefix("./") for line in listed) == ["_bmad-output/notes.md", "src/a.ts"], listing


@pytest.mark.skipif(not POSIX_BASH or GIT is None, reason="runs the documented clone in a POSIX bash with git")
def test_the_clone_reaches_a_tag_a_commit_and_a_sparse_subset(tmp_path):
    """Step 2's [L] clone checks out a tag or a commit SHA, and step 3's sparse form holds only the scope's folders."""
    section = _section(_read(ANALYZE_TARGET), "### 1. Resolve Target Location")
    [tag_clone] = _blocks(section, "git clone")
    sha_clone, sha_checkout = re.findall(r'`(git (?:clone --filter|-C "\{run_dir\}/clone" checkout)[^`]*)`', section)
    assert "{source_path}` ← `{run_dir}/clone`" in section and 'rm -rf "{run_dir}/clone"' in section
    origin = _write_tree(tmp_path / "origin", {"package.json": "{}\n", "packages/foo/src/a.ts": "export const a = 1;\n",
                                               "packages/bar/src/b.ts": "export const b = 1;\n"})
    _git("init", "-q", "-b", "main", cwd=origin)
    _git("add", "-A", cwd=origin)
    _git("commit", "-qm", "one", cwd=origin)
    _git("tag", "v1.0.0", cwd=origin)
    first = _git("rev-parse", "HEAD", cwd=origin).strip()
    _write_tree(origin, {"packages/foo/src/a.ts": "export const a = 2;\n"})
    _git("commit", "-qam", "two", cwd=origin)

    def run(commands: str, run_dir: Path, ref: str) -> Path:
        run_dir.mkdir()
        script = (commands.replace('"https://github.com/{owner}/{repo}.git"', f'"{origin.as_uri()}"')
                  .replace("{run_dir}", run_dir.as_posix()).replace("{analysis_ref}", ref))
        proc = _bash(script)
        assert proc.returncode == 0, proc.stderr
        return run_dir / "clone"

    tag = run(tag_clone, tmp_path / "tag", "v1.0.0")
    assert (tag / "packages" / "foo" / "src" / "a.ts").read_bytes() == b"export const a = 1;\n"
    sha = run(f"{sha_clone}\n{sha_checkout}\n", tmp_path / "sha", first)
    assert (sha / "packages" / "foo" / "src" / "a.ts").read_bytes() == b"export const a = 1;\n"
    # scope-definition §3c: the same clone with --sparse added, then only the folders the globs name
    tier_a = _section(_read(SCOPE_DEFINITION), "### 3c. Tier-A Authoring Surface (coarse-glob monorepo subsets)")
    [sparse_set] = re.findall(r'`(git -C "\{run_dir\}/clone" sparse-checkout set [^`]*)`', tier_a)
    assert "`--sparse` added" in tier_a
    sparse = run(tag_clone.replace("git clone ", "git clone --sparse --filter=blob:none ", 1) + "\n"
                 + sparse_set.replace('"<folder>"', '"packages/foo/src"') + "\n", tmp_path / "sparse", "v1.0.0")
    assert (sparse / "packages" / "foo" / "src" / "a.ts").is_file() and (sparse / "package.json").is_file()
    assert not (sparse / "packages" / "bar").exists()


@needs_bash
def test_a_rush_tree_reaches_the_workspace_menu(tmp_path):
    """§1b fetches the root manifests the listing names, rush.json included, and the detector finds the projects."""
    section = _section(_read(ANALYZE_TARGET), "### 1b. Detect Monorepo / Workspace Layout")
    assert "`rush.json`" in section and "Nx needs only the tree" in section
    [block] = _blocks(section, "--manifest-files")
    files = {
        "package.json": '{"name": "root", "private": true}\n',
        "rush.json": ('// Rush\n{"projects": [{"packageName": "@acme/web", "projectFolder": "apps/web"},\n'
                      ' {"packageName": "@acme/core", "projectFolder": "libraries/core"}]}\n'),
        "apps/web/package.json": '{"name": "@acme/web"}\n',
        "apps/web/src/index.ts": "export const web = 1;\n",
        "libraries/core/package.json": '{"name": "@acme/core"}\n',
        "libraries/core/src/index.ts": "export const core = 1;\n",
    }
    repo = _write_tree(tmp_path / "repo", files)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "tree.json").write_bytes(_probe_listing(sorted(files)).encode("utf-8"))
    block = (_fill_github(block, run_dir, _fetch_shim(tmp_path, repo))
             .replace("uv run {detectWorkspacesHelper}", _script("skf-detect-workspaces.py")))
    proc = _bash(block)
    assert proc.returncode == 0, proc.stderr
    fetched, out = _json_objects(proc.stdout)
    assert fetched["status"] == "ok" and fetched["via"] == "raw" and "rush.json" in fetched["fetched"], fetched
    assert out["is_monorepo"] is True and out["manifest_kind"] == "rush", out
    assert [w["name"] for w in out["workspaces"]] == ["@acme/web", "@acme/core"]
    assert (run_dir / "files" / "rush.json").read_bytes() == files["rush.json"].encode("utf-8")
    # §2's snapshot reads the same listing and manifests
    [snapshot] = _blocks(_section(_read(ANALYZE_TARGET), "### 2. Read Repository Structure"), "--snapshot")
    snapshot = (snapshot.replace('<§1b\'s manifest folder>', (run_dir / "files").as_posix())
                .replace("{run_dir}", run_dir.as_posix())
                .replace("uv run {detectWorkspacesHelper}", _script("skf-detect-workspaces.py")))
    proc = _bash(snapshot)
    assert proc.returncode == 0, proc.stderr
    facts = json.loads((run_dir / "snapshot.json").read_text(encoding="utf-8"))
    assert facts["file_count"] == len(files) and facts["manifest_kind"] == "rush"
    assert facts["top_level_files"] == ["package.json", "rush.json"]


def test_js_family_workspace_kinds_carry_no_language_override():
    section = _section(_read(ANALYZE_TARGET), "### 3. Detect Primary Language")
    [line] = [line for line in section.splitlines() if "JS-family workspace kinds" in line]
    assert "(`npm-workspaces`/`pnpm-workspaces`/`lerna`/`rush`/`nx`)" in line


@needs_bash
def test_a_tree_of_more_than_10000_files_reaches_the_language_detector_whole(tmp_path):
    """The detector reads the staged listing, so the one manifest that decides, listed last, is seen."""
    section = _section(_read(ANALYZE_TARGET), "### 3. Detect Primary Language")
    [block] = _blocks(section, "{detectLanguageHelper}")
    block = re.sub(r" \[--workspace-signal [^\]]*\]", "", block)  # §1b found no workspace
    paths = [f"src/mod{i // 100}/file{i}.rs" for i in range(12_000)] + ["Cargo.toml"]
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "tree.json").write_bytes(_probe_listing(paths).encode("utf-8"))
    block = block.replace("{run_dir}", run_dir.as_posix()).replace("uv run {detectLanguageHelper}",
                                                                   _script("skf-detect-language.py"))
    proc = _bash(block)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["language"] == "rust" and out["detection_source"] == "Cargo.toml present"


@needs_bash
def test_step_two_finds_the_entry_files_and_follows_their_re_exports(tmp_path):
    """§4.1 on a public repository read without gh: the extractor picks the entry file from package.json (a build
    output mapped back to its source), the fetch stages it raw, the extractor's --follow fetches and reads the
    module an `export *` names, and step 3 counts the exports from the result, apostrophes and all. A module the
    fetch cannot read stays a warning: the exports read before it are kept (no round is run by hand)."""
    section = _section(_read(ANALYZE_TARGET), "#### 4.1 Procedure")
    [find] = _blocks(section, "--mode entries")
    [parse] = _blocks(section, "--mode quick")
    assert "never pick an entry file yourself" in section
    assert "follow.txt" not in section and "--follow-file" not in section and "rounds" not in section
    files = {
        "package.json": '{"name": "demo", "version": "2.1.0", "main": "dist/index.js", "dependencies": {"zod": "3"}}\n',
        "src/index.ts": ("// it's the entry point; don't break on the quote\nexport * from './greet';\n"
                         "export * from './private';\nexport const greeting = \"it's here\";\n"),
        "src/greet.ts": "export function hello(name: string): string { return `hi ${name}'s`; }\n",
        "README.md": "# demo\n",
    }
    repo = _write_tree(tmp_path / "repo", files)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    # src/private.ts is listed, but the raw read answers 404 for it and there is no gh
    (run_dir / "tree.json").write_bytes(_probe_listing(sorted([*files, "src/private.ts"])).encode("utf-8"))
    fetch, extract, staged = _fetch_shim(tmp_path, repo), _extract_shim(tmp_path, repo), run_dir / "files"

    def run(block: str) -> None:
        block = (_fill_github(re.sub(r' \[--scope "\{monorepo_workspace\}"\]', "", block), run_dir, fetch)
                 .replace("uv run {extractPublicApiHelper}", extract)
                 .replace("<language>", "typescript").replace("<source root>", staged.as_posix()))
        block = re.sub(r" \[(--repo [^\]]*)\]", r" \1", block)  # a GitHub source passes --repo and --ref
        assert not re.findall(r"\{[A-Za-z_]+\}|<[a-z ]+>|\[--", block), block
        proc = _bash(block)
        assert proc.returncode == 0, proc.stderr

    run(find)
    entries = json.loads((run_dir / "entries.json").read_text(encoding="utf-8"))
    assert (entries["manifest"], entries["entry_files"]) == ("package.json", ["src/index.ts"])
    assert sorted(p.relative_to(staged).as_posix() for p in staged.rglob("*") if p.is_file()) == \
        ["package.json", "src/index.ts"]
    run(parse.replace("<manifest path>", "package.json").replace("<entry path>", "src/index.ts"))
    out = json.loads((run_dir / "extract.json").read_text(encoding="utf-8"))
    assert (out["package_name"], out["version"]) == ("demo", "2.1.0")
    assert sorted(e["name"] for e in out["exports"]) == ["greeting", "hello"]
    assert out["followed"] == ["src/greet.ts"] and (staged / "src" / "greet.ts").is_file()
    assert [r["module_file"] for r in out["unlisted"]] == ["src/private.ts"]
    assert any(w.startswith("--follow could not read src/private.ts") and "gh is not installed" in w
               for w in out["warnings"])
    # step 3 takes the count from the file, never from a number typed into its payload
    body = {"signals": {"wants_wiring_pattern": False, "named_module_subset": [], "wants_narrow_api": True},
            "module_count": 1, "mode": "interactive"}
    proc = _run("skf-recommend-scope-type.py", "--tree-file", str(run_dir / "tree.json"),
                "--extract-file", str(run_dir / "extract.json"), stdin=json.dumps(body))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["signals"] == {"wants_narrow_api": True, "export_count": 2}


@needs_bash
def test_the_fallback_path_stages_an_extraction_with_no_export(tmp_path):
    """§4.2 writes over extract.json (a failed extractor run may have left it empty), so step 3 always passes
    --extract-file, and an entries call that found nothing to parse goes there instead of an extractor call
    with no file."""
    text = _read(ANALYZE_TARGET)
    fallback = _section(text, "#### 4.2 Procedure")
    [stage] = re.findall(r"`(printf [^`]*extract\.json\")`", fallback)
    assert ("When the entries call exits non-zero, or it names neither a manifest nor an entry file, there is "
            "nothing to parse: skip the rest of §4.1 and take §4.2.") in _section(text, "#### 4.1 Procedure")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "extract.json").write_bytes(b"")
    proc = _bash(stage.replace("{run_dir}", run_dir.as_posix()))
    assert proc.returncode == 0, proc.stderr
    (run_dir / "tree.json").write_bytes(_probe_listing(["Gemfile", "lib/demo.rb"]).encode("utf-8"))
    body = {"signals": {"wants_wiring_pattern": False, "named_module_subset": [], "wants_narrow_api": True},
            "module_count": 1, "mode": "interactive"}
    proc = _run("skf-recommend-scope-type.py", "--tree-file", str(run_dir / "tree.json"),
                "--extract-file", str(run_dir / "extract.json"), stdin=json.dumps(body))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["scope_type"] != "public-api", "no count, so the public-api rule does not fire"


def test_a_public_repository_is_read_without_gh():
    """Every file steps 2 and 3 read from GitHub comes through skf-github-fetch.py, which needs gh only for a
    private repository, so a public repository the probe listed without gh goes on (no halt, no warning)."""
    for path in sorted(REFERENCES.glob("*.md")):
        text = _read(path)
        assert "gh api -H" not in text and "/contents/" not in text, path.name
    prefix = ('uv run {githubFetchHelper} --repo "{owner}/{repo}" --ref "{analysis_ref}" '
              '--tree-file "{run_dir}/tree.json" --dest "{run_dir}/files" ')
    calls = []
    for path in (ANALYZE_TARGET, SCOPE_DEFINITION):
        text = _read(path)
        assert "githubFetchProbeOrder:" in text.split("\n---\n", 1)[0], path.name
        calls += [line.strip() for block in _blocks(text, "{githubFetchHelper}") for line in block.splitlines()
                  if "{githubFetchHelper}" in line]
    assert len(calls) == 5 and all(call.startswith(prefix) for call in calls), calls
    assert f'`{prefix}"{{file}}"`' in _read(VERSION_RESOLUTION)
    listing = _section(_read(ANALYZE_TARGET), "### 1. Resolve Target Location")
    assert '`status: "ok"` with `gh`' not in listing and "**Fetching files.**" in listing
    assert "which needs no `gh`, and through `gh` only when that fails (a private repository)" in listing
    probe = _section(_read(GATHER_INTENT), "#### 3.3 Branch")
    assert "will HALT" not in probe and "a public one read without `gh` included" in probe


def test_modules_and_structure_come_from_the_snapshot():
    text = _read(ANALYZE_TARGET)
    picks = _section(text, "#### 4.3 Output format (both paths)")
    for needle in ("`workspaces`", "`module_candidates`", "`source_file_count`", '--snapshot --root "<that folder>"',
                   "`module_count`"):
        assert needle in picks, needle
    summary = _section(text, "### 5. Report Analysis Summary")
    for needle in ("{file_count}", "{dir_count}", "{module_count}", "`top_level_files`", "`top_level_dirs`"):
        assert needle in summary, needle
    payload = _section(_read(SCOPE_DEFINITION), "### 2c. Offer Scope Templates")
    assert '"module_count": <module_count from step 2 §4.3>' in payload


# --------------------------------------------------------------------------
# A docs-only target (#603)
# --------------------------------------------------------------------------


def test_a_docs_only_target_skips_the_repository_analysis():
    text = _read(ANALYZE_TARGET)
    assert text.index("\n### 0. Docs-Only Target\n") < text.index("\n### 1. Resolve Target Location\n")
    section = _section(text, "### 0. Docs-Only Target")
    assert "skip §1 to §5" in section and "`documentation`" in section and "`language_hint`" in section
    assert "`1.0.0` default" in section and "execute {nextStepFile}" in section
    scope = _read(SCOPE_DEFINITION)
    assert "`documentation` for a docs-only target" in _section(scope, "### 1. Present Scope Context")
    docs_only = _section(scope, "### 2. Handle Docs-Only Mode (if applicable)")
    assert "- `language`: step 2 §0's `{language}` (`documentation`" in docs_only


def test_a_docs_only_derive_run_writes_its_brief_with_the_documentation_language(tmp_path):
    """The flat payload step 5 builds for a docs-only derive run, with step 2's language, is one the writer takes."""
    section = _section(_read(ANALYZE_TARGET), "### 0. Docs-Only Target")
    language = re.search(r"else `([a-z]+)`", section).group(1)
    context = {
        "name": "stripe-api", "target_version": None, "detected_version": None, "source_type": "docs-only",
        "source_repo": "https://docs.stripe.com/api", "language": language,
        "description": "Stripe's REST API, from its docs. Use when an agent calls Stripe.", "forge_tier": "Quick",
        "created": "2026-10-01", "created_by": "demo", "scope_type": "docs-only",
        "scope_include": ["https://docs.stripe.com/api"], "scope_exclude": [],
        "scope_notes": "Generated from external documentation. All content is T3 confidence.",
        "scope_rationale": None, "scope_tier_a_include": None, "scope_amendments": None,
        "doc_urls": [{"url": "https://docs.stripe.com/api", "label": "API Reference"}], "scripts_intent": None,
        "assets_intent": None, "source_authority": "community", "target_ref": None, "source_ref": None,
    }
    target = tmp_path / "forge" / "stripe-api" / "skill-brief.yaml"
    proc = _run("skf-write-skill-brief.py", "write", "--target", str(target), "--from-flat", stdin=json.dumps(context))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["version"] == "1.0.0"
    check = _run("skf-validate-brief-schema.py", str(target))
    result = json.loads(check.stdout)
    assert result["valid"] is True, result["errors"]
    assert result["brief"]["language"] == "documentation" and result["brief"]["scope"]["type"] == "docs-only"


# --------------------------------------------------------------------------
# Payloads staged for the validators and the writers
# --------------------------------------------------------------------------


@needs_bash
def test_headless_arguments_reach_the_validator_from_a_staged_file(tmp_path):
    section = _section(_read(HEADLESS_ARGS), "### 2. Validate the Arguments")
    [block] = _blocks(section, "{validateBriefInputsHelper}")
    args = {"target_repo": "https://github.com/o/r", "skill_name": "demo",
            "intent": "Skill the client's retry API; it's what agents call", "scope_hint": "the `retry` module"}
    block = (block.replace("<the merged headless arguments, as one JSON object>", json.dumps(args))
             .replace("{run_dir}", tmp_path.as_posix())
             .replace("uv run {validateBriefInputsHelper}", _script("skf-validate-brief-inputs.py")))
    proc = _bash(block)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["valid"] is True and out["normalized"]["intent"] == args["intent"]


def _flat_payload_keys(section: str) -> set[str]:
    """The keys of the flat payload template step 5 §3 shows a derive run."""
    start = section.index("```json\n") + len("```json\n")
    return set(re.findall(r'^  "([a-z_]+)":', section[start:section.index("```", start)], re.M))


@needs_bash
def test_the_step_five_payload_reaches_the_writer_with_its_apostrophes(tmp_path):
    section = _section(_read(WRITE_BRIEF), "### 3. Write the Brief")
    # Step 5b gate run 3: a ratify run has a writer call of its own (--base-brief), so this is the derive block.
    [block] = _blocks(section, "--from-flat")
    assert "{writeSkillBriefHelper}" in block
    context = {
        "name": "demo", "target_version": None, "detected_version": "1.4.0", "source_type": "source",
        "source_repo": "https://github.com/o/r", "language": "typescript",
        "description": "The client's retry API. Use when an agent's call fails and it's worth retrying.",
        "forge_tier": "Forge", "created": "2026-10-01", "created_by": "demo", "scope_type": "public-api",
        "scope_include": ["src/**"], "scope_exclude": [], "scope_notes": "It's the `retry` module's surface.",
        "scope_rationale": None, "scope_tier_a_include": None,
        "scope_registry_path": None, "scope_ui_variants": None, "scope_demo_patterns": None, "doc_urls": None,
        "scripts_intent": None, "assets_intent": None, "source_authority": None, "target_ref": None,
    }
    # The context holds every key the template names; a derive run sets no source_ref and no amendments log.
    assert set(context) == _flat_payload_keys(section)
    target = tmp_path / "forge" / "demo" / "skill-brief.yaml"
    block = (block.replace("<the brief context above, as one JSON object>", json.dumps(context))
             .replace("{run_dir}", tmp_path.as_posix()).replace("{resolved-target-path}", target.as_posix())
             .replace("uv run {writeSkillBriefHelper}", _script("skf-write-skill-brief.py")))
    proc = _bash(block)
    assert proc.returncode == 0, proc.stderr
    brief = json.loads(_run("skf-validate-brief-schema.py", str(target)).stdout)["brief"]
    assert brief["description"] == context["description"] and brief["scope"]["notes"] == context["scope_notes"]
    assert brief["version"] == "1.4.0"


@needs_bash
def test_a_ratify_run_skips_the_overwrite_gate_only_for_the_brief_it_read(tmp_path):
    """Step 5 writes a ratified brief to the forge path: with no gate only when that is the file step 1 read
    (through any path or link); a brief read elsewhere, or renamed at step 4, meets the derive route's gates.
    Both paths reach the check through a quoted heredoc, so a `$`, a quote or a backtick in one is read as is."""
    section = _section(_read(WRITE_BRIEF), "### 2b. Existing Brief")
    [check] = _blocks(section, "<<'SKF_PATHS'")
    odd = "brie$fs `x` \"it's\""
    _write_tree(tmp_path, {"forge/demo/skill-brief.yaml": "name: demo\n", "briefs/skill-brief.yaml": "name: demo\n",
                           f"{odd}/skill-brief.yaml": "name: demo\n"})
    target, elsewhere = tmp_path / "forge" / "demo" / "skill-brief.yaml", tmp_path / "briefs" / "skill-brief.yaml"
    (tmp_path / "link").symlink_to(target.parent, target_is_directory=True)
    (tmp_path / odd / "same.yaml").symlink_to(target)
    check = check.replace("uv run python", f'"{sys.executable}"')

    def same(source: str, dest: Path = target) -> str:
        proc = _bash(check.replace("{resolved-target-path}", dest.as_posix()).replace("{ratify_source_path}", source),
                     cwd=tmp_path)
        assert proc.returncode == 0, proc.stderr
        return proc.stdout.strip()

    assert same(target.as_posix()) == "same"
    assert same("forge/demo/skill-brief.yaml") == "same", "a path relative to the working folder"
    assert same((tmp_path / "link" / "skill-brief.yaml").as_posix()) == "same", "a path through a link"
    assert same((tmp_path / odd / "same.yaml").as_posix()) == "same", "a path holding $, quotes and backticks"
    assert same((tmp_path / odd / "skill-brief.yaml").as_posix()) == "different"
    assert same((tmp_path / "missing.yaml").as_posix()) == "different", "a source that no longer exists"
    assert same(elsewhere.as_posix()) == "different"
    assert same(target.as_posix(), tmp_path / "forge" / "renamed" / "skill-brief.yaml") == "different"
    for gate in ("**Interactive (`{headless_mode}` is false), unless the ratify check printed `same`:**",
                 "headless (`{headless_mode}` is true), unless the ratify check printed `same`:"):
        assert gate in section, gate
    assert "takes precedence over both" not in section and "auto-overwrites the brief in place" not in section
    # the promise names the forge path, and force for another brief already there
    for path in (SKILL_MD, RATIFY, INVOCATION_CONTRACT, HEADLESS_ARGS):
        text = _read(path)
        for stale in ("rewritten in place", "writer in place", "write in place", "overwriting this file"):
            assert stale not in text, (path.name, stale)
    for path in (SKILL_MD, RATIFY):
        assert "(in place when it already lives there)" in _read(path), path.name
    for path in (RATIFY, INVOCATION_CONTRACT, HEADLESS_ARGS):
        assert "otherwise `force` applies as on the derive route" in _read(path), path.name


def _upstream_brief(tmp_path: Path) -> dict:
    """A brief carrying every field the writer renders, as skf-validate-brief-schema.py parses it."""
    brief = {
        "name": "demo", "version": "1.2.3", "source_type": "source", "source_repo": "https://github.com/o/r",
        "language": "typescript", "description": "Demo's components. Use when it's a UI task.",
        "forge_tier": "Forge", "created": "2026-09-30", "created_by": "an",
        "scope": {
            "type": "component-library", "include": ["packages/ui/src/**"], "exclude": ["**/*.test.*"],
            "tier_a_include": ["packages/ui/src/button.tsx"], "notes": "AN's notes: this skill's surface.",
            "rationale": {"recommended": "full-library", "chosen": "component-library",
                          "accepted_recommendation": False, "heuristic": "component-registry",
                          "reason": "a registry", "recorded": "2026-09-30"},
            "amendments": [{"path": "docs/x.md", "action": "added", "reason": "auth doc", "date": "2026-09-30",
                            "workflow": "skf-create-skill"}],
            "registry_path": "packages/ui/registry.ts", "ui_variants": [{"name": "base", "package": "packages/ui"}],
            "demo_patterns": ["**/demo/**"],
        },
        "target_version": "1.2.3", "target_ref": "v1.2.3", "source_ref": "v1.2.3",
        "doc_urls": [{"url": "https://demo.dev/docs/", "label": "Docs", "source": "homepage"}],
        "scripts_intent": "none", "assets_intent": "the JSON schemas under schemas/", "source_authority": "official",
    }
    path = tmp_path / "upstream" / "skill-brief.yaml"
    path.parent.mkdir(parents=True)
    path.write_bytes(json.dumps(brief).encode("utf-8"))  # JSON is YAML
    result = json.loads(_run("skf-validate-brief-schema.py", str(path)).stdout)
    assert result["valid"] is True, result["errors"]
    return result["brief"]


def _helper_call(block: str, helper: str, script: str, values: dict[str, str]) -> list[str]:
    """The argv of the documented `uv run {helper} ...` line of `block`, its placeholders filled from `values`."""
    [line] = [line for line in block.splitlines() if line.startswith(f"uv run {{{helper}}} ")]
    for placeholder, value in values.items():
        line = line.replace(placeholder, value)
    assert not re.search(r"\{[a-z_]+\}", line), line
    return [sys.executable, str(SCRIPTS / script), *shlex.split(line)[3:]]


def test_the_auto_path_hands_every_upstream_field_back_to_the_writer(tmp_path):
    """step-auto-brief writes from the upstream brief file itself, so no field AN wrote is rebuilt or dropped."""
    text = _read(AUTO_BRIEF)
    keep = [line for line in text.splitlines() if line.startswith("Nothing the upstream brief carries is rebuilt")]
    assert len(keep) == 1
    for field in ("scope.rationale", "scope.amendments", "scope.tier_a_include", "scope.registry_path",
                  "scope.ui_variants", "scope.demo_patterns"):
        assert f"`{field}`" in keep[0], field
    assert '"scope_rationale":  null' not in text and "auto-brief.json" not in text
    [write] = _blocks(_section(text, "### 4. Write Enriched Brief"), "{writeSkillBriefHelper}")
    assert '--base-brief "{brief_path}"' in write and "--from-flat" not in write

    upstream = _upstream_brief(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    # §3: the merge input, staged as the documented heredoc names its keys, and the helper's output kept in a file
    [merge] = _blocks(_section(text, "### 3. Enrich Brief with Detected Docs"), "{mergeDocUrlsHelper}")
    template = HEREDOC_RE.search(merge).group("body")
    detected = [{"url": "https://demo.dev/docs/index.html", "label": "README Link", "source": "readme-detection"},
                {"url": "https://demo.dev/api", "label": "API's reference", "source": "homepage"}]
    staged = (template.replace('"<scope_type>"', json.dumps(upstream["scope"]["type"]))
              .replace("<the upstream brief's doc_urls, [] if none>", json.dumps(upstream["doc_urls"]))
              .replace("<the mapped detected entries>", json.dumps(detected)))
    assert merge.rstrip().endswith('> "{run_dir}/doc-urls-merged.json"')
    proc = _run("skf-merge-doc-urls.py", stdin=staged)
    assert proc.returncode == 0, proc.stderr
    (run_dir / "doc-urls-merged.json").write_bytes(proc.stdout.encode("utf-8"))
    merged = json.loads(proc.stdout)["doc_urls"]
    # §4: the documented writer call, on the upstream brief file and the merged list
    target = tmp_path / "forge" / "demo" / "skill-brief.yaml"
    brief_path = tmp_path / "upstream" / "skill-brief.yaml"
    argv = _helper_call(write, "writeSkillBriefHelper", "skf-write-skill-brief.py", {
        "{forge_data_folder}/{skill_name}/skill-brief.yaml": target.as_posix(), "{brief_path}": brief_path.as_posix(),
        "{run_dir}": run_dir.as_posix()})
    proc = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", timeout=120, check=False)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["version"] == upstream["version"]
    written = json.loads(_run("skf-validate-brief-schema.py", str(target)).stdout)["brief"]
    assert written["doc_urls"] == merged and len(merged) == 2
    assert {k: v for k, v in written.items() if k != "doc_urls"} == \
        {k: v for k, v in upstream.items() if k != "doc_urls"}


# The fields step 4 or a step 3 [R] pass can change: the ratify patch names each, and no other.
RATIFY_PATCH_FIELDS = {
    "name", "description", "language", "scripts_intent", "assets_intent", "doc_urls", "scope.type", "scope.include",
    "scope.exclude", "scope.notes", "scope.rationale", "scope.tier_a_include", "scope.registry_path",
    "scope.ui_variants", "scope.demo_patterns",
}
COMPONENT_FIELDS = ("registry_path", "ui_variants", "demo_patterns")


def _value(context: dict, dotted: str):
    for part in dotted.split("."):
        context = context.get(part) if isinstance(context, dict) else None
    return context


def _ratify_change(name: str, context: dict) -> dict:
    """The run's context after `name`: what step 4 or a step 3 [R] pass changed; returns any step 4 change to a
    field the patch template does not name, which the prose adds to the patch under its brief key."""
    if name == "step-four-description":
        context["description"] = "Demo's buttons and dialogs. Use when it's a UI task in Demo."
    elif name == "revise-off-component-library":
        # scope-definition.md Rules: the pass drops the three fields when the type leaves component-library.
        context["scope"].update(type="public-api", include=["packages/ui/src/index.ts"])
        context["scope"]["rationale"].update(chosen="public-api", reason="the entry point only")
        for field in COMPONENT_FIELDS:
            context["scope"].pop(field)
    elif name == "step-four-version":
        context.update(version="1.3.0", target_version="1.3.0")
        return {"version": "1.3.0", "target_version": "1.3.0"}
    return {}


@needs_bash
@pytest.mark.parametrize("change", [
    pytest.param("none", id="as-ratified"),
    pytest.param("step-four-description", id="step-four-description"),
    pytest.param("revise-off-component-library", id="revise-off-component-library"),
    pytest.param("step-four-version", id="step-four-version"),
])
def test_a_ratify_run_writes_from_the_brief_it_ratified(tmp_path, change):
    """Step 5b gate run 3 (determinism-3): step 5 writes a ratified brief from the file step 1 read, with a patch
    of the fields steps 3 and 4 can change, so the amendments log, the tier-A list, the git refs and the version
    survive though no step retypes them, and the component-library fields go only when an [R] pass drops them."""
    section = _section(_read(WRITE_BRIEF), "### 3. Write the Brief")
    [block] = _blocks(section, "--base-brief")
    template = HEREDOC_RE.search(block).group("body")
    assert set(re.findall(r"<([a-z_.]+)>", template)) == RATIFY_PATCH_FIELDS
    for kept in ('"amendments"', '"version"', '"target_ref"', '"source_ref"', '"created"'):
        assert kept not in template, kept
    upstream = _upstream_brief(tmp_path)
    source = tmp_path / "upstream" / "skill-brief.yaml"
    # gather-intent-ratify.md §3 hydrates the run's context from the parsed brief, field for field.
    context = json.loads(json.dumps(upstream))
    extra = _ratify_change(change, context)
    patch = template
    for dotted in RATIFY_PATCH_FIELDS:
        patch = patch.replace(f"<{dotted}>", json.dumps(_value(context, dotted)))
    patch = json.dumps({**json.loads(patch), **extra})
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    target = tmp_path / "forge" / "demo" / "skill-brief.yaml"
    script = (block.replace(template, patch).replace("{run_dir}", run_dir.as_posix())
              .replace("{resolved-target-path}", target.as_posix())
              .replace("{ratify_source_path}", source.as_posix())
              .replace("uv run {writeSkillBriefHelper}", _script("skf-write-skill-brief.py")))
    proc = _bash(script)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["version"] == context["version"]
    assert "version_resolved" not in target.read_text(encoding="utf-8")
    written = json.loads(_run("skf-validate-brief-schema.py", str(target)).stdout)["brief"]
    assert written == context
    assert written["scope"]["amendments"] == upstream["scope"]["amendments"]
    assert written["scope"]["tier_a_include"] == upstream["scope"]["tier_a_include"]
    assert (written["target_ref"], written["source_ref"]) == (upstream["target_ref"], upstream["source_ref"])
    dropped = change == "revise-off-component-library"
    for field in COMPONENT_FIELDS:
        assert (field in written["scope"]) is not dropped, field


# --------------------------------------------------------------------------
# The target prompt reads the target with parse-target (#582)
# --------------------------------------------------------------------------


def _parse_target_block() -> str:
    [block] = _blocks(_read(GATHER_INTENT), "parse-target")
    return block


def test_the_target_prompt_routes_every_kind_parse_target_returns():
    text = _read(GATHER_INTENT)
    assert "resolvePackageProbeOrder:" in text and "emitBriefEnvelopeProbeOrder" not in text
    routes = text[text.index("Route on the `kind` it returns:"):text.index("#### 3.1a Branch")]
    kinds = re.search(r"^KINDS = \(([^)]*)\)", _read(SCRIPTS / "skf-resolve-package.py"), re.M).group(1)
    for kind in re.findall(r'"([a-z-]+)"', kinds):
        assert f"`{kind}`" in routes, kind
    package = _section(text, "#### 3.1b Branch: Resolve a Package Name")
    assert 'uv run {resolvePackageHelper} resolve "{package_name}" --timeout 10 [--registry {registry}]' in package
    for status in ("`ok`", "`ambiguous`", "`fallthrough`"):
        assert status in package, status


@pytest.mark.parametrize("target,kind,fields", [
    pytest.param("zod", "package", {"package_name": "zod"}, id="package"),
    pytest.param("requests==2.31.0", "package", {"registry": "pypi", "target_version": "2.31.0"}, id="pypi-pin"),
    pytest.param("https://www.npmjs.com/package/zod", "registry-page", {"package_name": "zod"}, id="registry-page"),
    pytest.param("https://github.com/vercel/next.js/tree/canary/packages/next", "github",
                 {"repo": "next.js", "ref": "canary", "subdir": "packages/next"}, id="github-tree"),
    pytest.param("https://gitlab.com/acme/lib", "other-host", {"host": "gitlab.com"}, id="other-host"),
    pytest.param("./vendor/lib", "local-path", {"path": "./vendor/lib"}, id="local-path"),
])
def test_parse_target_sorts_the_documented_targets(target, kind, fields):
    proc = _run("skf-resolve-package.py", "parse-target", stdin=target + "\n")
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["kind"] == kind and {k: out[k] for k in fields} == fields


def _routes() -> str:
    text = _read(GATHER_INTENT)
    return text[text.index("Route on the `kind` it returns:"):text.index("#### 3.1a Branch")]


@pytest.mark.parametrize("target, on_disk, branch", [
    pytest.param("skill-brief.yaml", {"skill-brief.yaml": "name: demo\n"}, "§3.1a", id="a-brief-here"),
    pytest.param("briefs/skill-brief.yaml", {"briefs/skill-brief.yaml": "name: demo\n"}, "§3.1a", id="a-brief-path"),
    pytest.param("zod/skill-brief.yaml", {"zod/skill-brief.yaml": "name: demo\n"}, "§3.1a", id="owner-repo-shaped"),
    pytest.param("forge-data/zod", {"forge-data/zod/skill-brief.yaml": "name: demo\n"}, "§3.1a",
                 id="a-folder-holding-a-brief"),
    pytest.param("libs/mylib", {"libs/mylib/src/index.ts": "export {};\n"}, "§3.3", id="a-source-folder"),
    pytest.param("mylib", {"mylib/src/index.ts": "export {};\n"}, "§3.3", id="a-package-shaped-folder"),
    pytest.param("My Projects/lib", {"My Projects/lib/index.ts": "export {};\n"}, "§3.3", id="a-path-with-a-space"),
])
def test_a_relative_path_on_disk_routes_as_a_local_path(target, on_disk, branch, tmp_path):
    """A path that exists is a local path whatever its shape: a brief (or a folder holding one) goes to the ratify
    branch, any other folder to the source branch, never to the package lookup, a github.com URL or the prompt."""
    [first] = _parse_target_block().splitlines()[:1]
    args = shlex.split(first.split("<<", 1)[0])[3:]
    assert args == ["parse-target", "--local-first"]
    _write_tree(tmp_path, on_disk)
    proc = subprocess.run([sys.executable, str(SCRIPTS / "skf-resolve-package.py"), *args], input=target + "\n",
                          capture_output=True, text=True, encoding="utf-8", timeout=60, check=False, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert (out["kind"], out["path"]) == ("local-path", target)
    # the documented local-path route, applied to what is on disk
    [route] = [line for line in _routes().splitlines() if line.startswith("  - `local-path`:")]
    assert route == ("  - `local-path`: a `skill-brief.yaml` file, or a folder that holds one → §3.1a; "
                     "any other path → §3.3.")
    path = tmp_path / target
    is_brief = path.name == "skill-brief.yaml" if path.is_file() else (path / "skill-brief.yaml").is_file()
    assert ("§3.1a" if is_brief else "§3.3") == branch
    assert "test -d" not in _routes()  # no package-shaped special case is left


@needs_bash
def test_the_documented_parse_target_call_keeps_quotes_and_dollars(tmp_path):
    block = _parse_target_block().replace("uv run {resolvePackageHelper}", _script("skf-resolve-package.py"))
    target = "https://github.com/acme/it's-$HOME`x`"
    proc = _bash(block.replace("{target}", target))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["input"] == target


# --------------------------------------------------------------------------
# The draft checkpoint follows the description and the scope (#587)
# --------------------------------------------------------------------------


def test_the_checkpoint_is_written_after_the_description_and_after_the_scope():
    gather = _read(GATHER_INTENT)
    # #599: the summary, the description and the menu are one message; [C] accepts and writes the draft
    assert "Draft checkpoint" not in _section(gather, "### 7. Summarize Gathered Intent")
    assert "Half 2" not in _section(gather, "### 7b. Synthesize Skill Description")
    [accept] = [line for line in _section(gather, "### 8. Present MENU OPTIONS").splitlines()
                if line.startswith("- IF C:")]
    assert accept.index("follow Half 2 (Checkpoint Write)") < accept.index("execute {nextStepFile}")
    scope = _read(SCOPE_DEFINITION)
    checkpoint = _section(scope, "### 5c. Draft Checkpoint (interactive only)")
    assert "{draftCheckpointFile}" in checkpoint and "Half 2 (Checkpoint Write)" in checkpoint
    assert scope.index("### 5c. Draft Checkpoint") < scope.index("### 6. Continue to Brief Confirmation")
    assert re.search(r"^draftCheckpointFile: 'references/draft-checkpoint\.md'$", scope, re.M)
    draft = _read(DRAFT_CHECKPOINT)
    assert "step 5 §4" not in draft and "step 5 §3 removes it" in draft
    assert "## Half 2: Checkpoint Write (loaded from step 1 §8, and from step 3 §5c)" in draft
    for field in ("`language`", "`detected_version`", "`analysis_ref`", "`monorepo_workspace`", "`scripts_intent`",
                  "`assets_intent`", "`tier_a_include`", "`rationale`", "`registry_path`"):
        assert field in _section(draft, "## Half 2: Checkpoint Write (loaded from step 1 §8, and from step 3 §5c)")
    assert "the checkpoint step 1 §8 and step 3 §5c wrote" in _read(WRITE_BRIEF)


def test_a_draft_that_holds_the_scope_resumes_at_step_four():
    resume = _section(_read(DRAFT_CHECKPOINT), "### `[Y]`")
    [scoped] = [line for line in resume.splitlines() if line.startswith("- **A draft written after step 3**")]
    assert "execute `references/confirm-brief.md` (step 4)" in scoped
    assert "`scope.registry_path` / `scope.ui_variants` / `scope.demo_patterns` ← `draft.scope.*`" in scoped
    [early] = [line for line in resume.splitlines() if line.startswith("- **A draft written by step 1**")]
    assert "§8" in early
    # Revise Scope after such a resume stages the analysis again before step 3 reads it
    rules = _section(_read(SCOPE_DEFINITION), "## Rules")
    [line] = [line for line in rules.splitlines() if line.startswith("- **Resumed draft:**")]
    assert "`{run_dir}/tree.json` does not exist" in line and "{analyzeStepFile}" in line


@needs_bash
def test_the_checkpoint_write_creates_the_skill_folder_and_keeps_an_apostrophe(tmp_path):
    [block] = _blocks(_read(DRAFT_CHECKPOINT), "{atomicWriteHelper}")
    draft = {"target_repo": "https://github.com/o/r", "intent": "the client's retries",
             "description": "It's the `retry` API. Use when a call fails.", "forge_tier": "Forge"}
    forge = tmp_path / "forge"
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    block = (block.replace("<the draft, as one JSON object>", json.dumps(draft))
             .replace("{run_dir}", run_dir.as_posix()).replace("{forge_data_folder}", forge.as_posix())
             .replace("{skill-name}", "demo").replace("uv run {atomicWriteHelper}", _script("skf-atomic-write.py")))
    proc = _bash(block)
    assert proc.returncode == 0, proc.stderr
    assert json.loads((forge / "demo" / ".brief-draft.json").read_text(encoding="utf-8")) == draft


# --------------------------------------------------------------------------
# Step 3's tier-A list from the recipe runner (#584)
# --------------------------------------------------------------------------


def _pinned_ast_grep() -> bool:
    """True when the ast-grep on PATH is the version package.json's test:python pins."""
    scripts = json.loads((REPO / "package.json").read_text(encoding="utf-8"))["scripts"]
    pin = re.search(r"--with ast-grep-cli==([\w.]+)", scripts["test:python"])
    exe = shutil.which("ast-grep")
    if pin is None or exe is None:
        return False
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0 and out.stdout.split()[-1:] == [pin.group(1)]


def test_the_tier_a_list_is_the_runners_reexport_targets():
    section = _section(_read(SCOPE_DEFINITION), "### 3c. Tier-A Authoring Surface (coarse-glob monorepo subsets)")
    [block] = _blocks(section, "{extractPublicApiHelper}")
    assert "--mode full" in block and '-o "{run_dir}/tier-a.json"' in block
    assert "`reexport_targets`" in section and "`entry_points.files[].file`" in section
    assert "by eye" in section and "`workflow_warnings[]`" in section  # Quick tier and a failed run
    assert "extractPublicApiProbeOrder:" in _read(SCOPE_DEFINITION)
    # a clone this section makes holds only the scope's folders, and goes once the runner has run
    assert "sparse-checkout set" in section
    assert 'remove a clone this section made (`rm -rf "{run_dir}/clone"`)' in section


def _tier_a_candidates(section: str, result: Path) -> list[str]:
    """Run the documented one-line filter over a runner result and return the lines it prints."""
    [block] = _blocks(section, "reexport_targets")
    [line] = block.strip().splitlines()
    argv = shlex.split(line.replace("{run_dir}/tier-a.json", result.as_posix()))
    assert argv[:3] == ["uv", "run", "python"]
    proc = subprocess.run([sys.executable, *argv[3:]], capture_output=True, text=True, encoding="utf-8",
                          timeout=60, check=False)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.splitlines()


def test_the_tier_a_candidates_are_printed_by_one_command(tmp_path):
    """The candidates are the defining files, less a name another package defines and less the entry points."""
    section = _section(_read(SCOPE_DEFINITION), "### 3c. Tier-A Authoring Surface (coarse-glob monorepo subsets)")
    result = tmp_path / "tier-a.json"
    result.write_bytes(json.dumps({
        "entry_points": {"files": [{"file": "packages/foo/src/index.ts"}]},
        "reexport_targets": [{"name": "a", "file": "packages/foo/src/a.ts"},
                             {"name": "quote", "file": "packages/foo/src/a.ts"},
                             {"name": "z", "file": "packages/foo/src/z-it's.ts"},
                             {"name": "local", "file": "packages/foo/src/index.ts"},
                             {"name": "other", "file": None}],
    }).encode("utf-8"))
    assert _tier_a_candidates(section, result) == ["packages/foo/src/a.ts", "packages/foo/src/z-it's.ts"]


@pytest.mark.skipif(not POSIX_BASH or not _pinned_ast_grep(), reason="needs bash and the pinned ast-grep")
def test_the_documented_runner_call_lists_the_files_the_barrel_re_exports(tmp_path):
    section = _section(_read(SCOPE_DEFINITION), "### 3c. Tier-A Authoring Surface (coarse-glob monorepo subsets)")
    [block] = _blocks(section, "{extractPublicApiHelper}")
    repo = _write_tree(tmp_path / "repo", {
        "package.json": '{"name": "root", "private": true, "workspaces": ["packages/*"]}\n',
        "packages/foo/package.json": '{"name": "@acme/foo", "main": "src/index.ts"}\n',
        "packages/foo/src/index.ts": "export * from './a';\nexport { b } from './b';\nexport const local = 1;\n",
        "packages/foo/src/a.ts": "export function a() {}\nexport const quote = \"it's\";\n",
        "packages/foo/src/b.ts": "export const b = 2;\n",
        "packages/foo/src/internal.ts": "export const hidden = 3;\n",
        "packages/bar/package.json": '{"name": "@acme/bar", "main": "src/index.ts"}\n',
        "packages/bar/src/index.ts": "export const bar = 1;\n",
    })
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    block = (block.replace("uv run {extractPublicApiHelper}", _script("skf-extract-public-api.py"))
             .replace("<source folder>", repo.as_posix()).replace("<include glob>", "packages/foo/src/**")
             .replace("<exclude glob>", "**/*.test.ts").replace("{language}", "typescript")
             .replace("{run_dir}", run_dir.as_posix()))
    proc = _bash(block, cwd=REPO)
    assert proc.returncode == 0, proc.stderr
    assert _tier_a_candidates(section, run_dir / "tier-a.json") == ["packages/foo/src/a.ts", "packages/foo/src/b.ts"]


# --------------------------------------------------------------------------
# The QMD registry entry
# --------------------------------------------------------------------------


def test_the_qmd_registry_entry_is_staged_json_the_helper_accepts(tmp_path):
    text = _read(QMD_REGISTRATION)
    [block] = _blocks(text, "register-qmd-collection")
    body = HEREDOC_RE.search(block).group("body")
    entry = json.loads(body.replace("{skill-name}", "demo").replace("{current ISO date}", "2026-10-01"))
    assert entry["name"] == "demo-brief" and "status" not in entry
    target = tmp_path / "forge-tier.yaml"
    tools = {"tools": {"ast_grep": True, "gh_cli": True, "qmd": True, "ccc": False, "security_scan": False},
             "tier": "Deep", "tier_detected_at": "2026-10-01T00:00:00+00:00",
             "ccc_index": {"indexed_path": None, "last_indexed": None, "status": "none", "file_count": 0,
                           "exclude_patterns": []}}
    proc = _run("skf-forge-tier-rw.py", "write-tools", "--target", str(target), stdin=json.dumps(tools))
    assert proc.returncode == 0, proc.stderr
    proc = _run("skf-forge-tier-rw.py", "register-qmd-collection", "--target", str(target),
                stdin=json.dumps(dict(entry, status="pending")))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["action"] == "appended"


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------


def test_the_run_folder_sits_under_the_project_root():
    """Every place the steps name the run folder's parent carries {project-root}."""
    for path in sorted(REFERENCES.glob("*.md")):
        for line in _read(path).splitlines():
            for match in re.finditer(r"\S*_bmad-output/\.skf-run", line):
                assert "{project-root}/_bmad-output/.skf-run" in match.group(0), f"{path.name}: {line[:100]}"
