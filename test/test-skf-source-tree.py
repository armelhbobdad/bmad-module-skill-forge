#!/usr/bin/env python3
"""Tests for skf-source-tree.py: update-skill reads a remote skill at one commit.

A scratch upstream (a bare repository) is served as
https://github.com/acme/lib through a url.<file uri>.insteadOf entry in a
per-test global git config, so every clone, ls-remote and fetch runs the
real git transport without the network. The upstream history:

- v1 (lightweight tag): src/core.py, scripts/build.sh, pyproject.toml 1.0.0
  and a tracked .gitignore;
- v2 (annotated tag): adds src/extra.py and scripts/release.sh, edits
  build.sh, pyproject.toml 2.0.0;
- m3 (main): deletes scripts/release.sh;
- m4 (main, pushed by the tests that need it): renames src/core.py to
  src/core2.py, adds "src/dir sp/é.py" and edits .gitignore.

SKF_WORKSPACE and the system temp folder point into tmp_path, so the
workspace clone, the run folders and the seven-day sweep never leave it.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "src" / "shared" / "scripts"
INIT = REPO_ROOT / "src" / "skf-update-skill" / "references" / "init.md"
HELPER = SCRIPTS / "skf-source-tree.py"
ATOMIC_WRITE = SCRIPTS / "skf-atomic-write.py"
HYGIENE = SCRIPTS / "skf-ccc-git-hygiene.py"
DRIFT = SCRIPTS / "skf-check-workspace-drift.py"
MERGE_CCC = SCRIPTS / "skf-merge-ccc-exclusions.py"
URL = "https://github.com/acme/lib"
LOCATION_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_PREFIX",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE",
)
CCC_BLOCK = "# CocoIndex Code (ccc)\n/.cocoindex_code/\n"

_MODULE = None


def _mod():
    """Load the helper lazily, so a missing helper fails each test, not collection."""
    global _MODULE
    if _MODULE is None:
        assert HELPER.is_file(), f"missing helper: {HELPER}"
        spec = importlib.util.spec_from_file_location("skf_source_tree", HELPER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _MODULE = module
    return _MODULE


def _args(*argv: str):
    return _mod()._build_parser().parse_args(list(argv))


def _env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in LOCATION_VARS}


def _g(cwd, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "advice.detachedHead=false",
         "-C", str(cwd), *args],
        capture_output=True, encoding="utf-8", errors="replace", env=_env(), stdin=subprocess.DEVNULL,
    )
    if check:
        assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"
    return proc.stdout.strip()


def _config_value(path: Path) -> str:
    text = path.as_posix().replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _snapshot(path: Path) -> dict:
    """{relpath: (size, mtime_ns)} for every file and link under path."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(path):
        for name in [*dirnames, *filenames]:
            p = Path(dirpath) / name
            st = os.lstat(p)
            out[p.relative_to(path).as_posix()] = (st.st_size, st.st_mtime_ns)
    return out


def _trees(env) -> list[Path]:
    found = []
    for root in (env.ws / "trees", env.tmp):
        if root.is_dir():
            found += [p for p in root.iterdir() if p.name.startswith("skf-tree-")]
    return found


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Scratch upstream, hermetic git config, workspace and temp folder."""
    work, bare = tmp_path / "work", tmp_path / "up.git"
    work.mkdir()
    _g(work, "init", "-q", "-b", "main")

    def commit(changes: dict, message: str) -> str:
        for rel, text in changes.items():
            p = work / rel
            if text is None:
                _g(work, "rm", "-q", "--", rel)
            else:
                _write(p, text)
                _g(work, "add", "--", rel)
        _g(work, "commit", "-q", "-m", message)
        return _g(work, "rev-parse", "HEAD")

    commit({"src/core.py": "def a(): pass\ndef b(): pass\n", "scripts/build.sh": "echo build\n",
            "pyproject.toml": '[project]\nname = "lib"\nversion = "1.0.0"\n', ".gitignore": "*.pyc\n"}, "v1")
    _g(work, "tag", "v1")
    commit({"src/extra.py": "def c(): pass\ndef d(): pass\ndef e(): pass\n", "scripts/release.sh": "echo rel\n",
            "scripts/build.sh": "echo build v2\n", "pyproject.toml": '[project]\nname = "lib"\nversion = "2.0.0"\n'},
           "v2")
    _g(work, "tag", "-a", "v2", "-m", "v2")
    commit({"scripts/release.sh": None}, "m3")
    _g(tmp_path, "clone", "-q", "--bare", str(work), str(bare))

    gitconfig = tmp_path / "gitconfig"
    session = os.environ.get("GIT_CONFIG_GLOBAL")

    def set_config(target: Path, hooks: Path | None = None) -> None:
        text = ""
        if session:
            text += f"[include]\n\tpath = {_config_value(Path(session))}\n"
        text += f'[url "{target.as_uri()}"]\n\tinsteadOf = {URL}\n'
        if hooks is not None:
            text += f"[core]\n\thooksPath = {_config_value(hooks)}\n"
        gitconfig.write_bytes(text.encode("utf-8"))

    set_config(bare)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    ws, tmp = tmp_path / "ws", tmp_path / "t"
    tmp.mkdir()
    monkeypatch.setenv("SKF_WORKSPACE", str(ws))
    for var in ("TMPDIR", "TEMP", "TMP"):
        monkeypatch.setenv(var, str(tmp))
    monkeypatch.setattr(tempfile, "tempdir", None)
    clone = ws / "repos" / "github.com" / "acme" / "lib"

    def sha(ref: str) -> str:
        return _g(bare, "rev-parse", f"{ref}^{{commit}}")

    def push(changes: dict, message: str, tag: str | None = None, annotated: bool = False) -> str:
        new = commit(changes, message)
        if tag:
            _g(work, "tag", *(["-a", tag, "-m", tag] if annotated else [tag]))
        _g(work, "push", "-q", str(bare), "main", *([f"refs/tags/{tag}"] if tag else []))
        return new

    def push_m4() -> str:
        return push({"src/core.py": None, "src/core2.py": "def a(): pass\ndef b(): pass\n",
                     "src/dir sp/é.py": "def f(): pass\n", ".gitignore": "*.pyc\n*.log\n"}, "m4")

    def clone_at(ref: str, move_to: str | None = None, dest: Path | None = None) -> Path:
        dest = dest or clone
        dest.parent.mkdir(parents=True, exist_ok=True)
        branch = [] if ref == "HEAD" else ["--branch", ref]
        _g(dest.parent, "clone", "-q", "--depth", "1", *branch, URL, str(dest))
        if move_to:
            _g(dest, "fetch", "-q", "--depth", "1", "origin", move_to)
            _g(dest, "checkout", "-q", "--detach", move_to)
        return dest

    def run(*argv: str, extra_env: dict | None = None):
        child = dict(os.environ)
        child.update(extra_env or {})
        proc = subprocess.run([sys.executable, str(HELPER), *argv], capture_output=True, encoding="utf-8",
                              errors="replace", env=child, cwd=str(tmp_path), stdin=subprocess.DEVNULL)
        try:
            data = json.loads(proc.stdout) if proc.stdout.strip() else None
        except ValueError:
            data = None
        return SimpleNamespace(rc=proc.returncode, json=data, stdout=proc.stdout, stderr=proc.stderr)

    def open_(*extra: str, pin: str = "", ref: str = "v2", root: Path | str | None = None):
        return run("open", "--source-repo", URL, "--source-root", str(root if root is not None else clone),
                   "--source-ref", ref, "--pinned-commit", pin, *extra)

    def unreachable() -> None:
        set_config(tmp_path / "missing.git")

    def hooks(folder: Path) -> None:
        set_config(bare, hooks=folder)

    return SimpleNamespace(tmp_path=tmp_path, work=work, bare=bare, ws=ws, tmp=tmp, clone=clone, sha=sha,
                           push=push, push_m4=push_m4, clone_at=clone_at, run=run, open=open_,
                           unreachable=unreachable, hooks=hooks, gitconfig=gitconfig)


def _changed(result) -> dict:
    data = json.loads(Path(result.json["changed_files"]).read_text(encoding="utf-8"))
    return {f["path"]: f["status"] for f in data["files"]}


# --------------------------------------------------------------------------
# Which sources the helper takes
# --------------------------------------------------------------------------


class TestParseRemote:
    @pytest.mark.parametrize("value", [
        "https://github.com/acme/lib",
        "https://github.com/acme/lib.git",
        "https://github.com/acme/lib/",
        "HTTPS://GitHub.com/acme/lib",
        "ssh://git@github.com:22/acme/lib.git",
        "git@github.com:acme/lib.git",
        "acme/lib",
    ])
    def test_remote_forms(self, value, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert _mod().parse_remote(value) == ("github.com", ("acme",), "lib")

    def test_nested_owner(self):
        assert _mod().parse_remote("https://gitlab.com/g/sub/lib") == ("gitlab.com", ("g", "sub"), "lib")

    @pytest.mark.parametrize("value, parsed", [
        ("https://github.com/acme/.github", ("github.com", ("acme",), ".github")),
        ("git@github-work:acme/lib.git", ("github-work", ("acme",), "lib")),
        ("https://github.com/acme/lib.v2", ("github.com", ("acme",), "lib.v2")),
    ])
    def test_names_with_dots_and_dashes(self, value, parsed):
        assert _mod().parse_remote(value) == parsed

    @pytest.mark.parametrize("value", [
        "https://evil.example/acme/..\\..\\..\\..\\Projects\\app",
        "git://evil.example/acme/..\\..\\x",
        "git@evil.example:acme/..\\..\\..\\x",
        "https://evil.example/acme/C:\\Users\\me\\Projects\\app",
        "https://evil.example/acme/C:/app",
        "https://evil.example/acme/\\Users\\x",
        "https://evil\\..\\..\\x/acme/lib",
        "https://github.com/.../lib",
        "https://github.com/acme/.. /x",
        "https://github.com/acme/li\tb",
    ])
    def test_part_that_is_not_one_folder_name(self, value):
        """On Windows `\\`, `C:` and trailing dots or spaces would move the clone and the tree out of
        their folders: `C:\\Users\\me\\.skf\\workspace\\trees\\skf-tree-...\\..\\..\\..\\..\\Projects\\app` is
        `C:\\Users\\me\\Projects\\app`, which open would then fetch into and check out."""
        assert _mod().parse_remote(value) is None

    @pytest.mark.parametrize("value", [
        "/abs/x", "./x", "../x", "~/x", "C:\\x\\y", "C:/x/y", "file:///x/y", "-x/y", "ext::sh -c x", "",
        "https://github.com/../lib",
    ])
    def test_local_values(self, value):
        assert _mod().parse_remote(value) is None

    def test_existing_relative_folder_is_local(self, tmp_path, monkeypatch):
        (tmp_path / "acme" / "lib").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        assert _mod().parse_remote("acme/lib") is None


# --------------------------------------------------------------------------
# open
# --------------------------------------------------------------------------


def test_clone_on_older_tag_reads_pinned_tag(env):
    """The issue's step 3: create-skill for another skill left the clone at v1."""
    env.clone_at("v2", move_to=env.sha("v1"))
    before = _snapshot(env.clone)
    r = env.open(pin=env.sha("v2"), root=f"{env.clone}/")
    assert r.rc == 0, r.stderr
    assert r.json["status"] == "ready"
    assert r.json["target_commit"] == env.sha("v2")
    tree = Path(r.json["tree"])
    assert (tree / "src" / "extra.py").is_file() and (tree / "scripts" / "release.sh").is_file()
    assert r.json["moved"] is False
    assert r.json["diff_status"] == "ok"
    assert r.json["changed_counts"] == {"added": 0, "modified": 0, "deleted": 0}
    assert _g(env.clone, "rev-parse", "HEAD") == env.sha("v1")
    assert _snapshot(env.clone) == before, "open wrote to the shared clone"


