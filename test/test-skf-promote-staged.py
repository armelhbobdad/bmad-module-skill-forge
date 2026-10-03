"""skf-promote-staged.py: create-skill step 7 publishes the staging folder byte for byte.

The helper copies the staged deliverables and references into the skill
package (built beside it and swapped in through skf-atomic-write.py
stage-dir and commit-dir), copies each inventory script and asset from the
source tree, writes the three workspace files into the forge version folder
one atomic write each, and reads every promoted file back against the bytes
it came from. With --carry-manual it keeps the hand-written content of the
earlier build it replaces: the scripts/[MANUAL]/ and assets/[MANUAL]/ files
go into the new package, and a hand-written [MANUAL] block the staged
SKILL.md lacks leaves the earlier SKILL.md in the forge folder's
manual-backup/ (step 5b create-skill enhancement-2), a folder the ownership
checks of skf-skill-inventory.py count as SKF's. These tests run it on
scratch folders.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "src" / "shared" / "scripts" / "skf-promote-staged.py"

spec = importlib.util.spec_from_file_location("skf_promote_staged", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
_inventory_spec = importlib.util.spec_from_file_location(
    "skf_skill_inventory_for_promote", REPO / "src" / "shared" / "scripts" / "skf-skill-inventory.py")
inventory = importlib.util.module_from_spec(_inventory_spec)
_inventory_spec.loader.exec_module(inventory)

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
    assert out["counts"] == {"deliverables": 3, "references": 2, "scripts": 0, "assets": 0, "manual": 0,
                             "workspace": 3}
    assert out["manual"] == {"from": None, "blocks": [], "missing_blocks": [], "files": [], "backup": None}
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
            '--forge-version "{forge_version}" [--inventory "{extraction_inventory}" --source-root "{source_root}"] '
            '[--carry-manual "{skill_package}"]')
    assert call in step
    args = mod._build_parser().parse_args(["promote", "--stage", "s", "--package", "p", "--forge-version", "f",
                                           "--inventory", "i", "--source-root", "r", "--carry-manual", "p"])
    assert (args.stage, args.package, args.forge_version) == (Path("s"), Path("p"), Path("f"))
    assert args.carry_manual == Path("p")


# --- --carry-manual: a same-version re-run keeps the hand-written content ---------

SEEDED = (b"<!-- [MANUAL:additional-notes] -->\n"
          b"<!-- Add custom notes here. This section is preserved during skill updates. -->\n"
          b"<!-- [/MANUAL:additional-notes] -->\n")
NOTES = b"<!-- [MANUAL:additional-notes] -->\nCall `init()` before `run()`.\n<!-- [/MANUAL:additional-notes] -->\n"
EXTRA = b"<!--[MANUAL:deploy]-->\nDeploy with `make ship`.\r\n<!-- [/MANUAL:deploy] -->\n"
MANUAL_FILES = {"scripts/[MANUAL]/ship.sh": b"#!/bin/sh\nmake ship\n", "assets/[MANUAL]/img/logo.svg": b"<svg/>\n"}


def _earlier_build(root: Path, skill_md: bytes) -> tuple[Path, Path]:
    """A package an earlier compile of the version promoted, then edited by hand."""
    package, forge = _layout(root)
    assert _promote(_stage(root / "first"), package, forge).returncode == 0
    (package / "SKILL.md").write_bytes(skill_md)
    for rel, data in {**MANUAL_FILES, "scripts/old.sh": b"x\n"}.items():
        (package / rel).parent.mkdir(parents=True, exist_ok=True)
        (package / rel).write_bytes(data)
    return package, forge


def test_carry_manual_keeps_the_hand_written_files_and_blocks(tmp_path):
    package, forge = _earlier_build(tmp_path, b"# Demo\n\n" + NOTES + b"\n## API\n\n" + EXTRA + SEEDED.replace(
        b"additional-notes", b"empty"))
    # Step 5 carried both hand-written blocks into the staged SKILL.md, the
    # appended one with other surrounding blank lines; the seeded-only block
    # holds nothing hand-written to carry.
    staged = b"# Demo\n\n" + NOTES + b"\n## API\n\n" + EXTRA.replace(b"\n<!-- [/", b"\n\n\n<!-- [/")
    stage = _stage(tmp_path / "second", {**FILES, "SKILL.md": staged})
    proc = _promote(stage, package, forge, "--carry-manual", str(package))
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert (package / "SKILL.md").read_bytes() == staged
    for rel, data in MANUAL_FILES.items():
        assert (package / rel).read_bytes() == data, rel
    assert out["manual"] == {"from": package.as_posix(), "blocks": ["additional-notes", "deploy"],
                             "missing_blocks": [], "files": ["scripts/[MANUAL]/ship.sh", "assets/[MANUAL]/img/logo.svg"],
                             "backup": None}
    assert out["counts"]["manual"] == 2 and out["warnings"] == []
    kinds = {f["path"]: f["kind"] for f in out["files"]}
    assert kinds[(package / "scripts" / "[MANUAL]" / "ship.sh").as_posix()] == "manual"
    assert not (forge / "manual-backup").exists()
    # Every other file of the earlier package is gone, as without the flag.
    assert not (package / "scripts" / "old.sh").exists()


def test_a_block_the_staged_skill_md_lacks_keeps_the_earlier_one(tmp_path):
    earlier = b"# Demo\n\n" + NOTES + EXTRA
    package, forge = _earlier_build(tmp_path, earlier)
    staged = b"# Demo\n\n" + NOTES + SEEDED.replace(b"additional-notes", b"deploy")
    stage = _stage(tmp_path / "second", {**FILES, "SKILL.md": staged})
    proc = _promote(stage, package, forge, "--carry-manual", str(package))
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    [backup] = (forge / "manual-backup").iterdir()
    assert re.fullmatch(r"SKILL-\d{8}-\d{6}\.md", backup.name)
    assert backup.read_bytes() == earlier
    assert out["manual"]["blocks"] == ["additional-notes"] and out["manual"]["missing_blocks"] == ["deploy"]
    assert out["manual"]["backup"] == backup.as_posix()
    [warning] = out["warnings"]
    assert "deploy" in warning and backup.as_posix() in warning
    # The files carry forward all the same, and the new SKILL.md is the staged one.
    assert (package / "scripts" / "[MANUAL]" / "ship.sh").is_file()
    assert (package / "SKILL.md").read_bytes() == staged


def test_a_later_backup_never_replaces_an_earlier_one(tmp_path):
    """Two runs that each lose a block keep both earlier SKILL.md files, even within one second."""
    first = b"# Demo\n\n" + NOTES + EXTRA
    package, forge = _earlier_build(tmp_path, first)
    lacking_deploy = b"# Demo\n\n" + NOTES
    assert _promote(_stage(tmp_path / "second", {**FILES, "SKILL.md": lacking_deploy}), package, forge,
                    "--carry-manual", str(package)).returncode == 0
    # The user has not restored `deploy` yet and writes another block, which the next run also loses.
    second = lacking_deploy + b"<!-- [MANUAL:faq] -->\nSee the wiki.\n<!-- [/MANUAL:faq] -->\n"
    (package / "SKILL.md").write_bytes(second)
    proc = _promote(_stage(tmp_path / "third", {**FILES, "SKILL.md": lacking_deploy}), package, forge,
                    "--carry-manual", str(package))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["manual"]["missing_blocks"] == ["faq"]
    assert sorted(p.read_bytes() for p in (forge / "manual-backup").iterdir()) == sorted([first, second])


def test_a_backup_name_already_taken_gets_a_suffix(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "time", SimpleNamespace(strftime=lambda fmt, t: "20261003-000000", gmtime=lambda: None))
    folder = tmp_path / mod.MANUAL_BACKUP
    assert mod._backup_target(tmp_path) == folder / "SKILL-20261003-000000.md"
    folder.mkdir()
    (folder / "SKILL-20261003-000000.md").write_bytes(b"x")
    (folder / "SKILL-20261003-000000-2.md").write_bytes(b"x")
    assert mod._backup_target(tmp_path) == folder / "SKILL-20261003-000000-3.md"


def test_a_crlf_earlier_block_matches_its_lf_carry(tmp_path):
    """A Windows checkout's CRLF SKILL.md, with trailing spaces, holds the block step 5 carried as LF."""
    earlier = (b"# Demo\r\n\r\n<!-- [MANUAL:notes] -->\r\nline one  \r\nline two\r\n<!-- [/MANUAL:notes] -->\r\n")
    package, forge = _earlier_build(tmp_path, earlier)
    staged = b"# Demo\n\n<!-- [MANUAL:notes] -->\nline one\nline two\n<!-- [/MANUAL:notes] -->\n"
    proc = _promote(_stage(tmp_path / "second", {**FILES, "SKILL.md": staged}), package, forge,
                    "--carry-manual", str(package))
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert (out["manual"]["blocks"], out["manual"]["missing_blocks"]) == (["notes"], [])
    assert out["manual"]["backup"] is None and out["warnings"] == []
    assert not (forge / "manual-backup").exists()


