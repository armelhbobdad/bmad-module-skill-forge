#!/usr/bin/env python3
"""create-skill reads a remote source through skf-source-tree.py resolve and
changes forge-tier.yaml only through skf-forge-tier-rw.py.

Prose pins, each checked against the helper it names:
- extract.md §2b runs resolve with --update-clone, maps target_ref,
  target_version and version onto its flags, binds source_ref,
  source_commit, tag_resolution and workspace_path (and the rest) from keys
  resolve prints, and dispatches on every status and failure reason it
  prints. Only the choice between several matching tags stays in prose, and
  it has a headless default. The tag forms the protocol lists are the ones
  resolve tries, in its order.
- The documented command, filled in as the prose says, reads a tag of a
  scratch upstream into a private tree and moves SKF's clone to it; several
  matching tags come back as candidates, and the command run again with the
  chosen one as --target-ref reads it; close removes the tree.
- metadata.json records SKF's clone as source_root, never the tree (the
  remote URL when the workspace path holds another folder, null for a
  docs-only brief), and step 7 and every HALT after §2b remove the tree: the
  [U] halt and report.md's HARD HALT contract name the close command. Every
  brief starts clean before the docs-only skip, so a --batch run never
  carries one brief's paths into the next.
- A missing skf-forge-tier-rw.py skips a registry change with a warning in
  every step, never a HALT.
- No create-skill step matches tags, clones, fetches, checks out or locks by
  hand.
- fetch-temporal, fetch-docs and generate-artifacts change qmd_collections and
  ccc_index_registry only through skf-forge-tier-rw.py (no flock or mtime
  compare-and-swap text), roll a failed `qmd collection add` back through
  remove-qmd-collection, and read the cache and embed checks from its `read`
  JSON. Every entry they pipe, filled in, is JSON the helper accepts.

The upstream is a bare repository served as https://github.com/acme/lib
through a url.<file uri>.insteadOf entry in a per-test global git config, so
the real git transport runs without the network. SKF_WORKSPACE and the
system temp folder point into tmp_path.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
CS = SRC / "skf-create-skill"
REFS = CS / "references"
EXTRACT = REFS / "extract.md"
PROTOCOLS = REFS / "source-resolution-protocols.md"
GENERATE = REFS / "generate-artifacts.md"
FETCH_TEMPORAL = REFS / "sub" / "fetch-temporal.md"
FETCH_DOCS = REFS / "sub" / "fetch-docs.md"
AUTH_PROTOCOL = REFS / "authoritative-files-protocol.md"
REPORT = REFS / "report.md"
CS_SKILL = CS / "SKILL.md"
SKILL_SECTIONS = CS / "assets" / "skill-sections.md"
SCRIPTS = SRC / "shared" / "scripts"
SOURCE_TREE = SCRIPTS / "skf-source-tree.py"
FORGE_TIER_RW = SCRIPTS / "skf-forge-tier-rw.py"
HYGIENE = SCRIPTS / "skf-ccc-git-hygiene.py"
URL = "https://github.com/acme/lib"
LOCATION_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX", "GIT_COMMON_DIR",
                 "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE")
REGISTRY_FILES = (FETCH_TEMPORAL, FETCH_DOCS, GENERATE)
FILLED = {
    "{skill-name}": "mylib",
    "{name}": "mylib",
    "{current ISO date}": "2026-09-30T12:00:00+00:00",
    "{brief.source_repo}": URL,
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _slice(text: str, start: str, end: str) -> str:
    assert text.count(start) == 1, f"start marker not found exactly once: {start!r}"
    i = text.index(start)
    j = text.find(end, i + len(start))
    assert j != -1, f"end marker {end!r} not found after {start!r}"
    return text[i:j]


def _frontmatter(path: Path) -> dict:
    text = _read(path)
    return yaml.safe_load(text[4:text.index("\n---\n", 4)])


def _fences(text: str) -> list[str]:
    return re.findall(r"^[ \t]*```[^\n]*\n(.*?)^[ \t]*```", text, flags=re.DOTALL | re.MULTILINE)


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _section_2b() -> str:
    return _slice(_read(EXTRACT), "### 2b. Resolve Source Access", "**Deferred CCC Discovery")


def _resolve_command() -> str:
    """The fenced resolve command of §2b, its backslash continuations joined."""
    [fence] = [f for f in _fences(_section_2b()) if " resolve " in f]
    return " ".join(line.strip().rstrip("\\").strip() for line in fence.strip().splitlines())


def _dispatch() -> str:
    return _slice(_section_2b(), "Dispatch on `{source_resolve_status}`:", "Then run Source Commit Capture")


# --------------------------------------------------------------------------
# extract.md §2b: the resolve call and what it binds
# --------------------------------------------------------------------------


def test_resolve_command_takes_the_brief_fields_and_moves_the_clone():
    command = _resolve_command()
    assert command.startswith("uv run {sourceTreeHelper} resolve ")
    for part in ('--source-repo "{source_repo}"', '[--target-ref "{brief.target_ref}"]',
                 '[--version "{brief.target_version}" --name "{brief.name}"]',
                 '[--version "{brief.version}" --implicit]', "--update-clone",
                 '[--hygiene-helper "{cccGitHygieneHelper}"]', '--timeout "{tree_timeout}"'):
        assert part in command, part
    section = _section_2b()
    assert ("Pass the first `--version` line when the brief sets `target_version`, else the second when it "
            "sets `version`, never both") in section
    table = _slice(_read(PROTOCOLS), "| The brief sets |", "\n\n")
    for row in ("| `target_ref` (it takes priority) |", "| `target_version` |", "| only `version` |",
                "| none of them |"):
        assert row in table, row
    # The field-to-flag mapping is written once, in §2b's command.
    for flag in ('--target-ref "{brief.target_ref}"', '--version "{brief.target_version}"',
                 '--version "{brief.version}"', '--name "{brief.name}"'):
        assert flag not in _read(PROTOCOLS), flag


def test_every_bound_key_is_a_key_resolve_prints(tmp_path):
    bind = _slice(_section_2b(), "Bind from its JSON", "\n")
    keys = set(re.findall(r"← `(\w+)`", bind))
    for handoff in ("source_ref", "source_commit", "tag_resolution", "workspace_path"):
        assert f"`{handoff}` ← `{handoff}`" in bind or f"`{{{handoff}}}` ← `{handoff}`" in bind, handoff
    local = tmp_path / "local-source"
    local.mkdir()
    proc = subprocess.run([sys.executable, str(SOURCE_TREE), "resolve", "--source-repo", str(local)],
                          capture_output=True, encoding="utf-8", cwd=str(tmp_path), stdin=subprocess.DEVNULL)
    printed = json.loads(proc.stdout)
    assert printed["status"] == "skipped"
    assert keys <= set(printed), sorted(keys - set(printed))
    assert {"tree", "clone", "clone_status", "clone_skip_reason"} <= keys
    assert "`{workspace_clone}` ← `clone`" in bind
    assert "display each entry of `warnings`" in bind


def test_dispatch_covers_every_status_and_reason():
    helper = _module(SOURCE_TREE, "skf_source_tree_create_prose")
    [statuses] = re.findall(r'status +("ready" \| "ambiguous"[^\n]*)', helper.__doc__)
    dispatch = _dispatch()
    for status in re.findall(r'"([a-z]+)"', statuses):
        assert f"- **`{status}`**" in dispatch, status
    unavailable = _slice(dispatch, "- **`unavailable`**", "\n")
    for reason in helper.OPEN_REASONS:
        assert f"`{reason}`" in unavailable, reason
    assert "- **No candidate resolves, or the command exits 1 or 2, or prints no JSON:**" in dispatch


def test_ready_reads_the_tree_and_records_the_clone():
    ready = _slice(_dispatch(), "- **`ready`**", "\n")
    assert "bind `{source_root}` ← `{source_tree}`" in ready
    assert "Build the §2 filtered file list again from `{source_root}`" in ready
    # A folder at the workspace path that is not SKF's clone (resolve's `clone` is null) is never recorded.
    assert ("Bind `{resolved-source-path}` ← `{workspace_clone}`, or ← `{source_repo}` when "
            "`{workspace_clone}` is null") in ready
    assert "When `{clone_status}` is `advanced` or `ok`" in ready
    assert "bind `{remote_clone_path}` ← `{workspace_clone}`" in ready
    capture = _slice(_read(PROTOCOLS), "## Source Commit Capture", "## Version Reconciliation")
    assert "**The `source_root` metadata.json records** is `{resolved-source-path}`" in capture
    assert "SKF's workspace clone (resolve's `clone`)" in capture
    assert "null for a docs-only skill" in capture
    assert "Never the tree itself" in capture
    assert '"source_root": "{resolved-source-path}"' in _read(SKILL_SECTIONS)


def test_every_brief_starts_clean_before_the_docs_only_skip():
    """A docs-only brief after a remote one must not keep that brief's clone, tree or source_root."""
    section = _section_2b()
    start = _slice(section, "**Start clean:**", "\n")
    assert "for every brief, docs-only included" in start
    assert "set `{source_tree}`, `{workspace_clone}` and `{remote_clone_path}` to null" in start
    assert "`{resolved-source-path}` to `{source_root}` (null for a docs-only brief)" in start
    assert "in a `--batch` run one brief's source never carries into the next" in start
    skip = '**If `source_type: "docs-only"`:** skip the rest of §2b'
    assert section.index("**Start clean:**") < section.index(skip)
    assert section.index("### 2b. Resolve Source Access") < section.index("**Start clean:**")
    assert "skip §2b entirely" not in section


