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
subcommand is gone.
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
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env python3\n# /// script\n# requires-python = \">=3.11\"\n"
                           "# dependencies = []\n# ///\n")
    assert "sys.exit(main())" in text