def test_tilde_source_root_matches(env, monkeypatch):
    home = env.tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("SKF_WORKSPACE", "~/ws")
    env.clone_at("v2", dest=home / "ws" / "repos" / "github.com" / "acme" / "lib")
    r = env.open(pin=env.sha("v2"), root="~/ws/repos/github.com/acme/lib")
    assert r.json["status"] == "ready", r.stdout + r.stderr
    assert r.json["clone"] is not None


def _record(monkeypatch) -> list:
    """Record every child the helper starts: (argv, Popen keywords plus the wait's `timeout`)."""
    calls = []
    real = subprocess.Popen

    class Recorder(real):
        def __init__(self, argv, *a, **kw):
            self._recorded = dict(kw)
            calls.append((list(argv), self._recorded))
            super().__init__(argv, *a, **kw)

        def wait(self, timeout=None):
            self._recorded.setdefault("timeout", timeout)
            return super().wait(timeout=timeout)

    monkeypatch.setattr(_mod().subprocess, "Popen", Recorder)
    return calls


def _git_calls(calls) -> list:
    return [(argv, kw) for argv, kw in calls if Path(argv[0]).stem.lower() == "git"]


def _subcommand(argv: list) -> tuple[str | None, int]:
    i = 1
    while i < len(argv):
        token = argv[i]
        if token in ("-c", "-C"):
            i += 2
            continue
        if token.startswith("-"):
            i += 1
            continue
        return token, i
    return None, i


def _fetch_sources(calls, dest: str) -> list[str]:
    """The repository each `fetch` into `dest` read from (the word after `--`)."""
    out = []
    for argv, _ in _git_calls(calls):
        sub, i = _subcommand(argv)
        if sub == "fetch" and argv[-1].endswith(dest):
            out.append(argv[argv.index("--", i) + 1])
    return out


def test_seeds_from_clone_when_it_has_the_commit(env, monkeypatch):
    env.clone_at("v2", move_to=env.sha("v1"))
    calls = _record(monkeypatch)
    code, out = _mod().open_tree(_args("open", "--source-repo", URL, "--source-root", str(env.clone),
                                       "--source-ref", "v2", "--pinned-commit", env.sha("v2")))
    assert code == 0 and out["status"] == "ready"
    sources = _fetch_sources(calls, ":refs/skf/target")
    assert sources and all(Path(s) == env.clone for s in sources), sources
    assert _mod()._rmtree(env.clone)  # git's read-only pack files block a plain rmtree on Windows

    env.clone_at("v1")
    calls.clear()
    code, out = _mod().open_tree(_args("open", "--source-repo", URL, "--source-root", str(env.clone),
                                       "--source-ref", "v2", "--pinned-commit", env.sha("v1")))
    assert code == 0 and out["status"] == "ready"
    assert _fetch_sources(calls, ":refs/skf/target") == [URL]


def test_branch_pinned_sees_upstream(env):
    """The issue's step 4: a skill that follows a branch sees its new commits."""
    m3 = env.sha("main")
    env.clone_at("HEAD")
    m4 = env.push_m4()
    r = env.open(pin=m3, ref="HEAD")
    assert r.json["status"] == "ready", r.stdout + r.stderr
    assert r.json["target_commit"] == m4
    assert r.json["moved"] is True
    changed = _changed(r)
    assert changed["src/core.py"] == "D"
    assert changed["src/core2.py"] == "A"
    assert changed["src/dir sp/é.py"] == "A"
    assert changed[".gitignore"] == "M"


def test_type_change_is_modified(env):
    """A file that becomes a link (git status T) is a modified file."""
    m3 = env.sha("main")
    env.clone_at("HEAD")
    target = env.tmp_path / "link-target.txt"
    _write(target, "src/core.py")
    blob = _g(env.work, "hash-object", "-w", str(target))
    _g(env.work, "update-index", "--cacheinfo", f"120000,{blob},scripts/build.sh")
    _g(env.work, "commit", "-q", "-m", "link")
    _g(env.work, "push", "-q", str(env.bare), "main")
    r = env.open(pin=m3, ref="HEAD")
    assert r.json["status"] == "ready", r.stdout + r.stderr
    assert _changed(r) == {"scripts/build.sh": "M"}
    assert r.json["changed_counts"] == {"added": 0, "modified": 1, "deleted": 0}


def test_head_on_tag_created_clone_is_default_branch(env):
    env.clone_at("v2")
    r = env.open(pin=env.sha("v2"), ref="HEAD")
    assert r.json["target_commit"] == env.sha("main")
    assert r.json["target_commit"] != env.sha("v2")
    assert r.json["ref_kind"] == "head"


def test_target_ref_repins_and_peels_annotated_tag(env):
    env.clone_at("v1")
    r = env.open("--target-ref", "v2", pin=env.sha("v1"), ref="v1")
    assert r.json["status"] == "ready", r.stdout + r.stderr
    assert r.json["target_ref"] == "v2"
    assert r.json["ref_kind"] == "tag"
    assert _g(env.bare, "cat-file", "-t", r.json["target_commit"]) == "commit"
    assert r.json["target_commit"] == env.sha("v2")
    assert r.json["changed_counts"] == {"added": 2, "modified": 2, "deleted": 0}


def test_tag_wins_over_same_named_branch(env):
    _g(env.work, "tag", "rel", env.sha("v1"))
    _g(env.work, "branch", "rel", env.sha("main"))
    _g(env.work, "push", "-q", str(env.bare), "refs/tags/rel", "refs/heads/rel")
    env.clone_at("v2")
    r = env.open("--target-ref", "rel", pin=env.sha("v2"))
    assert r.json["target_commit"] == env.sha("v1")
    assert r.json["ref_kind"] == "tag"


def test_full_sha_target_ref(env):
    env.clone_at("v2")
    m3 = env.sha("main")
    r = env.open("--target-ref", m3, pin=env.sha("v2"))
    assert r.json["status"] == "ready", r.stdout + r.stderr
    assert r.json["ref_kind"] == "commit"
    assert r.json["target_commit"] == m3


@pytest.mark.parametrize("value", ["", "null", "None", "head"])
def test_empty_or_null_ref_means_default_branch(env, value):
    """metadata.json may record no source_ref; init.md §6 passes an empty string."""
    env.clone_at("v2")
    r = env.open(pin=env.sha("v2"), ref=value)
    assert r.json["status"] == "ready", r.stdout + r.stderr
    assert r.json["target_ref"] == "HEAD" and r.json["ref_kind"] == "head"
    assert r.json["target_commit"] == env.sha("main")


def test_unknown_ref_unavailable_leaves_nothing(env):
    env.clone_at("v2")
    r = env.open("--target-ref", "nope", pin=env.sha("v2"))
    assert r.rc == 3
    assert r.json["status"] == "unavailable" and r.json["reason"] == "ref-not-found"
    assert "--target-ref" in r.json["message"]
    assert _trees(env) == []


def test_fetch_failure_leaves_no_tree(env):
    env.clone_at("v2")
    r = env.open("--target-ref", "0123456789abcdef0123456789abcdef01234567", pin=env.sha("v2"))
    assert r.rc == 3 and r.json["reason"] == "fetch-failed", r.stdout + r.stderr
    assert _trees(env) == []