def test_unavailable_degrades_to_source_reading():
    unavailable = _slice(_dispatch(), "- **`unavailable`**", "\n")
    # A retry starts the fetch again with only a little more time: the first call gets the longest one.
    assert "run the command once more" not in unavailable and "without the retry" not in _dispatch()
    remote = _slice(_section_2b(), "**Remote source at Forge, Forge+ or Deep tier:**", "\n")
    assert "a little under the longest timeout your shell tool can be given" in remote
    assert "Give the command that longest shell timeout" in remote
    assert "Degrading to source reading (T1-low) for this run." in unavailable
    assert "Keep `{source_root}` the remote URL" in unavailable
    assert "extract with the Quick tier strategy in §4" in unavailable


def test_only_the_tag_choice_stays_in_prose():
    protocols = _read(PROTOCOLS)
    several = _slice(protocols, "### Several Matching Tags", "### Local Source Warning")
    assert "`tag_resolution.candidates` lists the matching tags in the priority order above" in several
    assert "This is the one choice tag resolution leaves to you" in several
    headless = _slice(several, "- **GATE [default: first candidate]**", "\n")
    for token in ("under `{headless_mode}`, take the first candidate",
                  "record the auto-decision per the Workflow Rules", "gate `tag-choice`", "decision `{tag}`"):
        assert token in headless, token
    assert "auto-decisions.jsonl" not in several, "the sink mechanics live in the Workflow Rules"
    assert "Setting `target_ref` in the brief skips this question next time." in several
    ambiguous = _slice(_dispatch(), "- **`ambiguous`**", "\n")
    assert ('run the command again with `--target-ref "{chosen tag}"` (`HEAD` for the default branch) in '
            "place of `--version`, `--name`, `--implicit` and any `--target-ref` from the brief") in ambiguous
    gates = next(line for line in _read(CS_SKILL).splitlines() if line.startswith("| **Gates** |"))
    assert "step 3: Tag Choice Gate" in gates
    for by_hand in ("--paginate", "ls-remote", "semver sort", "refs/tags/", "Closest available tags"):
        assert by_hand not in protocols, by_hand