@pytest.mark.parametrize("same_folder", [True, False], ids=["same-folder", "split-folders"])
def test_the_backup_is_skf_output_to_the_ownership_checks(tmp_path, same_folder):
    """The next create-skill run of the version and drop-skill's purge still read the folder as SKF's."""
    skills = tmp_path / "out"
    forge_root = skills if same_folder else tmp_path / "forge"
    package, forge = skills / "demo" / "1.0.0" / "demo", forge_root / "demo" / "1.0.0"
    marked = {**FILES, "metadata.json": b'{"name": "demo", "generated_by": "create-skill"}\n'}
    assert _promote(_stage(tmp_path / "first", marked), package, forge).returncode == 0
    (package / "SKILL.md").write_bytes(b"# Demo\n\n" + NOTES)
    proc = _promote(_stage(tmp_path / "second", marked), package, forge, "--carry-manual", str(package))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["manual"]["backup"].startswith((forge / mod.MANUAL_BACKUP).as_posix() + "/")
    assert mod.MANUAL_BACKUP in inventory.FORGE_VERSION_FILES
    assert inventory.write_check(skills, "demo", "1.0.0", forge_root)["verdict"] == "ok"
    assert inventory.purge_check(skills, "demo", forge_root)["verdict"] == "ok"
    assert inventory.purge_check(skills, "demo", forge_root, "1.0.0")["verdict"] == "ok"


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs a file its owner cannot read")
def test_an_unreadable_earlier_file_writes_nothing(tmp_path):
    package, forge = _earlier_build(tmp_path, b"# Demo\n\n" + NOTES)
    unreadable = package / "scripts" / "[MANUAL]" / "ship.sh"
    unreadable.chmod(0)
    try:
        proc = _promote(_stage(tmp_path / "second"), package, forge, "--carry-manual", str(package))
    finally:
        unreadable.chmod(0o644)
    assert proc.returncode == 1
    assert json.loads(proc.stderr)["message"].startswith(f"cannot read {unreadable.as_posix()}: ")
    assert (package / "SKILL.md").read_bytes() == b"# Demo\n\n" + NOTES
    assert not (forge / "manual-backup").exists()