def test_option_like_ref_rejected(env, monkeypatch):
    env.clone_at("v2")
    r = env.run("open", "--source-repo", URL, "--source-root", str(env.clone), "--source-ref", "v2",
                "--pinned-commit", env.sha("v2"), "--target-ref=--upload-pack=x")
    assert r.rc == 3 and r.json["reason"] == "invalid-ref"
    calls = _record(monkeypatch)
    code, out = _mod().open_tree(_args("open", "--source-repo", URL, "--source-root", str(env.clone),
                                       "--source-ref", "v2", "--target-ref=--upload-pack=x"))
    assert code == 3 and out["reason"] == "invalid-ref"
    assert not [argv for argv, _ in _git_calls(calls) if "ls-remote" in argv]


def test_unreachable_reads_pinned_commit_offline(env):
    env.clone_at("v2")
    env.unreachable()
    r = env.open(pin=env.sha("v2"))
    assert r.rc == 0, r.stderr
    assert r.json["status"] == "offline"
    assert r.json["target_commit"] == env.sha("v2")
    assert URL in r.json["message"]
    assert r.json["diff_status"] == "ok"
    assert (Path(r.json["tree"]) / "src" / "extra.py").is_file()


def test_unreachable_without_local_pin_is_unavailable(env):
    env.clone_at("v1")
    env.unreachable()
    r = env.open(pin=env.sha("v2"))
    assert r.rc == 3 and r.json["reason"] == "upstream-unreachable"
    assert _trees(env) == []


def test_unreachable_with_target_ref_is_unavailable(env):
    env.clone_at("v2")
    env.unreachable()
    r = env.open("--target-ref", "v2", pin=env.sha("v2"))
    assert r.rc == 3 and r.json["reason"] == "upstream-unreachable"


def test_fetch_failure_reads_pinned_commit_offline(env, monkeypatch):
    """ls-remote answers but the commit cannot be fetched: read the local pin."""
    env.clone_at("v2")
    mod = _mod()
    real = mod._git

    def no_remote_fetch(cwd, *args, **kw):
        if "fetch" in args and URL in args:
            return 1, b"", "fatal: the remote end hung up unexpectedly"
        return real(cwd, *args, **kw)

    monkeypatch.setattr(mod, "_git", no_remote_fetch)
    code, out = mod.open_tree(_args("open", "--source-repo", URL, "--source-root", str(env.clone),
                                    "--source-ref", "HEAD", "--pinned-commit", env.sha("v2")))
    assert code == 0 and out["status"] == "offline", out
    assert out["target_commit"] == env.sha("v2") and out["ref_kind"] == "pinned"
    assert out["message"].startswith("Could not fetch HEAD")
    assert (Path(out["tree"]) / "src" / "extra.py").is_file()
    code, out = mod.open_tree(_args("open", "--source-repo", URL, "--source-root", str(env.clone),
                                    "--source-ref", "HEAD", "--pinned-commit", env.sha("v2"),
                                    "--target-ref", "HEAD"))
    assert code == 3 and out["reason"] == "fetch-failed", out
    assert len(_trees(env)) == 1


def test_short_pin_matches_by_prefix(env):
    env.clone_at("v2")
    r = env.open(pin=env.sha("v2")[:8])
    assert r.json["moved"] is False
    assert r.json["diff_status"] == "ok"


@pytest.mark.parametrize("pin", ["", "local", "null", " None "])
def test_no_pinned_commit_reads_the_ref_and_moved_is_null(env, pin):
    """metadata.json without a source_commit: init.md §7 shows its own row for `moved` null."""
    env.clone_at("v1")
    r = env.open(pin=pin)
    assert r.rc == 0 and r.json["status"] == "ready", r.stdout + r.stderr
    assert r.json["target_commit"] == env.sha("v2")
    assert r.json["moved"] is None
    assert r.json["diff_status"] == "unavailable"
    assert r.json["changed_files"] is None and r.json["changed_counts"] is None
    assert not (Path(r.json["tree"]).parent / "changed-files.json").exists()
    seven = INIT.read_text(encoding="utf-8").split("### 7. Present Baseline Summary", 1)[1].split("### 8.", 1)[0]
    assert "- `ready` and `{source_moved}` null: `{target_commit} (no pinned commit before this run)`;" in seven


def test_unknown_base_gives_diff_unavailable(env):
    env.clone_at("v2")
    r = env.open(pin="0123456789abcdef0123456789abcdef01234567")
    assert r.json["status"] == "ready", r.stdout + r.stderr
    assert r.json["moved"] is True
    assert r.json["diff_status"] == "unavailable"
    assert r.json["changed_files"] is None and r.json["changed_counts"] is None


def test_missing_clone_reads_upstream_and_creates_nothing(env):
    r = env.open(pin=env.sha("v2"))
    assert r.json["status"] == "ready", r.stdout + r.stderr
    assert Path(r.json["clone"]) == env.clone
    assert not os.path.lexists(env.clone)


def test_foreign_folder_at_workspace_path_left_alone(env):
    other = env.tmp_path / "other"
    other.mkdir()
    _g(other, "init", "-q", "-b", "main")
    _write(other / "x.txt", "x\n")
    _g(other, "add", "x.txt")
    _g(other, "commit", "-q", "-m", "x")
    env.clone.parent.mkdir(parents=True)
    _g(env.tmp_path, "clone", "-q", str(other), str(env.clone))
    head = _g(env.clone, "rev-parse", "HEAD")
    r = env.open(pin=env.sha("v2"))
    assert r.json["status"] == "ready", r.stdout + r.stderr
    assert r.json["clone"] is None
    assert any("is not SKF's clone" in w for w in r.json["warnings"])
    assert _g(env.clone, "rev-parse", "HEAD") == head


@pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="POSIX permissions; root can search any folder")
def test_unsearchable_workspace_folder_is_not_taken_for_skfs_clone(env):
    """os.stat, not pathlib: from Python 3.14 pathlib calls such a folder missing."""
    env.clone_at("v2")
    host = env.ws / "repos" / "github.com"
    os.chmod(host, 0)
    try:
        r = env.open(pin=env.sha("v2"))
        a = _advance(env, target=env.sha("v1"), expect=env.sha("v2"))
    finally:
        os.chmod(host, 0o755)
    assert r.json is not None, r.stderr
    assert r.json["status"] == "ready" and r.json["clone"] is None, r.json
    assert any("is not SKF's clone" in w for w in r.json["warnings"])
    assert a.json["skip_reason"] == "not-a-clone"
    assert _g(env.clone, "rev-parse", "HEAD") == env.sha("v2")


def test_host_letter_case_of_clone_folder_ignored(env):
    """create-skill copies the host as the URL spells it."""
    mixed = "https://GitHub.com/acme/lib"
    with env.gitconfig.open("ab") as fh:
        fh.write(f'[url "{env.bare.as_uri()}"]\n\tinsteadOf = {mixed}\n'.encode("utf-8"))
    dest = env.ws / "repos" / "GitHub.com" / "acme" / "lib"
    env.clone_at("v2", move_to=env.sha("v1"), dest=dest)
    _g(dest, "remote", "set-url", "origin", mixed)
    r = env.run("open", "--source-repo", mixed, "--source-root", str(dest), "--source-ref", "v2",
                "--pinned-commit", env.sha("v2"))
    assert r.json["status"] == "ready", r.stdout + r.stderr
    assert r.json["target_commit"] == env.sha("v2")
    assert r.json["clone"] is not None and _mod()._same_path(r.json["clone"], dest)


def test_origin_compared_without_insteadof(env):
    env.clone_at("v2")
    r = env.open(pin=env.sha("v2"))
    assert r.json["clone"] is not None
    assert r.json["warnings"] == []


def test_relocated_workspace_needs_matching_origin(env):
    old = env.tmp_path / "old" / "repos" / "github.com" / "acme" / "lib"
    env.clone_at("v2", dest=old)
    r = env.open(pin=env.sha("v2"), root=old)
    assert r.json["status"] == "ready", r.stdout + r.stderr
    assert Path(r.json["clone"]) == old
    _g(old, "remote", "set-url", "origin", "https://github.com/other/thing")
    r = env.open(pin=env.sha("v2"), root=old)
    assert r.json["status"] == "skipped" and r.json["skip_reason"] == "not-workspace-clone"


def test_clone_and_tree_paths_stay_in_their_folders(env, monkeypatch):
    """The second guard behind parse_remote: a name that leaves `repos/` or the run folder is not taken."""
    mod = _mod()
    env.clone_at("v2")
    # What a Windows `..\\..\\escape` repository part is there: the tree would be <workspace>/escape.
    parsed = ("github.com", ("acme",), "../../escape")
    monkeypatch.setattr(mod, "parse_remote", lambda value: parsed if value == URL else None)
    code, out = mod.open_tree(_args("open", "--source-repo", URL, "--source-root", str(mod.clone_path(parsed)),
                                    "--source-ref", "v2", "--pinned-commit", env.sha("v2")))
    assert code == 0 and out["status"] == "skipped" and out["skip_reason"] == "not-remote", out
    out = mod.advance(_args("advance", "--clone", str(env.clone), "--source-repo", URL,
                            "--target", env.sha("v1"), "--expect-commit", env.sha("v2")))
    assert out["skip_reason"] == "not-a-clone", out
    assert not os.path.lexists(env.ws / "escape") and _trees(env) == []
    assert _g(env.clone, "rev-parse", "HEAD") == env.sha("v2")
    assert not mod._stays_inside(("github.com", ("..", "..", ".."), "x")), "the clone would leave repos/"
    assert not mod._stays_inside(("github.com", ("acme",), "lib/../x")), "the tree would leave its run folder"
    assert mod._stays_inside(("github.com", ("acme",), "lib"))