def test_a_head_fallback_adds_to_the_warning_resolve_printed():
    """resolve's warning already names the version and the nearest tags; the protocol adds only its advice."""
    protocols = _read(PROTOCOLS)
    fallbacks = [line for line in protocols.splitlines() if line.startswith("- **`fallback-head`:**")]
    assert len(fallbacks) == 2
    for line in fallbacks:
        assert "the warning it printed names the nearest tags. ⚠️ Add:" in line
    assert "No git tag found matching" not in protocols and "Falling back to default branch" not in protocols
    helper = _read(SOURCE_TREE)
    assert "no tag of {source_repo} matches version {version}; reading HEAD" in helper
    assert "(nearest tags: " in helper


def test_protocol_lists_the_tag_forms_resolve_tries_in_its_order():
    helper = _module(SOURCE_TREE, "skf_source_tree_create_forms")
    explicit = _slice(_read(PROTOCOLS), "### Explicit Tag Resolution", "Outcomes, from")
    implicit = _slice(_read(PROTOCOLS), "### Implicit Tag Resolution", "Package-scoped monorepo forms")

    def listed(section: str) -> list[str]:
        forms = []
        for line in section.splitlines():
            if line.startswith("- **"):
                forms += re.findall(r"`([^`]*\{[^`]*)`", line.split("(e.g", 1)[0])
        return forms

    fill = {"{target_version}": "1.0.0", "{brief.version}": "1.0.0", "{brief.name}": "lib", "{scope}": "acme"}
    documented = []
    for form in listed(explicit):
        for key, value in fill.items():
            form = form.replace(key, value)
        documented.append(form)
    tags = {tag: "0" * 40 for tag in documented}
    assert helper.match_tags(tags, "1.0.0", "lib") == documented
    documented_implicit = [form.replace("{brief.version}", "1.0.0") for form in listed(implicit)]
    assert helper.match_tags(tags, "1.0.0", "lib", implicit=True) == documented_implicit == ["1.0.0", "v1.0.0"]


