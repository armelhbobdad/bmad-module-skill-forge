"""skf-promote-staged.py: create-skill step 7 publishes the staging folder byte for byte.

The helper copies the staged deliverables and references into the skill
package (built beside it and swapped in through skf-atomic-write.py
stage-dir and commit-dir), copies each inventory script and asset from the
source tree, writes the three workspace files into the forge version folder
one atomic write each, and reads every promoted file back against the bytes
it came from. These tests run it on scratch folders.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "src" / "shared" / "scripts" / "skf-promote-staged.py"

spec = importlib.util.spec_from_file_location("skf_promote_staged", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# Bytes that a rewrite from context would not reproduce: CRLF, a BOM, no final newline.
SKILL_MD = b"\xef\xbb\xbf---\r\nname: demo\r\n---\r\n\r\n# Demo\r\nno final newline"
FILES = {
    "SKILL.md": SKILL_MD,
    "context-snippet.md": b"[demo v1.0.0]|root: skills/demo/\n",
    "metadata.json": b'{"name": "demo", "doc_sources": [{"url": "https://x"}]}\n',
    "references/full-api-reference.md": b"## Full API Reference\n",
    "references/nested/types.md": b"## Types\n",
    "provenance-map.json": b'{"entries": []}\n',
    "evidence-report.md": b"# Evidence\n## Remaining Warnings\n- none\n",
    "extraction-rules.yaml": b"language: python\n",
}


def _stage(root: Path, files: dict[str, bytes] = FILES) -> Path:
    stage = root / "_bmad-output" / ".skf-stage" / "demo"
    for rel, data in files.items():
        path = stage / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return stage


def _layout(root: Path) -> tuple[Path, Path]:
    return root / "skills" / "demo" / "1.0.0" / "demo", root / "forge" / "demo" / "1.0.0"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          encoding="utf-8", timeout=120)


def _promote(stage: Path, package: Path, forge: Path, *extra: str) -> subprocess.CompletedProcess:
    return _run("promote", "--stage", str(stage), "--package", str(package), "--forge-version", str(forge), *extra)


def test_promotes_every_staged_file_byte_for_byte(tmp_path):
    stage = _stage(tmp_path)
    package, forge = _layout(tmp_path)
    proc = _promote(stage, package, forge)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    for rel, data in FILES.items():
        target = forge / rel if rel in mod.WORKSPACE_FILES else package / rel
        assert target.read_bytes() == data, rel
    assert out["counts"] == {"deliverables": 3, "references": 2, "scripts": 0, "assets": 0, "workspace": 3}
    assert out["package"] == package.as_posix() and out["forge_version"] == forge.as_posix()
    by_path = {f["path"]: f for f in out["files"]}
    skill = by_path[(package / "SKILL.md").as_posix()]
    assert skill["kind"] == "deliverable"
    assert skill["bytes"] == len(SKILL_MD)
    assert skill["sha256"] == "sha256:" + hashlib.sha256(SKILL_MD).hexdigest()
    assert by_path[(forge / "evidence-report.md").as_posix()]["kind"] == "workspace"
    assert by_path[(package / "references" / "nested" / "types.md").as_posix()]["kind"] == "reference"
    # the workspace files never land in the package, nor the deliverables in the forge folder
    assert not (package / "provenance-map.json").exists() and not (forge / "SKILL.md").exists()
    assert not package.with_name("demo.skf-tmp").exists()


def test_a_second_promotion_replaces_the_package_whole(tmp_path):
    """A re-forge of the version leaves no reference file of the earlier compile behind."""
    package, forge = _layout(tmp_path)
    first = _stage(tmp_path / "a", {**FILES, "references/old.md": b"stale\n"})
    assert _promote(first, package, forge).returncode == 0
    (forge / "create-skill-result-latest.json").write_text("{}", encoding="utf-8")
    second = _stage(tmp_path / "b")
    proc = _promote(second, package, forge)
    assert proc.returncode == 0, proc.stderr
    assert not (package / "references" / "old.md").exists()
    assert sorted(p.name for p in (package / "references").iterdir()) == ["full-api-reference.md", "nested"]
    # the forge folder keeps what earlier runs wrote there
    assert (forge / "create-skill-result-latest.json").is_file()
    assert not any(p.name.startswith("demo.skf-rollback-") for p in package.parent.iterdir())


def test_scripts_and_assets_come_from_the_source_tree(tmp_path):
    stage = _stage(tmp_path)
    package, forge = _layout(tmp_path)
    source = tmp_path / "src-tree"
    (source / "bin").mkdir(parents=True)
    (source / "bin" / "run.sh").write_bytes(b"#!/bin/sh\necho hi\n")
    (source / "schemas").mkdir()
    (source / "schemas" / "x.schema.json").write_bytes(b'{"$schema": "y"}\n')
    inventory = tmp_path / "demo.inventory.json"
    inventory.write_text(json.dumps({
        "exports": [],
        "scripts_inventory": [{"name": "run.sh", "source_file": "bin/run.sh",
                               "content_hash": "sha256:" + hashlib.sha256(b"#!/bin/sh\necho hi\n").hexdigest()}],
        "assets_inventory": [{"name": "x.schema.json", "source_file": "schemas/x.schema.json",
                              "content_hash": "sha256:" + "0" * 64}],
    }), encoding="utf-8")
    proc = _promote(stage, package, forge, "--inventory", str(inventory), "--source-root", str(source))
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert (package / "scripts" / "run.sh").read_bytes() == b"#!/bin/sh\necho hi\n"
    assert (package / "assets" / "x.schema.json").read_bytes() == b'{"$schema": "y"}\n'
    assert (out["counts"]["scripts"], out["counts"]["assets"]) == (1, 1)
    # a hash that no longer matches is copied anyway, with a warning
    assert len(out["warnings"]) == 1 and out["warnings"][0].startswith("assets/x.schema.json:")


@pytest.mark.parametrize("record,needle", [
    ({"name": "a.sh", "source_file": "../outside.sh"}, "not a path inside --source-root"),
    ({"name": "a.sh", "source_file": "missing.sh"}, "is not a file under --source-root"),
    ({"source_file": "bin/run.sh", "name": "x/y"}, "has no usable name"),
], ids=["outside-the-tree", "missing-file", "bad-name"])
def test_a_bad_inventory_entry_writes_nothing(tmp_path, record, needle):
    stage = _stage(tmp_path)
    package, forge = _layout(tmp_path)
    source = tmp_path / "src-tree"
    (source / "bin").mkdir(parents=True)
    (source / "bin" / "run.sh").write_bytes(b"x\n")
    inventory = tmp_path / "inv.json"
    inventory.write_text(json.dumps({"exports": [], "scripts_inventory": [record]}), encoding="utf-8")
    proc = _promote(stage, package, forge, "--inventory", str(inventory), "--source-root", str(source))
    assert proc.returncode == 1
    assert needle in json.loads(proc.stderr)["message"]
    assert not package.exists() and not forge.exists()


def test_two_scripts_with_one_name_are_refused(tmp_path):
    stage = _stage(tmp_path)
    package, forge = _layout(tmp_path)
    source = tmp_path / "src-tree"
    for folder in ("bin", "tools"):
        (source / folder).mkdir(parents=True)
        (source / folder / "run.sh").write_bytes(b"x\n")
    inventory = tmp_path / "inv.json"
    inventory.write_text(json.dumps({"exports": [], "scripts_inventory": [
        {"name": "run.sh", "source_file": "bin/run.sh"}, {"name": "run.sh", "source_file": "tools/run.sh"}]}),
        encoding="utf-8")
    proc = _promote(stage, package, forge, "--inventory", str(inventory), "--source-root", str(source))
    assert proc.returncode == 1
    assert "would both be scripts/run.sh" in json.loads(proc.stderr)["message"]


@pytest.mark.parametrize("missing", ["SKILL.md", "metadata.json", "extraction-rules.yaml"])
def test_a_missing_staged_file_writes_nothing(tmp_path, missing):
    stage = _stage(tmp_path, {k: v for k, v in FILES.items() if k != missing})
    package, forge = _layout(tmp_path)
    proc = _promote(stage, package, forge)
    assert proc.returncode == 1
    assert missing in json.loads(proc.stderr)["message"]
    assert not package.exists() and not forge.exists()


def test_files_the_package_does_not_take_are_listed(tmp_path):
    stage = _stage(tmp_path, {**FILES, "notes.txt": b"x\n"})
    package, forge = _layout(tmp_path)
    proc = _promote(stage, package, forge)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["ignored"] == ["notes.txt"]
    assert not (package / "notes.txt").exists()


def test_a_half_written_or_hidden_reference_is_not_promoted(tmp_path):
    """A <name>.skf-tmp an interrupted skf-atomic-write.py write left, or a hidden file, never ships."""
    leftovers = {"references/full-api-reference.md.skf-tmp": b"half\n", "references/.DS_Store": b"\x00",
                 "references/.cache/x.md": b"x\n"}
    stage = _stage(tmp_path, {**FILES, **leftovers})
    package, forge = _layout(tmp_path)
    proc = _promote(stage, package, forge)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["counts"]["references"] == 2
    assert out["ignored"] == sorted(leftovers)
    for rel in leftovers:
        assert not (package / rel).exists(), rel


def test_a_package_path_that_is_a_file_fails_the_swap(tmp_path):
    """commit-dir refuses a non-folder target: exit 2, and the file is left as it was."""
    stage = _stage(tmp_path)
    package, forge = _layout(tmp_path)
    package.parent.mkdir(parents=True)
    package.write_bytes(b"not a folder")
    proc = _promote(stage, package, forge)
    assert proc.returncode == 2
    assert "commit-dir failed" in json.loads(proc.stderr)["message"]
    assert package.read_bytes() == b"not a folder"
    assert not forge.exists()


def test_inventory_entries_need_a_source_root(tmp_path):
    stage = _stage(tmp_path)
    package, forge = _layout(tmp_path)
    inventory = tmp_path / "inv.json"
    inventory.write_text(json.dumps({"exports": [], "assets_inventory": [{"name": "a", "source_file": "a"}]}),
                         encoding="utf-8")
    proc = _promote(stage, package, forge, "--inventory", str(inventory))
    assert proc.returncode == 1
    assert "pass --source-root" in json.loads(proc.stderr)["message"]


def test_the_documented_call_parses():
    """generate-artifacts.md §3 runs the promote subcommand with these flags."""
    step = (REPO / "src" / "skf-create-skill" / "references" / "generate-artifacts.md").read_text(encoding="utf-8")
    call = ('uv run {promoteStagedHelper} promote --stage "<staging-skill-dir>" --package "{skill_package}" '
            '--forge-version "{forge_version}" [--inventory "{extraction_inventory}" --source-root "{source_root}"]')
    assert call in step
    args = mod._build_parser().parse_args(["promote", "--stage", "s", "--package", "p", "--forge-version", "f",
                                           "--inventory", "i", "--source-root", "r"])
    assert (args.stage, args.package, args.forge_version) == (Path("s"), Path("p"), Path("f"))
