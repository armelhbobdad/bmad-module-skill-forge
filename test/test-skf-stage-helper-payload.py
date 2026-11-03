#!/usr/bin/env python3
"""Tests for stage-helper-payload.py: the helper payload read from disk (#584).

coverage-check.md §0b asks skf-detect-workspaces.py whether a local source is
a monorepo. The helper takes one JSON payload on stdin and reads no file,
and a payload the model writes by hand can cut or mis-escape a file. The
script reads the files and prints the payload instead. These tests cover
what the payload holds, what the tree leaves out, the bytes it prints, and,
piped into the real helper, the answer the step reads. The Quick-tier scan
(coverage-check-tiers.md, which coverage-check.md §2 loads at Quick tier)
no longer goes through it: skf-extract-public-api.py --mode quick reads its
files itself (--manifest-file, --entry-file), so the extract-public-api
subcommand is gone. With --brief, the tree leaves out what the brief's
scope.exclude drops, so a workspace whose members it drops is no
workspace (#780).
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "skf-test-skill" / "scripts" / "stage-helper-payload.py"
SCRIPTS = REPO_ROOT / "src" / "shared" / "scripts"
WORKSPACES = SCRIPTS / "skf-detect-workspaces.py"

spec = importlib.util.spec_from_file_location("stage_helper_payload", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

# The recipe runner, whose monorepo arm reads a brief's scope.exclude as this script does (#780).
_extract_spec = importlib.util.spec_from_file_location("skf_extract_public_api_for_staging",
                                                       SCRIPTS / "skf-extract-public-api.py")
EXTRACT = importlib.util.module_from_spec(_extract_spec)
assert _extract_spec.loader is not None
_extract_spec.loader.exec_module(EXTRACT)


def _write(root: Path, files: dict[str, str | bytes]) -> Path:
    """Write each file as the exact bytes given (text as UTF-8, LF kept on every OS)."""
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    return root


def _stage(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT_PATH), *args], capture_output=True, check=False)


def _pipe(helper: Path, stage_args: list[str], helper_args: list[str] | None = None) -> dict:
    """Run the script and pipe its stdout into `helper`, as the step's command does."""
    staged = _stage(*stage_args)
    assert staged.returncode == 0, staged.stderr.decode("utf-8")
    proc = subprocess.run([sys.executable, str(helper), *(helper_args or [])], input=staged.stdout,
                          capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr.decode("utf-8")
    return json.loads(proc.stdout)


# --------------------------------------------------------------------------
# detect-workspaces
# --------------------------------------------------------------------------


def test_tree_lists_every_file_outside_skipped_folders(tmp_path):
    root = _write(tmp_path / "src", {
        "package.json": "{}",
        "packages/a/package.json": "{}",
        "packages/a/src/index.ts": "export const a = 1;\n",
        "packages/a/node_modules/dep/package.json": "{}",
        "node_modules/dep/package.json": "{}",
        ".git/HEAD": "ref: refs/heads/main\n",
        ".venv/lib/pyproject.toml": "",
        "vendor/mod/go.mod": "",
        "target/package/x-1.0.0/Cargo.toml": "",
        "src/__pycache__/m.pyc": b"\x00",
        ".github/workflows/ci.yml": "on: push\n",
    })
    assert mod.list_tree(root) == ["package.json", "packages/a/package.json", "packages/a/src/index.ts"]


def test_tree_does_not_follow_a_linked_folder(tmp_path):
    root = _write(tmp_path / "src", {"package.json": "{}"})
    outside = _write(tmp_path / "outside", {"packages/x/package.json": "{}"})
    try:
        os.symlink(outside, root / "linked", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this platform cannot create a folder symlink here")
    assert mod.list_tree(root) == ["package.json"]


def test_root_texts_hold_the_root_files_as_written(tmp_path):
    manifest = '{"name": "it\'s \\"quoted\\"", "description": "café \\\\ tab\\t"}\n'
    root = _write(tmp_path / "src", {
        "package.json": manifest,
        "Cargo.toml": b"\xef\xbb\xbf[workspace]\nmembers = [\"crates/*\"]\n",  # a byte order mark
        "README.md": "# demo\n",
        ".env": "TOKEN=secret\n",
        "logo.png": b"\x89PNG\r\n\x1a\n\xff\xfe",
        "packages/a/package.json": "{}",
    })
    (root / "big.json").write_bytes(b"x" * (mod.MAX_ROOT_FILE_BYTES + 1))
    texts = mod.root_texts(root)
    assert sorted(texts) == ["Cargo.toml", "README.md", "package.json"]
    assert texts["package.json"] == manifest
    assert texts["Cargo.toml"].startswith("[workspace]")


@pytest.mark.parametrize("files, expected", [
    ({"package.json": json.dumps({"name": "root", "workspaces": ["packages/*"]}),
      "packages/a/package.json": "{}", "packages/b/package.json": "{}",
      "packages/a/node_modules/c/package.json": "{}"},
     (True, "npm-workspaces", ["packages/a", "packages/b"])),
    ({"Cargo.toml": "[workspace]\nmembers = [\"crates/*\"]\n",
      "crates/core/Cargo.toml": "[package]\nname = \"core\"\n", "crates/cli/Cargo.toml": "[package]\nname = \"cli\"\n"},
     (True, "cargo-workspace", ["crates/cli", "crates/core"])),
    ({"apps/web/package.json": "{}", "libs/ui/package.json": "{}"},
     (True, "generic-folders", ["apps/web", "libs/ui"])),
    ({"package.json": json.dumps({"name": "single"}), "src/index.ts": "export {};\n",
      "node_modules/a/package.json": "{}", "node_modules/b/package.json": "{}"},
     (False, None, [])),
], ids=["npm-workspaces", "cargo-workspace", "generic-folders", "single-package"])
def test_the_detector_reads_the_staged_payload(tmp_path, files, expected):
    root = _write(tmp_path / "src", files)
    out = _pipe(WORKSPACES, ["detect-workspaces", "--source-root", str(root)])
    assert (out["is_monorepo"], out["manifest_kind"], [w["path"] for w in out["workspaces"]]) == expected


# #780: the workspace layouts and briefs both paths read alike (stage-helper-payload.py piped to the
# detector, and the recipe runner's monorepo arm), shared with the runner's and the prose command's tests.
SCOPE_EXCLUDE = json.loads((REPO_ROOT / "test" / "fixtures" / "workspace-scope-exclude.json").read_text("utf-8"))
SCOPE_CASES = [pytest.param(case, id=case["id"]) for case in SCOPE_EXCLUDE["cases"]]


def _brief(folder: Path, excludes: list[str]) -> Path:
    """A skill brief whose scope.exclude lists `excludes`, closed by the trailing `---` SKF 1.x wrote."""
    lines = "".join(f"    - '{g}'\n" for g in excludes)
    return _write(folder, {"skill-brief.yaml": f"name: pkg\nscope:\n  include: ['python/**']\n  exclude:\n{lines}---\n"}
                  ) / "skill-brief.yaml"


def _staged_case(tmp_path: Path, case: dict) -> tuple[Path, list[str]]:
    """The case's tree under tmp_path/src, and the detect-workspaces arguments (with --brief when it has one)."""
    root = _write(tmp_path / "src", SCOPE_EXCLUDE["trees"][case["tree"]])
    args = ["detect-workspaces", "--source-root", str(root)]
    if case["exclude"] is not None:
        args += ["--brief", str(_brief(tmp_path, case["exclude"]))]
    return root, args


@pytest.mark.parametrize("case", SCOPE_CASES)
def test_a_brief_keeps_a_member_only_through_its_kept_files(tmp_path, case):
    """#780: a workspace member counts only through the files the brief keeps, so excluding its source
    files drops it and excluding only its manifest does not; a workspace with no member left is no
    workspace, one with a member left still is, and the root manifests are staged whatever it excludes."""
    root, args = _staged_case(tmp_path, case)
    out = _pipe(WORKSPACES, args)
    assert (out["is_monorepo"], out["manifest_kind"]) == (case["is_monorepo"], case["manifest_kind"])
    staged = json.loads(_stage(*args).stdout)
    assert sorted(staged["manifests"]) == sorted(f for f in SCOPE_EXCLUDE["trees"][case["tree"]] if "/" not in f)
    assert set(staged["manifests"]) <= set(staged["tree"])  # every root file here is a manifest


def test_a_member_kept_keeps_its_workspace(tmp_path):
    root = _write(tmp_path / "src", SCOPE_EXCLUDE["trees"]["npm-two-packages"])
    out = _pipe(WORKSPACES, ["detect-workspaces", "--source-root", str(root), "--brief",
                             str(_brief(tmp_path, ["packages/b/**"]))])
    assert [w["path"] for w in out["workspaces"]] == ["packages/a"]


@pytest.mark.parametrize("brief", [
    "name: pkg\n",
    "name: pkg\nscope:\n  include: ['rust/**']\n",
    "scope:\n  exclude: rust/**\n",
    "scope:\n  exclude: [7, '', null]\n",
], ids=["no-scope", "include-only", "exclude-not-a-list", "no-glob"])
def test_a_brief_without_an_exclude_glob_drops_nothing(tmp_path, brief):
    """scope.include plays no part: only an exclude glob leaves a path out."""
    root = _write(tmp_path / "src", SCOPE_EXCLUDE["trees"]["rust-beside-python"])
    path = _write(tmp_path, {"skill-brief.yaml": brief}) / "skill-brief.yaml"
    assert _stage("detect-workspaces", "--source-root", str(root), "--brief", str(path)).stdout == \
        _stage("detect-workspaces", "--source-root", str(root)).stdout


@pytest.mark.parametrize("files, message", [
    ({}, "cannot read --brief"),
    ({"skill-brief.yaml": "scope: [\n"}, "is not valid YAML"),
    ({"skill-brief.yaml": "name: pkg\ncreated: 2024-13-45\n"}, "is not valid YAML: month must be in 1..12"),
    ({"skill-brief.yaml": "- a\n- b\n"}, "is not a YAML mapping"),
    ({"skill-brief.yaml": b"scope:\n  exclude: ['\xff']\n"}, "cannot read --brief"),
], ids=["missing", "not-yaml", "invalid-date", "not-a-mapping", "not-utf8"])
def test_a_brief_it_cannot_read_exits_1(tmp_path, files, message):
    """One JSON line on stderr, an invalid date (a ValueError YAML raises, not a YAMLError) included."""
    root = _write(tmp_path / "src", {"package.json": "{}"})
    _write(tmp_path, files)
    proc = _stage("detect-workspaces", "--source-root", str(root), "--brief", str(tmp_path / "skill-brief.yaml"))
    assert proc.returncode == 1 and proc.stdout == b""
    (line,) = proc.stderr.decode("utf-8").splitlines()
    assert message in json.loads(line)["error"]


def test_a_brief_without_pyyaml_names_it(tmp_path, monkeypatch, capsys):
    """Run without `uv run`, so with no PyYAML: the brief reader says how to run the script."""
    root = _write(tmp_path / "src", {"package.json": "{}"})
    monkeypatch.setitem(sys.modules, "yaml", None)  # `import yaml` raises ImportError
    assert mod.main(["detect-workspaces", "--source-root", str(root), "--brief",
                     str(_brief(tmp_path, ["rust/**"]))]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--brief is read with PyYAML: run the script with `uv run`" in json.loads(captured.err)["error"]


def test_a_brief_with_no_resolver_beside_it_exits_1(tmp_path):
    """Installed without skf-resolve-authoritative-files.py in the shared scripts folder, the brief
    reader names the missing script."""
    scripts = tmp_path / "skf" / "skf-test-skill" / "scripts"
    shared = tmp_path / "skf" / "shared" / "scripts"
    scripts.mkdir(parents=True)
    shared.mkdir(parents=True)
    for source in (SCRIPT_PATH, SCRIPT_PATH.parent / "load-coverage-inputs.py"):
        (scripts / source.name).write_bytes(source.read_bytes())
    (shared / WORKSPACES.name).write_bytes(WORKSPACES.read_bytes())
    root = _write(tmp_path / "src", {"package.json": "{}"})
    proc = subprocess.run([sys.executable, str(scripts / SCRIPT_PATH.name), "detect-workspaces", "--source-root",
                           str(root), "--brief", str(_brief(tmp_path, ["rust/**"]))],
                          capture_output=True, check=False)
    assert proc.returncode == 1 and proc.stdout == b""
    assert "skf-resolve-authoritative-files.py not found" in json.loads(proc.stderr)["error"]


@pytest.mark.parametrize("case", SCOPE_CASES)
def test_both_paths_give_one_verdict(tmp_path, monkeypatch, case):
    """#780: Test Skill's workspace detection and the recipe runner's monorepo arm, which picks Create and
    Update Skill's stored denominator, read the same layout under the same brief alike."""
    root, args = _staged_case(tmp_path, case)
    detected = _pipe(WORKSPACES, args)
    monkeypatch.setattr(EXTRACT, "_ast_grep", lambda: (None, None, None))  # the arms need no ast-grep
    out = tmp_path / "extract.json"
    flags = ["--brief", args[-1]] if case["exclude"] is not None else []
    assert EXTRACT.main(["--mode", "full", "--source-root", str(root), *flags, "-o", str(out)]) == 3
    arms = json.loads(out.read_text(encoding="utf-8"))["arms"]
    assert (arms["monorepo"], arms["monorepo_kind"]) == (detected["is_monorepo"], detected["manifest_kind"]) \
        == (case["is_monorepo"], case["manifest_kind"])


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_a_missing_source_root_exits_1(tmp_path):
    proc = _stage("detect-workspaces", "--source-root", str(tmp_path / "absent"))
    assert proc.returncode == 1 and proc.stdout == b""
    assert "not a folder" in json.loads(proc.stderr)["error"]


@pytest.mark.parametrize("args", [[], ["detect-workspaces"], ["extract-public-api", "--source-root", "."]],
                         ids=["no-command", "no-source-root", "retired-extract-public-api"])
def test_bad_arguments_exit_2(args):
    assert _stage(*args).returncode == 2


def test_output_is_one_ascii_line(tmp_path):
    root = _write(tmp_path / "src", {"package.json": '{"description": "café 日本"}\n'})
    proc = _stage("detect-workspaces", "--source-root", str(root))
    assert proc.returncode == 0
    assert proc.stdout.isascii() and proc.stdout.strip().count(b"\n") == 0
    assert json.loads(proc.stdout)["manifests"]["package.json"] == '{"description": "café 日本"}\n'


def test_script_header():
    """--brief reads the skill brief's YAML through skf-resolve-authoritative-files.py, which needs PyYAML."""
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env python3\n# /// script\n# requires-python = \">=3.11\"\n"
                           "# dependencies = [\"pyyaml\"]\n# ///\n")
    assert "sys.exit(main())" in text