def test_no_create_skill_step_resolves_or_locks_by_hand():
    for path in sorted(CS.rglob("*.md")):
        text = _read(path)
        for by_hand in ("git clone", "fetch origin", "checkout FETCH_HEAD", "ls-remote", "flock -x",
                        "fcntl.flock", "kill -0", "read-CAS", "st_mtime"):
            assert by_hand not in text, (path.relative_to(REPO_ROOT), by_hand)
        for line in text.splitlines():
            if "flock" in line:
                # The only lock left is the one skf-atomic-write.py flip-link takes inside its own call.
                assert "`{skill_group}/active.skf-lock`" in line, (path.relative_to(REPO_ROOT), line[:100])


def test_every_halt_after_resolution_removes_the_tree():
    rule = next(line for line in _read(CS_SKILL).splitlines() if "bound `{source_tree}`" in line)
    assert 'every HALT after it first runs `uv run {sourceTreeHelper} close --tree "{source_tree}"`' in rule
    generate = _read(GENERATE)
    last = generate[generate.index("### 7. Auto-Proceed"):]
    assert 'uv run {sourceTreeHelper} close --tree "{source_tree}"' in last
    assert "Then set `{source_tree}` to null." in last
    assert last.index("close --tree") < last.index("load `{nextStepFile}`")
    close = 'uv run {sourceTreeHelper} close --tree "{source_tree}"'
    update = _slice(_read(AUTH_PROTOCOL), "- **[U] Update:**", "6. **Summary.**")
    assert f"When `{{source_tree}}` is set, first run `{close}` from `{{project-root}}`" in update
    halt = _slice(_read(REPORT), "### Result Contract on HARD HALT", "**For every HARD HALT under")
    assert halt.index("**Remove the private source tree first.**") < halt.index("The success-variant contract")
    assert "headless or not" in halt and f"run `{close}` from `{{project-root}}`" in halt
    for path in (EXTRACT, GENERATE, REPORT):
        order = _frontmatter(path)["sourceTreeProbeOrder"]
        assert order == ["{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py",
                         "{project-root}/src/shared/scripts/skf-source-tree.py"], path.name


# --------------------------------------------------------------------------
# The documented command against a scratch upstream
# --------------------------------------------------------------------------


def _env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in LOCATION_VARS}


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(cwd), *args],
                          capture_output=True, encoding="utf-8", errors="replace", env=_env(),
                          stdin=subprocess.DEVNULL)
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"
    return proc.stdout.strip()