def test_carry_manual_with_nothing_hand_written(tmp_path):
    package, forge = _layout(tmp_path)
    assert _promote(_stage(tmp_path / "first", {**FILES, "SKILL.md": SEEDED}), package, forge).returncode == 0
    proc = _promote(_stage(tmp_path / "second"), package, forge, "--carry-manual", str(package))
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["manual"] == {"from": package.as_posix(), "blocks": [], "missing_blocks": [], "files": [],
                             "backup": None}
    assert out["warnings"] == [] and not (forge / "manual-backup").exists()


def test_carry_manual_needs_a_folder(tmp_path):
    stage = _stage(tmp_path)
    package, forge = _layout(tmp_path)
    proc = _promote(stage, package, forge, "--carry-manual", str(package))
    assert proc.returncode == 1
    assert "is not a folder" in json.loads(proc.stderr)["message"]
    assert not package.exists() and not forge.exists()


@pytest.mark.parametrize(("data", "blocks"), [
    (NOTES + EXTRA, [("additional-notes", True), ("deploy", True)]),
    (SEEDED, [("additional-notes", False)]),
    # An unclosed marker is no block; a close marker pairs with the first open of its name before it.
    (b"<!-- [MANUAL:a] -->\nx\n" + NOTES, [("additional-notes", True)]),
    (b"<!-- [MANUAL:a] -->x<!-- [/MANUAL:a] -->y<!-- [/MANUAL:a] -->", [("a", True)]),
    # The seeded note with other line endings and spaces is still the seeded note; a note of the
    # user's own, written as an HTML comment, is hand-written.
    (SEEDED.replace(b"\n", b"  \r\n"), [("additional-notes", False)]),
    (b"<!-- [MANUAL:todo] -->\n<!-- TODO: pin the retry count -->\n<!-- [/MANUAL:todo] -->", [("todo", True)]),
    (b"<!-- [MANUAL:blank] -->\n \n<!-- [/MANUAL:blank] -->", [("blank", False)]),
], ids=["two-blocks", "seeded-only", "unclosed", "first-close", "seeded-crlf", "own-comment", "blank"])
def test_blocks_pair_their_markers(data, blocks):
    found = mod._manual_blocks(data)
    assert [(name, mod._hand_written(interior)) for name, interior in found] == blocks