@pytest.mark.skipif(os.name == "nt", reason="the shim is a POSIX shell script")
def test_git_shim_in_cwd_never_runs(env):
    """update-skill runs the helper from the project folder, which SKF does not control."""
    env.clone_at("v2")
    shim_dir = env.tmp_path / "shim"
    marker = env.tmp_path / "shim-ran"
    _write(shim_dir / "git", f'#!/bin/sh\necho "$@" >> "{marker.as_posix()}"\nexit 0\n')
    os.chmod(shim_dir / "git", 0o755)
    child = {**os.environ, "PATH": str(shim_dir)}

    def run(*argv: str):
        proc = subprocess.run([sys.executable, str(HELPER), *argv], capture_output=True, encoding="utf-8",
                              env=child, cwd=str(shim_dir), stdin=subprocess.DEVNULL)
        return proc.returncode, json.loads(proc.stdout)

    code, out = run("open", "--source-repo", URL, "--source-root", str(env.clone), "--source-ref", "v2",
                    "--pinned-commit", env.sha("v2"))
    assert (code, out["status"], out["reason"]) == (3, "unavailable", "git-unavailable"), out
    code, out = run("advance", "--clone", str(env.clone), "--source-repo", URL, "--target", env.sha("v1"),
                    "--expect-commit", env.sha("v2"))
    assert (code, out["status"], out["skip_reason"]) == (0, "skipped", "not-a-clone"), out
    assert not marker.exists(), marker.read_text(encoding="utf-8")


def test_local_and_quick_sources_skip(env):
    local = env.tmp_path / "local"
    local.mkdir()
    r = env.run("open", "--source-repo", "./lib", "--source-root", str(local), "--source-ref", "local")
    assert r.json["status"] == "skipped" and r.json["skip_reason"] == "not-remote"
    r = env.run("open", "--source-repo", URL, "--source-root", str(local), "--source-ref", "v2")
    assert r.json["status"] == "skipped" and r.json["skip_reason"] == "not-workspace-clone"
    r = env.run("open", "--source-repo", URL, "--source-root", URL, "--source-ref", "v2")
    assert r.json["status"] == "skipped" and r.json["skip_reason"] == "not-workspace-clone"
    assert _trees(env) == []


def test_tree_unaffected_by_later_clone_checkout(env):
    env.clone_at("v2")
    r = env.open(pin=env.sha("v2"))
    tree = Path(r.json["tree"])
    _g(env.clone, "fetch", "-q", "--depth", "1", "origin", env.sha("v1"))
    _g(env.clone, "checkout", "-q", "--detach", env.sha("v1"))
    assert (tree / "src" / "extra.py").is_file()
    assert _g(tree, "rev-parse", "HEAD") == env.sha("v2")


def test_tree_folder_falls_back_to_temp(env):
    env.clone_at("v2")
    env.ws.mkdir(exist_ok=True)
    (env.ws / "trees").write_bytes(b"not a folder")
    r = env.open(pin=env.sha("v2"))
    assert r.json["status"] == "ready", r.stdout + r.stderr
    assert Path(r.json["tree"]).parent.parent == env.tmp
    assert any("system temp folder" in w for w in r.json["warnings"])


def test_sweep_removes_only_stale_skf_trees(env):
    env.clone_at("v2")
    fresh = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    target = env.tmp_path / "link-target"
    target.mkdir()
    _write(target / "keep.txt", "keep\n")
    made_links = []
    for root in (env.ws / "trees", env.tmp):
        root.mkdir(parents=True, exist_ok=True)
        (root / "skf-tree-20000101T000000Z-abcdefgh").mkdir()
        _write(root / "skf-tree-20000101T000000Z-abcdefgh" / "lib" / "f.txt", "x\n")
        young = root / f"skf-tree-{fresh}-ijklmnop"
        young.mkdir()
        os.utime(young, (946684800, 946684800))
        (root / "keep-me").mkdir()
        link = root / "skf-tree-20000101T000000Z-zzzzzzzz"
        try:
            os.symlink(target, link, target_is_directory=True)
            made_links.append(link)
        except (OSError, NotImplementedError):
            pass
    r = env.open(pin=env.sha("v2"))
    assert r.json["status"] == "ready"
    for root in (env.ws / "trees", env.tmp):
        assert not (root / "skf-tree-20000101T000000Z-abcdefgh").exists()
        assert (root / f"skf-tree-{fresh}-ijklmnop").is_dir()
        assert (root / "keep-me").is_dir()
    for link in made_links:
        assert os.path.lexists(link)
    assert (target / "keep.txt").is_file()


@pytest.mark.skipif(os.name == "nt", reason="the hook is a POSIX shell script")
def test_user_hooks_never_run_in_the_tree(env):
    env.clone_at("v2")
    hooks = env.tmp_path / "hooks"
    marker = env.tmp_path / "hook-ran"
    _write(hooks / "post-checkout", f'#!/bin/sh\necho ran > "{marker.as_posix()}"\n')
    os.chmod(hooks / "post-checkout", 0o755)
    env.hooks(hooks)
    r = env.open(pin=env.sha("v2"))
    assert r.json["status"] == "ready", r.stdout + r.stderr
    assert not marker.exists()


def test_json_files_have_no_crlf(env):
    env.clone_at("v1")
    r = env.open(pin=env.sha("v1"))
    run = Path(r.json["tree"]).parent
    for name in ("run.json", "changed-files.json"):
        data = (run / name).read_bytes()
        assert b"\r\n" not in data
        json.loads(data.decode("utf-8"))
    assert r.stdout.isascii() and r.stdout.count("\n") == 1


def test_inherited_git_env_ignored(env):
    env.clone_at("v2")
    decoy = env.tmp_path / "decoy"
    decoy.mkdir()
    _g(decoy, "init", "-q", "-b", "main")
    _write(decoy / "d.txt", "d\n")
    _g(decoy, "add", "d.txt")
    _g(decoy, "commit", "-q", "-m", "d")
    head = _g(decoy, "rev-parse", "HEAD")
    index = decoy / ".git" / "index"
    mtime = index.stat().st_mtime_ns
    r = env.run("open", "--source-repo", URL, "--source-root", str(env.clone), "--source-ref", "v2",
                "--pinned-commit", env.sha("v2"),
                extra_env={"GIT_DIR": str(decoy / ".git"), "GIT_WORK_TREE": str(decoy),
                           "GIT_INDEX_FILE": str(index)})
    assert r.json["status"] == "ready", r.stdout + r.stderr
    assert r.json["target_commit"] == env.sha("v2")
    assert (Path(r.json["tree"]) / "src" / "extra.py").is_file()
    assert _g(decoy, "rev-parse", "HEAD") == head
    assert index.stat().st_mtime_ns == mtime