@pytest.fixture
def upstream(tmp_path, monkeypatch):
    """acme/lib: tags 1.0.0 and v1.0.0 on the first commit, lib@2.0.0 on the second (main)."""
    if shutil.which("git") is None:
        pytest.skip("git is not available")
    work, bare = tmp_path / "work", tmp_path / "up.git"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    shas = {}
    for version in ("1.0.0", "2.0.0"):
        (work / "pyproject.toml").write_bytes(f'[project]\nname = "lib"\nversion = "{version}"\n'.encode("utf-8"))
        _git(work, "add", "pyproject.toml")
        _git(work, "commit", "-q", "-m", version)
        shas[version] = _git(work, "rev-parse", "HEAD")
        if version == "1.0.0":
            _git(work, "tag", "1.0.0")
            _git(work, "tag", "-a", "v1.0.0", "-m", "v1.0.0")
        else:
            _git(work, "tag", "lib@2.0.0")
    _git(tmp_path, "clone", "-q", "--bare", str(work), str(bare))
    gitconfig = tmp_path / "gitconfig"
    session = os.environ.get("GIT_CONFIG_GLOBAL")
    text = ""
    if session:
        text += '[include]\n\tpath = "' + Path(session).as_posix() + '"\n'
    text += f'[url "{bare.as_uri()}"]\n\tinsteadOf = {URL}\n'
    gitconfig.write_bytes(text.encode("utf-8"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    ws, tmp = tmp_path / "ws", tmp_path / "t"
    tmp.mkdir()
    monkeypatch.setenv("SKF_WORKSPACE", str(ws))
    for var in ("TMPDIR", "TEMP", "TMP"):
        monkeypatch.setenv(var, str(tmp))
    monkeypatch.setattr(tempfile, "tempdir", None)
    return {"shas": shas, "ws": ws, "cwd": tmp_path}


def _documented_resolve(brief: dict) -> list[str]:
    """§2b's command filled in for `brief` as its "Pass ..." sentence says."""
    command = _resolve_command()
    keep = {
        "--target-ref": "target_ref" in brief,
        '--version "{brief.target_version}"': "target_version" in brief,
        '--version "{brief.version}"': "version" in brief and "target_version" not in brief,
        "--hygiene-helper": True,
    }

    def group(match: re.Match) -> str:
        body = match.group(1)
        return body if any(body.startswith(flag) and wanted for flag, wanted in keep.items()) else ""

    command = re.sub(r"\[([^\[\]]*)\]", group, command).replace("uv run {sourceTreeHelper} ", "", 1)
    fills = {"{source_repo}": URL, "{cccGitHygieneHelper}": HYGIENE.as_posix(), "{tree_timeout}": "100",
             **{f"{{brief.{key}}}": value for key, value in brief.items()}}
    for key, value in fills.items():
        command = command.replace(key, value)
    assert "{" not in command, command
    words = shlex.split(command)
    assert words[0] == "resolve", words
    return [sys.executable, str(SOURCE_TREE), *words]


def _run(argv: list[str], cwd: Path) -> dict:
    proc = subprocess.run(argv, capture_output=True, encoding="utf-8", errors="replace", cwd=str(cwd),
                          stdin=subprocess.DEVNULL, timeout=300)
    assert proc.stdout.strip(), proc.stderr
    return json.loads(proc.stdout)


def test_documented_resolve_reads_the_tag_into_a_private_tree(upstream):
    out = _run(_documented_resolve({"name": "lib", "target_version": "2.0.0"}), upstream["cwd"])
    assert (out["status"], out["source_ref"], out["tag_resolution"]["status"]) == ("ready", "lib@2.0.0", "matched")
    assert out["source_commit"] == upstream["shas"]["2.0.0"]
    tree = Path(out["tree"])
    assert b'version = "2.0.0"' in (tree / "pyproject.toml").read_bytes()
    clone = Path(out["workspace_path"])
    assert clone.as_posix() == (upstream["ws"] / "repos" / "github.com" / "acme" / "lib").as_posix()
    assert out["clone_status"] in ("advanced", "ok")
    assert _git(clone, "rev-parse", "HEAD") == out["source_commit"]
    assert not tree.is_relative_to(clone), "the run reads its own tree, never SKF's clone"
    closed = _run([sys.executable, str(SOURCE_TREE), "close", "--tree", out["tree"]], upstream["cwd"])
    assert closed["status"] == "removed" and not tree.exists()


def test_several_matching_tags_then_the_chosen_one(upstream):
    out = _run(_documented_resolve({"name": "lib", "target_version": "1.0.0"}), upstream["cwd"])
    assert out["status"] == "ambiguous" and out["tree"] is None
    assert out["tag_resolution"]["candidates"] == ["1.0.0", "v1.0.0"]
    chosen = out["tag_resolution"]["candidates"][0]  # the headless default
    again = _run(_documented_resolve({"target_ref": chosen}), upstream["cwd"])
    assert (again["status"], again["source_ref"], again["tag_resolution"]["status"]) == ("ready", "1.0.0",
                                                                                          "target-ref")
    assert again["source_commit"] == upstream["shas"]["1.0.0"]
    _run([sys.executable, str(SOURCE_TREE), "close", "--tree", again["tree"]], upstream["cwd"])


def test_implicit_version_without_a_tag_falls_back_to_head(upstream):
    out = _run(_documented_resolve({"name": "lib", "version": "2.0.0"}), upstream["cwd"])
    assert (out["status"], out["source_ref"]) == ("ready", "HEAD")
    record = out["tag_resolution"]
    assert (record["status"], record["mode"], record["reason"]) == ("fallback-head", "implicit", "no-matching-tag")
    assert out["source_commit"] == upstream["shas"]["2.0.0"]
    _run([sys.executable, str(SOURCE_TREE), "close", "--tree", out["tree"]], upstream["cwd"])


# --------------------------------------------------------------------------
# forge-tier.yaml registry writes
# --------------------------------------------------------------------------


def _registry_blocks(path: Path) -> list[tuple[str, str]]:
    """(command line, entry JSON) of each heredoc a file pipes to the registry helper."""
    blocks = []
    for fence in _fences(_read(path)):
        lines = [line.strip() for line in fence.strip().splitlines()]
        if lines and lines[0].endswith("<<'SKF_REGISTRY_ENTRY'"):
            assert lines[-1] == "SKF_REGISTRY_ENTRY", lines
            blocks.append((lines[0], "\n".join(lines[1:-1])))
    return blocks


def _fill(text: str, extra: dict | None = None) -> str:
    for key, value in {**FILLED, **(extra or {})}.items():
        text = text.replace(key, value)
    return text


def _rw(target: Path, *argv: str, stdin: str = "") -> dict:
    proc = subprocess.run([sys.executable, str(FORGE_TIER_RW), *argv[:1], "--target", str(target), *argv[1:]],
                          input=stdin, capture_output=True, encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _forge_tier(tmp_path: Path) -> Path:
    target = tmp_path / "forger-sidecar" / "forge-tier.yaml"
    target.parent.mkdir()
    _rw(target, "write-tools", stdin=json.dumps({
        "tools": {"ast_grep": True, "gh_cli": True, "qmd": True, "ccc": True},
        "tier": "Deep",
        "ccc_index": {"status": "fresh"},
    }))
    return target


@pytest.mark.parametrize("path", REGISTRY_FILES, ids=[p.name for p in REGISTRY_FILES])
def test_registry_changes_only_through_the_helper(path):
    text = _read(path)
    for by_hand in ("st_mtime", "read-CAS", "{atomicWriteHelper} write --target {sidecar_path}",
                    "replace it. Otherwise, append", "forge-tier.yaml.lock` for the read-modify-write"):
        assert by_hand not in text, by_hand
    for line in text.splitlines():
        if "flock" in line:  # only skf-atomic-write.py flip-link's own lock, in generate-artifacts §4
            assert "`{skill_group}/active.skf-lock`" in line, line[:100]
    frontmatter = _frontmatter(path)
    assert frontmatter["forgeTierRwProbeOrder"][-1] == "{project-root}/src/shared/scripts/skf-forge-tier-rw.py"
    assert frontmatter["forgeTierConfig"] == "{sidecar_path}/forge-tier.yaml"
    assert "holds `{sidecar_path}/forge-tier.yaml.lock` for its one read-modify-write" in text
    if path != GENERATE:
        assert "atomicWriteProbeOrder" not in frontmatter and "{atomicWriteHelper}" not in text


@pytest.mark.parametrize("path", REGISTRY_FILES, ids=[p.name for p in REGISTRY_FILES])
def test_a_missing_registry_helper_never_halts(path):
    """Steps 3b, 3c and 7 share one policy: registration is skipped with a warning, never a HALT."""
    text = _read(path)
    end = text.index("\n---\n", 4)
    comment = text[text.index("# Resolve `{forgeTierRwHelper}`"):text.index("forgeTierRwProbeOrder:")]
    probe = " ".join(line.lstrip("#").strip() for line in comment.splitlines())
    assert "HALT" not in probe and "the registry change with a warning" in probe
    for line in text[end:].splitlines():
        assert not ("{forgeTierRwHelper}" in line and "HALT" in line), line[:100]


@pytest.mark.parametrize("path", REGISTRY_FILES, ids=[p.name for p in REGISTRY_FILES])
def test_registered_entries_are_json_the_helper_accepts_and_rolls_back(path, tmp_path):
    target = _forge_tier(tmp_path)
    ccc_root = (tmp_path / "ws" / "repos" / "github.com" / "acme" / "lib").as_posix()
    blocks = _registry_blocks(path)
    assert blocks, f"{path.name} registers nothing through the helper"
    text = _read(path)
    for command, body in blocks:
        entry = json.loads(_fill(body, {"{ccc_root}": ccc_root}))
        words = shlex.split(command.split("<<", 1)[0])
        assert words[:3] == ["uv", "run", "{forgeTierRwHelper}"]
        assert words[4:] == ["--target", "{forgeTierConfig}"], words
        subcommand = words[3]
        result = _rw(target, subcommand, stdin=json.dumps(entry))
        assert result["action"] == "appended", result
        data = _rw(target, "read")["data"]
        if subcommand == "register-qmd-collection":
            assert entry in data["qmd_collections"]
            rollback = f'remove-qmd-collection --target "{{forgeTierConfig}}" --name {json.loads(body)["name"]}'
            assert rollback in text, rollback
            removed = _rw(target, "remove-qmd-collection", "--name", entry["name"])
            assert removed["action"] == "removed"
        else:
            assert subcommand == "register-ccc-index"
            assert entry in data["ccc_index_registry"] and entry["path"] == ccc_root


def test_cache_and_embed_checks_read_the_registry_json():
    cache = _slice(_read(FETCH_TEMPORAL), "### 2. Check Cache", "### 3.")
    assert 'uv run {forgeTierRwHelper} read --target "{forgeTierConfig}"' in cache
    assert "Bind `{registry_collections}` ← its `data.qmd_collections`" in cache
    assert "Read `forge-tier.yaml` from the sidecar path." not in cache
    embed = _slice(_read(FETCH_TEMPORAL), "**Scope the embed:**", "\n")
    assert "`{registry_collections}`" in embed
    for path, section in ((FETCH_DOCS, ("### 5b.", "### 6.")), (GENERATE, ("### 6. ", "### 6b."))):
        assert 'uv run {forgeTierRwHelper} read --target "{forgeTierConfig}"' in _slice(_read(path), *section)


def test_a_failed_add_rolls_the_registry_back_and_registers_nothing():
    temporal = _slice(_read(FETCH_TEMPORAL), "### 4. Index Into QMD", "**Keep `{temporal_feeder}`.**")
    fence = _fences(temporal)[0]
    assert fence.index("if ! qmd collection add") < fence.index("remove-qmd-collection") < fence.index("else")
    assert "**Register the collection** only when `qmd collection add` succeeded" in temporal
    docs = _slice(_read(FETCH_DOCS), "### 5b.", "### 6.")
    assert "**If `qmd collection add` fails after a successful `remove`:** remove the registry entry too" in docs
    assert "4. Register the collection in the `qmd_collections` array (only if step 2 `add` succeeded)" in docs
    extraction = _slice(_read(GENERATE), "### 6. ", "### 6b.")
    fence = _fences(extraction)[0]
    assert fence.index("if qmd collection add") < fence.index("else") < fence.index("remove-qmd-collection")
    assert "**Registry update:** only when `qmd collection add` succeeded" in extraction


def test_generate_6b_takes_no_lock_of_its_own():
    """The W1 helper holds forge-tier.yaml.lock itself; a second, outside lock is stale to it."""
    section = _slice(_read(GENERATE), "### 6b.", "### 7.")
    for gone in ("Acquire an exclusive `flock`", "Release the lock after the command completes",
                 "under `flock`", "fall back to read-CAS-by-mtime"):
        assert gone not in section, gone
    assert "Like every registry change of §6, the helper holds `{sidecar_path}/forge-tier.yaml.lock`" in section
