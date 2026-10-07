#!/usr/bin/env python3
"""A skill brief SKF 1.x wrote, closed by a trailing `---` (#679).

YAML reads that closing marker as a second, empty document, which
`yaml.safe_load` refuses, so every 3.0 helper that read a brief with it
refused every 1.x brief. skf-resolve-authoritative-files.py's
parse_brief_yaml reads the stream, skips a document that holds no value
(empty, or an explicit null) and refuses more than one document that holds
a value; every script that reads a skill brief parses it with it.

The parser's rows first, then each of the ten scripts that read a brief,
given a 1.x brief (accepted) and a brief of two documents (refused through
the script's own YAML error, the text naming "a single document").
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


REPO = Path(__file__).resolve().parent.parent
SHARED = REPO / "src" / "shared" / "scripts"
RESOLVER = SHARED / "skf-resolve-authoritative-files.py"
VALIDATOR = SHARED / "skf-validate-brief-schema.py"
QUICK_BATCH = SHARED / "skf-quick-batch.py"
GAP_DISPATCH = SHARED / "skf-provenance-gap-dispatch.py"
ASSEMBLY_SHAPE = SHARED / "skf-derive-assembly-shape.py"
WRITER = SHARED / "skf-write-skill-brief.py"
EXTRACTOR = SHARED / "skf-extract-public-api.py"
CLASSIFIER = SHARED / "skf-classify-changed-files.py"
REGISTRY = SHARED / "skf-detect-registry.py"
COVERAGE_INPUTS = REPO / "src" / "skf-test-skill" / "scripts" / "load-coverage-inputs.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


resolver = _load(RESOLVER, "skf_resolve_authoritative_files")


BRIEF = {
    "name": "my-skill",
    "version": "1.0.0",
    "source_repo": "https://github.com/foo/bar",
    "language": "python",
    "description": "Compiles things from sources.",
    "forge_tier": "Forge",
    "created": "2026-05-15",
    "created_by": "armel",
    "scope": {"type": "public-api", "include": ["src/**"], "exclude": ["**/test_*"], "notes": ""},
}
BODY = yaml.safe_dump(BRIEF, sort_keys=False)
# What SKF 1.x wrote: the brief between a leading and a trailing marker.
LEGACY = "---\n" + BODY + "---\n"
# A second document that holds something: no reader can tell which is the brief.
TWO_DOCUMENTS = "---\n" + BODY + "---\nname: other-skill\n"
SINGLE = "a single document"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def _source(tmp_path: Path) -> Path:
    """A source tree the brief's scope cuts: one file in scope, one excluded."""
    root = tmp_path / "source"
    _write(root / "src" / "pkg" / "__init__.py", "def hello(x: int) -> int:\n    return x\n")
    _write(root / "src" / "pkg" / "test_hello.py", "def test_hello():\n    pass\n")
    return root


def _run(script: Path, *args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(script), *args], input=stdin, capture_output=True,
                          text=True, encoding="utf-8", timeout=120, check=False)


def _refused(proc: subprocess.CompletedProcess, code: int, wording: str) -> None:
    """The script's own YAML error, with its exit code, naming a single document."""
    assert proc.returncode == code, (proc.returncode, proc.stderr)
    assert wording in proc.stderr and SINGLE in proc.stderr, proc.stderr


@pytest.fixture(params=["legacy", "two-documents"])
def brief(request, tmp_path: Path) -> tuple[str, Path]:
    text = LEGACY if request.param == "legacy" else TWO_DOCUMENTS
    return request.param, _write(tmp_path / "brief" / "skill-brief.yaml", text)


# --------------------------------------------------------------------------
# parse_brief_yaml: the rows of the spec's matrix
# --------------------------------------------------------------------------


@pytest.mark.parametrize("text", [LEGACY, "---\n" + BODY, BODY], ids=["1.x", "3.x-marker", "3.x-bare"])
def test_a_brief_of_one_document_is_its_mapping(text):
    assert resolver.parse_brief_yaml(text) == BRIEF


@pytest.mark.parametrize("text", ["---\n---\n" + BODY, BODY + "---\n~\n", BODY + "---\nnull\n"],
                         ids=["leading-empty", "trailing-tilde", "trailing-null"])