def test_git_child_env_and_argv(env, monkeypatch):
    m3 = env.sha("main")
    env.clone_at("HEAD")
    m4 = env.push_m4()
    v2 = env.sha("v2")
    monkeypatch.setenv("GIT_DIR", str(env.tmp_path / "nowhere"))
    calls = _record(monkeypatch)
    code, out = _mod().open_tree(_args("open", "--source-repo", URL, "--source-root", str(env.clone),
                                       "--source-ref", "HEAD", "--pinned-commit", m3))
    assert code == 0 and out["status"] == "ready" and out["moved"] is True
    _mod().advance(_args("advance", "--clone", str(env.clone), "--source-repo", URL, "--target", m4,
                         "--expect-commit", m3, "--tree", out["tree"], "--drift-helper", str(DRIFT)))
    assert _mod()._rmtree(env.clone)  # git's read-only pack files block a plain rmtree on Windows
    _mod().advance(_args("advance", "--clone", str(env.clone), "--source-repo", URL,
                         "--target", v2, "--target-ref", "v2"))
    git = _git_calls(calls)
    seen = set()
    for argv, kw in git:
        child = kw["env"]
        assert not set(child) & set(LOCATION_VARS), argv
        assert child["LC_ALL"] == "C" and child["GIT_TERMINAL_PROMPT"] == "0"
        assert child["GCM_INTERACTIVE"] == "never"
        assert kw["stdin"] is subprocess.DEVNULL
        # Files, not pipes, and a process group of its own: see _run.
        assert hasattr(kw["stdout"], "fileno") and hasattr(kw["stderr"], "fileno"), argv
        if os.name == "nt":
            assert kw["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP, argv
        else:
            assert kw["start_new_session"] is True, argv
        assert argv[1:3] == ["-c", f"core.hooksPath={os.devnull}"]
        sub, i = _subcommand(argv)
        seen.add(sub)
        if sub in ("checkout", "clone"):
            head = argv[:i]
            assert "core.longpaths=true" in head and "advice.detachedHead=false" in head, argv
        if sub in ("fetch", "ls-remote", "clone"):
            assert "--" in argv[i:], argv
    assert {"ls-remote", "fetch", "checkout", "clone", "diff"} <= seen, seen


# --------------------------------------------------------------------------
# Time limit
# --------------------------------------------------------------------------


def test_time_limit_is_shared_by_every_call(monkeypatch):
    mod = _mod()
    now = [1000.0]
    monkeypatch.setattr(mod, "time", SimpleNamespace(monotonic=lambda: now[0], sleep=time.sleep))
    try:
        mod._start_clock(100)
        assert mod._cap(600) == 95 and mod._cap(600, network=True) == 85
        assert mod._cap(30) == 30 and not mod._expired()
        now[0] += 90
        assert mod._cap(600) == 5 and mod._cap(600, network=True) is None
        assert mod._expired() and not mod._out_of_time()
        now[0] += 5
        assert mod._cap(600) is None and mod._out_of_time()
        assert mod._git(".", "--version") == (-1, b"", "timeout")
    finally:
        mod._start_clock(None)
    assert mod._cap(600, network=True) == 600
    assert _args("open").timeout == _args("advance", "--clone", "c", "--source-repo", URL,
                                          "--target", "x").timeout == 100


def _grandchild_script(marker: Path) -> str:
    """A child that starts a grandchild sharing its output, as git starts ssh.

    The grandchild gets the marker path as an argument, not inside its
    code, so a Windows path's backslashes cannot break the code.
    """
    return ("import subprocess, sys, time\n"
            "subprocess.Popen([sys.executable, '-c', 'import pathlib, sys, time; time.sleep(3); "
            "pathlib.Path(sys.argv[1]).write_text(\"x\")', sys.argv[1]])\n"
            "time.sleep(60)\n")


def test_a_stopped_call_takes_what_it_started_with_it(tmp_path):
    """POSIX stops the process group, Windows runs taskkill /T: the grandchild never survives."""
    marker = tmp_path / "grandchild-survived"
    start = time.monotonic()
    returncode, _out, _err, killed = _mod()._run([sys.executable, "-c", _grandchild_script(marker), str(marker)], 1)
    assert returncode is None and killed is (os.name == "nt")
    assert time.monotonic() - start < 10
    time.sleep(4)
    assert not marker.exists()


@pytest.mark.skipif(os.name == "nt", reason="SIGTERM is POSIX")
def test_a_stopped_call_gets_sigterm_first(tmp_path):
    """git removes its lock files on SIGTERM; SIGKILL would leave them."""
    cleaned = tmp_path / "cleaned"
    code = ("import pathlib, signal, sys, time\n"
            "def bye(*_):\n"
            "    pathlib.Path(sys.argv[1]).write_text('x')\n"
            "    sys.exit(1)\n"
            "signal.signal(signal.SIGTERM, bye)\n"
            "print('ready', flush=True)\n"
            "time.sleep(60)\n")
    returncode, out, _err, killed = _mod()._run([sys.executable, "-c", code, str(cleaned)], 2)
    assert returncode is None and out.strip() == b"ready"
    assert cleaned.is_file() and killed is False


@pytest.mark.skipif(os.name == "nt", reason="SIGTERM is POSIX")
def test_a_call_that_outlives_sigterm_is_killed_and_says_so(tmp_path):
    """SIGKILL leaves git's lock files: only then may the helper remove one."""
    code = ("import signal, time\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "print('ready', flush=True)\n"
            "time.sleep(60)\n")
    start = time.monotonic()
    returncode, out, _err, killed = _mod()._run([sys.executable, "-c", code], 2)
    assert returncode is None and out.strip() == b"ready" and killed is True
    assert time.monotonic() - start < 10


def test_windows_stop_uses_taskkill_tree(monkeypatch):
    calls = []
    mod = _mod()
    monkeypatch.setattr(mod, "_resolve_outside_cwd", lambda name: "taskkill" if name == "taskkill" else None)
    monkeypatch.setattr(mod.subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw.get("timeout"))))

    class Proc:
        pid = 4242
        killed = False

        def kill(self):
            self.killed = True

        def wait(self, timeout=None):
            return 1

    proc = Proc()
    mod._stop(proc, windows=True)
    assert calls == [(["taskkill", "/F", "/T", "/PID", "4242"], mod.KILL_WAIT_SEC)] and proc.killed


@pytest.mark.skipif(os.name == "nt", reason="the stand-in git is a POSIX shell script")
def test_a_stopped_git_never_waits_for_its_transport(monkeypatch, tmp_path):
    """Windows: killing git leaves its ssh or https transport running, holding what git's stderr was.

    This runs Windows' side on POSIX: subprocess.run reads every pipe to its
    end after the kill, as CPython does on Windows, and the stop reaches
    git alone. A git call that read its output through pipes would wait
    for the transport; the helper's temporary files do not.
    """
    mod = _mod()
    fake_git = tmp_path / "git"
    fake_git.write_bytes(b"#!/bin/sh\nsleep 6 &\nexec sleep 30\n")
    os.chmod(fake_git, 0o755)
    real_run = subprocess.run

    def windows_run(argv, *a, timeout=None, capture_output=False, **kw):
        if capture_output:
            kw.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with subprocess.Popen(argv, *a, **kw) as proc:
            try:
                out, err = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                raise
        return subprocess.CompletedProcess(argv, proc.returncode, out, err)

    def stop_git_only(proc, windows=False):
        proc.kill()
        proc.wait()
        return True

    monkeypatch.setattr(mod.subprocess, "run", windows_run)
    monkeypatch.setattr(mod, "_stop", stop_git_only)
    monkeypatch.setattr(mod, "_resolve_outside_cwd", lambda name: str(fake_git))
    start = time.monotonic()
    res = mod._git(tmp_path, "fetch", timeout=1)
    elapsed = time.monotonic() - start
    monkeypatch.setattr(mod.subprocess, "run", real_run)
    assert res is not None and res[2] == "timeout"
    assert res[0] == mod.KILLED
    assert elapsed < 4, f"the stopped git call took {elapsed:.1f}s"


def test_open_stops_within_its_time_limit(env):
    env.clone_at("v2")
    r = env.open("--timeout", "0", pin=env.sha("v2"))
    assert r.rc == 3, r.stdout + r.stderr
    assert r.json["status"] == "unavailable" and r.json["reason"] == "timed-out"
    assert "0-second time limit" in r.json["message"]
    assert _trees(env) == []


def test_every_git_call_fits_the_time_limit(env, monkeypatch):
    m3 = env.sha("main")
    env.clone_at("HEAD")
    m4 = env.push_m4()
    calls = _record(monkeypatch)
    code, out = _mod().open_tree(_args("open", "--source-repo", URL, "--source-root", str(env.clone),
                                       "--source-ref", "HEAD", "--pinned-commit", m3, "--timeout", "40"))
    assert code == 0 and out["status"] == "ready", out
    assert_advanced = _mod().advance(_args("advance", "--clone", str(env.clone), "--source-repo", URL,
                                           "--target", m4, "--expect-commit", m3, "--tree", out["tree"],
                                           "--drift-helper", str(DRIFT), "--timeout", "40"))
    assert assert_advanced["status"] == "advanced", assert_advanced
    network = local = 0
    for argv, kw in calls:
        assert kw["timeout"] <= 40, argv
        if Path(argv[0]).stem.lower() == "git":
            sub, i = _subcommand(argv)
            if sub == "ls-remote" or (sub == "fetch" and URL in argv):
                network += 1
                assert kw["timeout"] <= 25, argv
            else:
                local += 1
    assert network and local


# --------------------------------------------------------------------------
# advance
# --------------------------------------------------------------------------


def _advance(env, *extra: str, target: str, expect: str = "", drift: bool = True, tree: str | None = None):
    argv = ["advance", "--clone", str(env.clone), "--source-repo", URL, "--target", target]
    if expect:
        argv += ["--expect-commit", expect]
    if tree:
        argv += ["--tree", tree]
    if drift:
        argv += ["--drift-helper", str(DRIFT)]
    return env.run(*argv, *extra)


def _m4_tree(env, m3: str) -> str:
    """A run tree at m4, built while upstream is reachable."""
    r = env.open(pin=m3, ref="HEAD")
    assert r.json["status"] == "ready", r.stdout + r.stderr
    return r.json["tree"]