def _create_skill(rel: str) -> str:
    return (REPO / "src" / "skf-create-skill" / rel).read_text(encoding="utf-8")


def test_create_skill_carries_the_hand_written_content_forward():
    """Step 5 puts an earlier build's [MANUAL] blocks into the staged SKILL.md and records the decision
    before the Auto-Decisions table renders; step 7 hands the earlier package to the helper; step 8 names
    what was kept under Warnings."""
    rules = _create_skill("assets/compile-assembly-rules.md")
    section_8 = rules[rules.index("**Section 8"):rules.index("### Tier 2")]
    (carry,) = [line for line in section_8.splitlines() if line.startswith("- **Carry an earlier build's blocks.**")]
    for needle in ("`{skills_output_folder}/{name}/{version}/{name}/SKILL.md` exists "
                   "(`{version}` with build metadata stripped, as step 7 §1 does)",
                   "from `<!-- [MANUAL:<id>] -->` to the first `<!-- [/MANUAL:<id>] -->` after it",
                   "hand-written unless it holds nothing but whitespace or the seeded note above",
                   "append a block whose id has no marker here at the end of this section",
                   "Step 6 then validates SKILL.md with the blocks in",
                   '--decision < "{run_dir}/decision.json"`'):
        assert needle in carry, needle
    # The helper's seeded note is the one this section seeds.
    assert mod.SEEDED_NOTE.decode("utf-8") in section_8
    decision = json.loads(re.search(r'`(\{"step": "compile"[^`]+\})`', carry).group(1))
    schema = json.loads((REPO / "src" / "shared" / "scripts" / "schemas"
                         / "skf-create-skill-result-envelope.v1.json").read_text(encoding="utf-8"))
    item = schema["properties"]["headless_decisions"]["items"]
    assert set(item["required"]) <= set(decision) <= set(item["properties"])
    assert decision["gate"] == "manual-carry-forward" and "manual-carry-forward" in item["properties"]["gate"]["description"]

    step7 = _create_skill("references/generate-artifacts.md")
    assert "`{existing_generator}` ← `write_check.version_generated_by`" in step7
    assert "`--carry-manual \"{skill_package}\"` when `{skill_package}` already exists" in step7
    assert "`manual` (what `--carry-manual` kept: `blocks`, `missing_blocks`, `files`, `backup`)" in step7
    assert "`{forge_version}/manual-backup/SKILL-<UTC time>.md`" in step7
    assert "or the earlier package cannot be read; nothing was written" in step7
    compile_step = _create_skill("references/compile.md")
    assert "step 3d component-extraction gates, step 5 manual-carry-forward)" in compile_step

    report = _create_skill("references/report.md")
    warnings = report[report.index("### 3. Display Warnings"):report.index("### 4. ")]
    for field in ("`manual.blocks`", "`manual.files`", "`manual.missing_blocks`", "`{manual.backup}`",
                  "{existing_generator, or SKF}",
                  "show the section when either applies, even with no other warning"):
        assert field in warnings, field