def test_a_document_that_holds_no_value_is_skipped_wherever_it_stands(text):
    assert resolver.parse_brief_yaml(text) == BRIEF


def test_more_than_one_document_that_holds_a_value_is_refused():
    with pytest.raises(yaml.YAMLError, match=SINGLE):
        resolver.parse_brief_yaml("a: 1\n---\nb: 2\n")


@pytest.mark.parametrize("text", ["---\n---\n", ""], ids=["markers-only", "empty"])
def test_a_brief_of_no_document_is_none(text):
    assert resolver.parse_brief_yaml(text) is None


def test_text_that_is_not_yaml_is_still_a_yaml_error():
    with pytest.raises(yaml.YAMLError):
        resolver.parse_brief_yaml("scope: [unclosed\n")


def test_load_brief_reads_a_legacy_brief(tmp_path):
    assert resolver.load_brief(_write(tmp_path / "skill-brief.yaml", LEGACY)) == BRIEF


# --------------------------------------------------------------------------
# The ten scripts that read a skill brief
# --------------------------------------------------------------------------


def test_resolve_authoritative_files(brief, tmp_path):
    kind, path = brief
    proc = _run(RESOLVER, "resolve", "--source-root", str(_source(tmp_path)), "--brief", str(path))
    if kind == "legacy":
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["status"] == "no-candidates"
    else:
        _refused(proc, 1, "is not valid YAML")


def test_validate_brief_schema(brief):
    kind, path = brief
    proc = _run(VALIDATOR, str(path))
    envelope = json.loads(proc.stdout)
    if kind == "legacy":
        assert proc.returncode == 0, proc.stdout
        assert envelope["valid"] is True and envelope["brief"] == BRIEF
    else:
        assert proc.returncode == 1
        assert envelope["halt_reason"] == "brief-malformed"
        message = envelope["errors"][0]["message"]
        assert message.startswith("Brief is not valid YAML") and SINGLE in message


def test_validate_brief_schema_keeps_its_empty_error_for_markers_only(tmp_path):
    proc = _run(VALIDATOR, str(_write(tmp_path / "skill-brief.yaml", "---\n---\n")))
    envelope = json.loads(proc.stdout)
    assert proc.returncode == 1 and envelope["halt_reason"] == "brief-malformed"
    assert envelope["errors"][0]["message"] == "Brief is empty"


def test_quick_batch_start_briefs(brief, tmp_path):
    kind, path = brief
    proc = _run(QUICK_BATCH, "start", "--briefs", str(path), "--run-root", str(tmp_path / "run"))
    assert proc.returncode == 0, proc.stderr
    rejected = json.loads(proc.stdout)["rejected"]
    if kind == "legacy":
        assert rejected == []
    else:
        assert [r["error_code"] for r in rejected] == ["brief-malformed"]
        assert rejected[0]["message"].startswith("Brief is not valid YAML") and SINGLE in rejected[0]["message"]


def test_provenance_gap_dispatch(brief, tmp_path):
    kind, path = brief
    forge = tmp_path / "forge"
    _write(forge / "my-skill" / "1.0.0" / "drift-report-A.md",
           "# Report\n\n## Out-of-Scope Observations\n- `src/new.py` - 1 export\n")
    proc = _run(GAP_DISPATCH, "dispatch", "--skill-name", "my-skill", "--baseline-version", "1.0.0",
                "--forge-data-folder", str(forge), "--brief", str(path))
    if kind == "legacy":
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["status"] == "candidates-found"
    else:
        _refused(proc, 1, "is not valid YAML")


def test_derive_assembly_shape(brief):
    kind, path = brief
    proc = _run(ASSEMBLY_SHAPE, str(path))
    if kind == "legacy":
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout) == {"assembly_shape": "standard", "gate_signal": None}
    else:
        _refused(proc, 2, "Brief is not valid YAML")