class TestAdvance:
    def test_advances_clone_from_old_pin(self, env):
        m3 = env.sha("main")
        env.clone_at("HEAD")
        m4 = env.push_m4()
        tree = _m4_tree(env, m3)
        r = _advance(env, "--hygiene-helper", str(HYGIENE), target=m4, expect=m3, tree=tree)
        assert r.rc == 0, r.stderr
        assert r.json["status"] == "advanced", r.json
        assert r.json["lock"] == "held" and r.json["hygiene"] == "ran"
        assert _g(env.clone, "rev-parse", "HEAD") == m4 == r.json["head_sha"]
        exclude = (env.clone / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        assert ".cocoindex_code/" in exclude and "/.skf-workspace.lock" in exclude
        assert _g(env.clone, "status", "--porcelain") == ""

    def test_noop_at_target(self, env):
        env.clone_at("v2")
        reflog = _g(env.clone, "reflog").splitlines()
        r = _advance(env, target=env.sha("v2"), expect=env.sha("v1"))
        assert r.json["status"] == "ok"
        assert _g(env.clone, "reflog").splitlines() == reflog

    def test_leaves_clone_another_run_moved(self, env):
        m3 = env.sha("main")
        env.clone_at("v1")
        m4 = env.push_m4()
        r = _advance(env, target=m4, expect=m3)
        assert r.json["status"] == "skipped" and r.json["skip_reason"] == "head-moved"
        assert _g(env.clone, "rev-parse", "HEAD") == env.sha("v1")

    def test_leaves_tracked_changes_but_ignores_untracked(self, env):
        m3 = env.sha("main")
        env.clone_at("HEAD")
        m4 = env.push_m4()
        tree = _m4_tree(env, m3)
        _write(env.clone / "scripts" / "build.sh", "echo edited\n")
        r = _advance(env, target=m4, expect=m3, tree=tree)
        assert r.json["status"] == "skipped" and r.json["skip_reason"] == "local-changes"
        assert (env.clone / "scripts" / "build.sh").read_text(encoding="utf-8") == "echo edited\n"
        assert _g(env.clone, "rev-parse", "HEAD") == m3
        _g(env.clone, "checkout", "-q", "--", "scripts/build.sh")
        _write(env.clone / ".DS_Store", "finder\n")
        r = _advance(env, target=m4, expect=m3, tree=tree)
        assert r.json["status"] == "advanced", r.json
        assert (env.clone / ".DS_Store").is_file()

    def test_hygiene_runs_before_fetch_and_checkout(self, env, monkeypatch):
        m3 = env.sha("main")
        env.clone_at("HEAD")
        m4 = env.push_m4()
        tree = _m4_tree(env, m3)
        calls = _record(monkeypatch)
        out = _mod().advance(_args("advance", "--clone", str(env.clone), "--source-repo", URL, "--target", m4,
                                   "--expect-commit", m3, "--tree", tree, "--hygiene-helper", str(HYGIENE),
                                   "--drift-helper", str(DRIFT)))
        assert out["status"] == "advanced", out
        order = []
        for argv, _ in calls:
            if len(argv) > 1 and Path(argv[1]) == HYGIENE:
                order.append("hygiene")
            elif Path(argv[0]).stem.lower() == "git" and _subcommand(argv)[0] in ("fetch", "checkout"):
                order.append(_subcommand(argv)[0])
        assert order[0] == "hygiene" and {"fetch", "checkout"} <= set(order), order

    def test_hygiene_restores_ccc_gitignore(self, env):
        m3 = env.sha("main")
        env.clone_at("HEAD")
        m4 = env.push_m4()
        tree = _m4_tree(env, m3)
        gitignore = env.clone / ".gitignore"
        edited = gitignore.read_text(encoding="utf-8") + CCC_BLOCK
        gitignore.write_bytes(edited.encode("utf-8"))
        r = _advance(env, target=m4, expect=m3, tree=tree)
        assert r.json["status"] == "skipped" and r.json["skip_reason"] == "local-changes"
        assert gitignore.read_text(encoding="utf-8") == edited
        r = _advance(env, "--hygiene-helper", str(HYGIENE), target=m4, expect=m3, tree=tree)
        assert r.json["status"] == "advanced", r.json
        assert gitignore.read_bytes() == _g(env.clone, "show", "HEAD:.gitignore").encode("utf-8") + b"\n"

    def test_busy_lock_skips(self, env):
        m3 = env.sha("main")
        env.clone_at("HEAD")
        m4 = env.push_m4()
        lock = env.clone / ".skf-workspace.lock"
        holder = (
            "import importlib.util, os, sys, time\n"
            f"spec = importlib.util.spec_from_file_location('m', {str(HELPER)!r})\n"
            "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
            f"fd = os.open({str(lock)!r}, os.O_RDWR | os.O_CREAT, 0o644)\n"
            "m._acquire_lock(fd)\n"
            "print('locked', flush=True)\n"
            "time.sleep(3)\n"
        )
        child = subprocess.Popen([sys.executable, "-c", holder], stdout=subprocess.PIPE, text=True)
        try:
            assert child.stdout.readline().strip() == "locked"
            r = _advance(env, "--lock-timeout", "0.5", target=m4, expect=m3)
        finally:
            child.wait(timeout=30)
        assert r.json["status"] == "skipped" and r.json["skip_reason"] == "lock-busy"
        assert r.json["lock"] == "busy"
        assert _g(env.clone, "rev-parse", "HEAD") == m3

    @pytest.mark.skipif(shutil.which("flock") is None, reason="no flock binary")
    def test_lock_excludes_flock_binary(self, env):
        m3 = env.sha("main")
        env.clone_at("HEAD")
        m4 = env.push_m4()
        lock = env.clone / ".skf-workspace.lock"
        child = subprocess.Popen(["flock", "-x", str(lock), "-c", "echo locked; sleep 3"],
                                 stdout=subprocess.PIPE, text=True)
        try:
            assert child.stdout.readline().strip() == "locked"
            r = _advance(env, "--lock-timeout", "0.5", target=m4, expect=m3)
        finally:
            child.wait(timeout=30)
        assert r.json["skip_reason"] == "lock-busy"

    def test_recreates_missing_clone(self, env):
        v2 = env.sha("v2")
        r = env.run("advance", "--clone", str(env.clone), "--source-repo", URL, "--target", v2,
                    "--target-ref", "v2")
        assert r.rc == 0, r.stderr
        assert r.json["created"] is True
        assert r.json["status"] == "ok"
        assert _g(env.clone, "rev-parse", "HEAD") == v2
        assert _g(env.clone, "config", "--get", "remote.origin.fetch") == "+refs/tags/v2:refs/tags/v2"
        assert (env.clone / ".skf-workspace.lock").is_file()

    def test_missing_clone_then_checks_out_target(self, env):
        """The new clone lands on the default branch; the target is an older commit."""
        m3 = env.sha("main")
        m4 = env.push_m4()
        r = env.run("advance", "--clone", str(env.clone), "--source-repo", URL, "--target", m3,
                    "--target-ref", m3)
        assert r.rc == 0, r.stderr
        assert r.json["created"] is True
        assert r.json["status"] == "advanced", r.json
        assert _g(env.clone, "rev-parse", "HEAD") == m3 == r.json["head_sha"] != m4

    def test_time_limit_leaves_clone_and_says_so(self, env):
        m3 = env.sha("main")
        env.clone_at("HEAD")
        m4 = env.push_m4()
        tree = _m4_tree(env, m3)
        r = _advance(env, "--timeout", "0", target=m4, expect=m3, tree=tree)
        assert r.rc == 0, r.stderr
        assert r.json["status"] == "skipped" and r.json["skip_reason"] == "timed-out", r.json
        assert r.json["head_sha"] == m3
        assert any("time limit" in w for w in r.json["warnings"])
        assert _g(env.clone, "rev-parse", "HEAD") == m3
        r = _advance(env, "--timeout", "15", target=m4, expect=m3, tree=tree)
        assert r.json["status"] == "skipped" and r.json["skip_reason"] == "timed-out", r.json
        has_m4 = subprocess.run(["git", "-C", str(env.clone), "cat-file", "-e", f"{m4}^{{commit}}"],
                                capture_output=True, env=_env(), stdin=subprocess.DEVNULL)
        assert has_m4.returncode != 0, "a fetch started in the shared clone without the local reserve"
        r = _advance(env, "--timeout", "40", target=m4, expect=m3, tree=tree)
        assert r.json["status"] == "advanced", r.json

    @pytest.mark.skipif(os.name == "nt", reason="the slow filter is a POSIX shell script")
    @pytest.mark.parametrize("stop", ["sigterm", "forced"])
    def test_checkout_stopped_part_way_leaves_no_lock_or_ref(self, env, monkeypatch, stop):
        """The limit stops the checkout in the clone: no index.lock or refs/skf/advance stays behind.

        A smudge filter stands in for a slow checkout (git-lfs, a large diff
        on a slow disk). `forced` stops git the way taskkill /F does on
        Windows, so git cannot remove its own index.lock.
        """
        mod = _mod()
        m3 = env.sha("main")
        env.clone_at("HEAD")
        slow = env.tmp_path / "slow-smudge"
        _write(slow, '#!/bin/sh\nif [ -n "$SKF_TEST_SLOW_SMUDGE" ]; then sleep 30; fi\nexec cat\n')
        os.chmod(slow, 0o755)
        with env.gitconfig.open("ab") as fh:
            fh.write(f'[filter "slow"]\n\tsmudge = {_config_value(slow)}\n'.encode("utf-8"))
        target = env.push({".gitattributes": "*.bin filter=slow\n", "data.bin": "payload\n",
                           "src/core.py": "def a(): pass\n"}, "slow")
        tree = _m4_tree(env, m3)
        monkeypatch.setenv("SKF_TEST_SLOW_SMUDGE", "1")
        monkeypatch.setattr(mod, "NETWORK_RESERVE_SEC", 1.0)
        monkeypatch.setattr(mod, "FINAL_READ_SEC", 0.5)
        if stop == "forced":
            def forced(proc, windows=False):
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                return True

            monkeypatch.setattr(mod, "_stop", forced)
        out = mod.advance(_args("advance", "--clone", str(env.clone), "--source-repo", URL, "--target", target,
                                "--expect-commit", m3, "--tree", tree, "--drift-helper", str(DRIFT),
                                "--timeout", "5"))
        assert out["status"] == "skipped" and out["skip_reason"] == "checkout-interrupted", out
        assert out["head_sha"] == m3 and _g(env.clone, "rev-parse", "HEAD") == m3
        assert not os.path.lexists(env.clone / ".git" / "index.lock")
        assert _g(env.clone, "for-each-ref", "refs/skf") == ""
        finish = [w for w in out["warnings"] if "checkout --force --detach" in w]
        assert len(finish) == 1, out["warnings"]
        monkeypatch.delenv("SKF_TEST_SLOW_SMUDGE")
        # No ref keeps the target in the clone any more, so a gc may prune it before the user acts.
        _g(env.clone, "gc", "--quiet", "--prune=now")
        pruned = subprocess.run(["git", "-C", str(env.clone), "cat-file", "-e", f"{target}^{{commit}}"],
                                capture_output=True, env=_env(), stdin=subprocess.DEVNULL)
        assert pruned.returncode != 0, "the gc left the target commit in the clone"
        commands = finish[0][finish[0].index("these commands finish it: ") + len("these commands finish it: "):]
        fetch, checkout = commands.split(" and then ")
        assert shlex.split(fetch)[3:] == ["fetch", "--depth", "1", "origin", target], fetch
        for command in (fetch, checkout):
            subprocess.run(shlex.split(command), check=True, capture_output=True, env=_env(),
                           stdin=subprocess.DEVNULL)
        assert _g(env.clone, "rev-parse", "HEAD") == target
        assert _g(env.clone, "status", "--porcelain") == "?? .skf-workspace.lock"

    @pytest.mark.parametrize("spent", [False, True], ids=["time-left", "time-spent"])
    @pytest.mark.parametrize("with_tree", [True, False], ids=["from-tree", "from-remote"])
    def test_fetch_stopped_by_the_limit_leaves_no_lock_or_ref(self, env, monkeypatch, with_tree, spent):
        """git holds .git/shallow.lock through a --depth fetch; a forced stop leaves it.

        `time-spent`: the stop used up the limit, so no limited call can
        start afterwards and the ref must still go.
        """
        mod = _mod()
        m3 = env.sha("main")
        env.clone_at("HEAD")
        m4 = env.push_m4()
        tree = _m4_tree(env, m3)
        real = mod._git
        lock = env.clone / ".git" / "shallow.lock"

        def stopped_fetch(cwd, *args, **kw):
            # Only a fetch the limit lets start gets stopped; the others never start.
            if "fetch" in args and Path(cwd) == env.clone and mod._cap(1.0, kw.get("network", False)) is not None:
                real(cwd, "update-ref", mod.ADVANCE_REF, m3)
                lock.write_bytes(b"")
                if spent:
                    monkeypatch.setattr(mod, "_deadline", time.monotonic() + 1)
                return mod.KILLED, b"", "timeout"
            return real(cwd, *args, **kw)

        monkeypatch.setattr(mod, "_git", stopped_fetch)
        argv = ["advance", "--clone", str(env.clone), "--source-repo", URL, "--target", m4,
                "--expect-commit", m3, "--drift-helper", str(DRIFT)]
        out = mod.advance(_args(*argv, *(["--tree", tree] if with_tree else [])))
        assert out["skip_reason"] == ("timed-out" if spent else "target-missing"), out
        assert not os.path.lexists(lock)
        assert _g(env.clone, "for-each-ref", "refs/skf") == ""
        assert _g(env.clone, "rev-parse", "HEAD") == m3

    def test_checkout_stopped_after_it_finished_is_advanced(self, env, monkeypatch):
        """git moves HEAD last, so a clone at the target after a stop holds the whole checkout."""
        mod = _mod()
        m3 = env.sha("main")
        env.clone_at("HEAD")
        m4 = env.push_m4()
        tree = _m4_tree(env, m3)
        real = mod._git

        def finished_then_stopped(cwd, *args, **kw):
            res = real(cwd, *args, **kw)
            return (mod.STOPPED, b"", "timeout") if "checkout" in args else res

        monkeypatch.setattr(mod, "_git", finished_then_stopped)
        out = mod.advance(_args("advance", "--clone", str(env.clone), "--source-repo", URL, "--target", m4,
                                "--expect-commit", m3, "--tree", tree, "--drift-helper", str(DRIFT)))
        assert out["status"] == "advanced" and out["head_sha"] == m4, out
        assert not [w for w in out["warnings"] if "checkout --force" in w]

    def test_lock_left_by_another_git_is_kept(self, tmp_path):
        """Only a call the limit killed left the lock: one that never started, failed or ended on SIGTERM did not."""
        mod = _mod()
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        lock = git_dir / "index.lock"
        lock.write_bytes(b"")
        warnings = []
        # STOPPED: SIGTERM let the stopped git remove its lock, so this one is another git's.
        for res in (None, (-1, b"", "timeout"), (128, b"", "fatal: Unable to create 'index.lock': File exists."),
                    (mod.STOPPED, b"", "timeout")):
            mod._clear_lock(tmp_path, res, "index.lock", warnings)
            assert lock.is_file(), res
        mod._clear_lock(tmp_path, (mod.KILLED, b"", "timeout"), "index.lock", warnings)
        assert not lock.exists() and warnings == []

    def test_limit_spent_after_the_fetch_leaves_no_ref(self, env, monkeypatch):
        """The fetch wrote refs/skf/advance, then too little time is left to start the checkout."""
        mod = _mod()
        m3 = env.sha("main")
        env.clone_at("HEAD")
        m4 = env.push_m4()
        tree = _m4_tree(env, m3)
        real = mod._git

        def fetch_then_spend(cwd, *args, **kw):
            res = real(cwd, *args, **kw)
            if "fetch" in args and Path(cwd) == env.clone:
                assert _g(env.clone, "for-each-ref", "refs/skf") != ""
                # Local calls may still start; a network call or the checkout may not.
                monkeypatch.setattr(mod, "_deadline", time.monotonic()
                                    + (mod.FINAL_READ_SEC + mod.NETWORK_RESERVE_SEC) / 2)
            return res

        monkeypatch.setattr(mod, "_git", fetch_then_spend)
        out = mod.advance(_args("advance", "--clone", str(env.clone), "--source-repo", URL, "--target", m4,
                                "--expect-commit", m3, "--tree", tree, "--drift-helper", str(DRIFT)))
        assert out["skip_reason"] == "timed-out", out
        assert _g(env.clone, "for-each-ref", "refs/skf") == ""
        assert _g(env.clone, "rev-parse", "HEAD") == m3

    @pytest.mark.parametrize("given", ["tree", "run-folder"])
    def test_takes_target_from_tree_offline(self, env, given):
        """--tree takes the run folder too: an agent binds it, since changed-files.json sits there."""
        m3 = env.sha("main")
        env.clone_at("HEAD")
        m4 = env.push_m4()
        tree = _m4_tree(env, m3)
        env.unreachable()
        r = _advance(env, target=m4, expect=m3, tree=tree if given == "tree" else str(Path(tree).parent))
        assert r.json["status"] == "advanced", r.json
        assert _g(env.clone, "rev-parse", "HEAD") == m4

    def test_never_forces(self, env):
        m3 = env.sha("main")
        env.clone_at("HEAD")
        m4 = env.push_m4()
        tree = _m4_tree(env, m3)
        _write(env.clone / "src" / "core2.py", "mine\n")
        r = _advance(env, target=m4, expect=m3, tree=tree)
        assert r.json["status"] == "skipped" and r.json["skip_reason"] == "checkout-failed"
        assert (env.clone / "src" / "core2.py").read_text(encoding="utf-8") == "mine\n"
        assert _g(env.clone, "rev-parse", "HEAD") == m3

    def test_missing_drift_helper_is_unverified(self, env):
        m3 = env.sha("main")
        env.clone_at("HEAD")
        m4 = env.push_m4()
        r = _advance(env, target=m4, expect=m3, drift=False)
        assert r.json["skip_reason"] == "head-unverified"
        r = _advance(env, "--drift-helper", str(env.tmp_path / "nope.py"), target=m4, expect=m3, drift=False)
        assert r.json["skip_reason"] == "head-unverified"
        assert _g(env.clone, "rev-parse", "HEAD") == m3

    def test_drift_helper_usage_exit_2_is_not_mismatch(self, env):
        m3 = env.sha("main")
        env.clone_at("HEAD")
        m4 = env.push_m4()
        stub = env.tmp_path / "stub.py"
        stub.write_bytes(b"import sys\nsys.exit(2)\n")
        r = _advance(env, "--drift-helper", str(stub), target=m4, expect=m3, drift=False)
        assert r.json["skip_reason"] == "head-unverified"

    def test_invalid_target_and_foreign_clone(self, env):
        env.clone_at("v2")
        r = _advance(env, target="abc", expect=env.sha("v2"))
        assert r.json["skip_reason"] == "invalid-target"
        _g(env.clone, "remote", "set-url", "origin", "https://github.com/other/thing")
        r = _advance(env, target=env.sha("v1"), expect=env.sha("v2"))
        assert r.json["skip_reason"] == "not-a-clone"


# --------------------------------------------------------------------------
# close
# --------------------------------------------------------------------------


class TestClose:
    def test_removes_run_folder(self, env):
        env.clone_at("v2")
        r = env.open(pin=env.sha("v2"))
        run = Path(r.json["tree"]).parent
        c = env.run("close", "--tree", r.json["tree"])
        assert c.rc == 0 and c.json["status"] == "removed"
        assert not os.path.lexists(run)

    def test_rm_handler_clears_readonly_and_retries(self, tmp_path):
        f = tmp_path / "ro.pack"
        f.write_bytes(b"x")
        os.chmod(f, 0o444)
        seen = []

        def func(p):
            seen.append((p, os.access(p, os.W_OK)))

        _mod()._on_rm_error(func, str(f), None)
        assert seen == [(str(f), True)]

    @pytest.mark.parametrize("path, long", [
        ("C:\\Users\\me\\.skf\\workspace\\trees\\skf-tree-x", "\\\\?\\C:\\Users\\me\\.skf\\workspace\\trees\\skf-tree-x"),
        ("\\\\server\\share\\trees\\skf-tree-x", "\\\\?\\UNC\\server\\share\\trees\\skf-tree-x"),
        ("\\\\?\\C:\\trees\\skf-tree-x", "\\\\?\\C:\\trees\\skf-tree-x"),
    ])
    def test_long_path_forms(self, path, long):
        assert _mod()._long_path(path) == long

    def test_windows_removal_goes_through_the_long_path(self, tmp_path, monkeypatch):
        """Past MAX_PATH, where Windows long paths are off, only the `\\\\?\\` form removes the deep files
        a core.longpaths checkout wrote, so close and the seven-day sweep would leave them for good."""
        mod = _mod()
        run = tmp_path / "skf-tree-20260101T000000Z-aaaaaaaa"
        _write(run / "lib" / "f.txt", "x\n")
        seen = []
        monkeypatch.setattr(mod.shutil, "rmtree", lambda target, **kw: seen.append(target))
        mod._rmtree(run, windows=True)
        assert seen == [mod._long_path(os.path.abspath(run))] and seen[0].startswith("\\\\?\\")
        mod._rmtree(run, windows=False)
        assert seen[1] == run
        monkeypatch.undo()
        assert mod._rmtree(run) and not os.path.lexists(run)

    @pytest.mark.skipif(os.name != "nt", reason="MAX_PATH is Windows'")
    def test_removes_files_past_max_path(self, tmp_path):
        run = tmp_path / "skf-tree-20260101T000000Z-aaaaaaaa"
        deep = _mod()._long_path(os.path.abspath(run / "lib" / ("d" * 120) / ("e" * 120) / ("f" * 40)))
        os.makedirs(deep)
        with open(os.path.join(deep, "g.txt"), "wb") as fh:
            fh.write(b"x")
        assert _mod()._rmtree(run) and not os.path.lexists(run)

    def test_refuses_foreign_paths(self, env):
        def record(run: Path, tree: str) -> None:
            run.mkdir(parents=True)
            (run / "lib").mkdir()
            (run / "run.json").write_bytes(json.dumps({"tool": "skf-source-tree", "tree": tree}).encode("utf-8"))

        plain = env.tmp_path / "plain"
        record(plain, str(plain / "lib"))
        bare = env.tmp_path / "skf-tree-20260101T000000Z-aaaaaaaa"
        bare.mkdir()
        (bare / "lib").mkdir()
        other = env.tmp_path / "skf-tree-20260101T000000Z-bbbbbbbb"
        record(other, str(env.tmp_path / "elsewhere" / "lib"))
        cases = [plain, bare, other]
        real = env.tmp_path / "real-run"
        link = env.tmp_path / "skf-tree-20260101T000000Z-cccccccc"
        record(real, str(link / "lib"))
        try:
            os.symlink(real, link, target_is_directory=True)
            cases.append(link)
        except (OSError, NotImplementedError):
            pass
        for run in cases:
            c = env.run("close", "--tree", str(run / "lib"))
            assert c.rc == 0 and c.json["status"] == "refused", (run, c.json)
            assert (run / "lib").is_dir()
        assert (real / "run.json").is_file()

    def test_missing_is_missing(self, env):
        env.clone_at("v2")
        r = env.open(pin=env.sha("v2"))
        assert env.run("close", "--tree", r.json["tree"]).json["status"] == "removed"
        c = env.run("close", "--tree", r.json["tree"])
        assert c.rc == 0 and c.json["status"] == "missing"
        c = env.run("close", "--tree", str(Path(r.json["tree"]).parent))
        assert c.rc == 0 and c.json["status"] == "missing"

    def test_takes_the_run_folder(self, env):
        """A live run bound the run folder, where changed-files.json sits, and close refused it."""
        env.clone_at("v2")
        r = env.open(pin=env.sha("v2"))
        run = Path(r.json["tree"]).parent
        assert (run / "changed-files.json").is_file()
        c = env.run("close", "--tree", f"{run}{os.sep}")
        assert c.rc == 0 and c.json["status"] == "removed", c.json
        assert not os.path.lexists(run)

    def test_refuses_a_run_folder_whose_record_is_not_its_own(self, env):
        trees = env.ws / "trees"
        cases = {
            "skf-tree-20260101T000000Z-aaaaaaaa": {"tool": "skf-source-tree", "tree": str(env.tmp_path / "x" / "lib")},
            "skf-tree-20260101T000000Z-bbbbbbbb": {"tool": "other", "tree": None},
            "skf-tree-20260101T000000Z-cccccccc": None,
        }
        for name, record in cases.items():
            run = trees / name
            (run / "lib").mkdir(parents=True)
            if record is not None:
                if record["tree"] is None:
                    record["tree"] = str(run / "lib")
                (run / "run.json").write_bytes(json.dumps(record).encode("utf-8"))
            c = env.run("close", "--tree", str(run))
            assert c.rc == 0 and c.json["status"] == "refused", (name, c.json)
            assert (run / "lib").is_dir()


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


class TestCli:
    def test_one_ascii_line_and_exit_codes(self, env):
        env.clone_at("v2")
        ready = env.open(pin=env.sha("v2"))
        skipped = env.run("open", "--source-repo", "./x", "--source-root", str(env.tmp_path))
        unavailable = env.open("--target-ref", "nope", pin=env.sha("v2"))
        advanced = _advance(env, target=env.sha("v2"))
        closed = env.run("close", "--tree", ready.json["tree"])
        for result, rc in ((ready, 0), (skipped, 0), (unavailable, 3), (advanced, 0), (closed, 0)):
            assert result.rc == rc, (result.stdout, result.stderr)
            assert result.stdout.count("\n") == 1 and result.stdout.isascii()
        assert set(ready.json) == {"status", "skip_reason", "reason", "message", "tree", "clone", "target_ref",
                                   "ref_kind", "target_commit", "moved", "diff_status", "changed_files",
                                   "changed_counts", "warnings"}
        assert set(skipped.json) == set(ready.json) == set(unavailable.json)
        assert set(advanced.json) == {"status", "skip_reason", "head_sha", "created", "lock", "hygiene",
                                      "log_message", "warnings"}
        assert env.run("bogus").rc == 2

    def test_reason_vocabularies(self):
        """Every reason the code returns is listed, in the constant and the docstring."""
        mod = _mod()
        tree = ast.parse(HELPER.read_text(encoding="utf-8"))
        open_found, advance_found = set(), set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            args = [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            if node.func.id == "_unavailable_or_late" and args:
                open_found.add(args[0])
            elif node.func.id == "_unavailable" and args:
                open_found.add(args[0])
            elif node.func.id == "finish" and len(args) == 2:
                advance_found.add(args[1])
        assert open_found | {"timed-out"} == set(mod.OPEN_REASONS), open_found
        assert advance_found == set(mod.ADVANCE_SKIP_REASONS), advance_found
        doc = mod.__doc__
        for name, values in (("OPEN_REASONS", mod.OPEN_REASONS), ("ADVANCE_SKIP_REASONS", mod.ADVANCE_SKIP_REASONS)):
            end = doc.index(f"({name})")
            start = doc.rindex("null |", 0, end)
            assert re.findall(r'"([a-z-]+)"', doc[start:end]) == list(values), name

    def test_unexpected_error_exits_1(self, monkeypatch, capsys):
        mod = _mod()

        def boom(_args):
            raise RuntimeError("boom")

        monkeypatch.setattr(mod, "open_tree", boom)
        assert mod.main(["open", "--source-repo", URL]) == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert json.loads(captured.err)["status"] == "error"


# --------------------------------------------------------------------------
# Pinned copies
# --------------------------------------------------------------------------


def _node(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node
    raise AssertionError(f"{name} not found at the top level of {path.name}")


def _without_docstring(node) -> str:
    node = copy.deepcopy(node)
    first = node.body[0] if node.body else None
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        node.body = node.body[1:]
    return ast.dump(node)


class TestPinnedCopies:
    @pytest.mark.parametrize("name, source", [
        ("_acquire_lock", ATOMIC_WRITE),
        ("_release_lock", ATOMIC_WRITE),
        ("_same_path", HYGIENE),
        ("classify_match", DRIFT),
        ("is_skippable_pinned", DRIFT),
        ("GIT_LOCATION_VARS", DRIFT),
    ])
    def test_copies_identical(self, name, source):
        assert HELPER.is_file(), f"missing helper: {HELPER}"
        assert ast.dump(_node(HELPER, name)) == ast.dump(_node(source, name)), (
            f"{name} in skf-source-tree.py differs from {source.name}; keep the copies identical")

    def test_cwd_guard_code_matches_merge_helper(self):
        assert HELPER.is_file(), f"missing helper: {HELPER}"
        assert _without_docstring(_node(HELPER, "_resolve_outside_cwd")) == _without_docstring(
            _node(MERGE_CCC, "_resolve_outside_cwd"))

    def test_keep_identical_notes(self):
        text = HELPER.read_text(encoding="utf-8")
        for note in ("Keep identical to _acquire_lock in skf-atomic-write.py",
                     "Keep identical to _release_lock in skf-atomic-write.py",
                     "Keep identical to _same_path in skf-ccc-git-hygiene.py",
                     "Keep identical to classify_match in skf-check-workspace-drift.py",
                     "Keep identical to is_skippable_pinned in skf-check-workspace-drift.py",
                     "Keep identical to GIT_LOCATION_VARS in skf-check-workspace-drift.py",
                     "test/test-skf-source-tree.py pins"):
            assert note in text, note