def test_write_skill_brief_base_brief(brief, tmp_path):
    kind, path = brief
    target = tmp_path / "out" / "skill-brief.yaml"
    proc = _run(WRITER, "write", "--target", str(target), "--base-brief", str(path))
    if kind == "legacy":
        assert proc.returncode == 0, proc.stderr
        # The rewrite keeps the leading marker only, so it holds one document.
        written = target.read_text(encoding="utf-8")
        assert written.startswith("---\n") and not written.rstrip().endswith("---")
        assert yaml.safe_load(written)["scope"] == BRIEF["scope"]
    else:
        _refused(proc, 1, "is not YAML")
        assert not target.exists()


def test_write_skill_brief_amend(brief):
    kind, path = brief
    entry = {"path": "llms.txt", "action": "skipped", "category": "auth-doc", "reason": "r",
             "date": "2026-10-07", "workflow": "skf-create-skill"}
    proc = _run(WRITER, "amend", "--target", str(path), stdin=json.dumps({"amendments": [entry]}))
    if kind == "legacy":
        assert proc.returncode == 0, proc.stderr
        assert yaml.safe_load(path.read_text(encoding="utf-8"))["scope"]["amendments"] == [entry]
    else:
        _refused(proc, 1, "is not a YAML brief")
        assert path.read_text(encoding="utf-8") == TWO_DOCUMENTS


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


@pytest.mark.skipif(not _pinned_ast_grep(), reason="no ast-grep of the version package.json pins")
def test_extract_public_api_full_mode_applies_a_legacy_briefs_scope(tmp_path):
    path = _write(tmp_path / "skill-brief.yaml", LEGACY)
    proc = _run(EXTRACTOR, "--mode", "full", "--source-root", str(_source(tmp_path)), "--brief", str(path),
                "--tier", "Forge", "--head-cap", "0")
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["status"] == "ok"
    assert (out["scope"]["include"], out["scope"]["exclude"]) == (["src/**"], ["**/test_*"])
    assert out["scope"]["type"] == "public-api" and out["scope"]["languages"] == ["python"]
    assert out["files_in_scope"] == 1, "the brief's exclude leaves the test file out"


def test_extract_public_api_full_mode_refuses_two_documents(tmp_path):
    path = _write(tmp_path / "skill-brief.yaml", TWO_DOCUMENTS)
    proc = _run(EXTRACTOR, "--mode", "full", "--source-root", str(_source(tmp_path)), "--brief", str(path))
    _refused(proc, 2, "is not valid YAML")
    assert proc.stdout == ""


def test_load_coverage_inputs_surface(brief, tmp_path):
    kind, path = brief
    per_file = _write(tmp_path / "per-file-1.json", json.dumps(
        {"file": "src/pkg/__init__.py", "exports_found": ["hello"], "signature_mismatches": []}))
    proc = _run(COVERAGE_INPUTS, "surface", "--per-file", str(per_file), "--name", "unplaced", "--brief", str(path))
    if kind == "legacy":
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["sets"] == {"all": ["hello", "unplaced"], "scope.include": ["hello"]}
    else:
        _refused(proc, 1, "is not valid YAML")


def test_load_coverage_inputs_without_the_shared_parser_is_an_input_error(tmp_path, monkeypatch):
    module = _load(COVERAGE_INPUTS, "load_coverage_inputs_legacy_brief")
    monkeypatch.setattr(module, "SHARED_SCRIPTS", tmp_path)
    monkeypatch.setattr(module, "_SIBLINGS", {})
    with pytest.raises(module.InputError, match="skf-resolve-authoritative-files.py not found"):
        module.read_brief(str(_write(tmp_path / "skill-brief.yaml", LEGACY)))


def test_classify_changed_files(brief, tmp_path):
    kind, path = brief
    proc = _run(CLASSIFIER, "classify", "--source-root", str(_source(tmp_path)), "--brief", str(path))
    if kind == "legacy":
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert out["mode"] == "full"
        assert out["category_a"]["modified"] == ["src/pkg/__init__.py"]
    else:
        _refused(proc, 1, "is not valid YAML")


def test_detect_registry_demo(brief, tmp_path):
    kind, path = brief
    proc = _run(REGISTRY, "demo", "--source-root", str(_source(tmp_path)), "--brief", str(path))
    if kind == "legacy":
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert (out["files_listed"], out["files_scanned"]) == (2, 1)
    else:
        _refused(proc, 2, "is not valid YAML")
