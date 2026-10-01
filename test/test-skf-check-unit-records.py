#!/usr/bin/env python3
"""Tests for skf-check-unit-records.py, which skf-analyze-source's step 4 runs.

Each subagent of map-and-detect section 2 writes its record as a file and
returns only its path; the script strips a wrapping fence, parses and checks
every record against the contract, so the parent neither copies a record
nor checks one by hand (#592, analyze-source determinism-11).
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "src" / "shared" / "scripts" / "skf-check-unit-records.py"
MAP = REPO / "src" / "skf-analyze-source" / "references" / "map-and-detect.md"
UNIT_EXPORTS = REPO / "src" / "skf-analyze-source" / "references" / "map-unit-exports.md"

spec = importlib.util.spec_from_file_location("skf_check_unit_records", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

GOOD = {
    "unit_name": "auth",
    "files_count": 12,
    "exports_count": 7,
    "export_pattern": "barrel: 5 functions, 2 classes",
    "api_surface": ["login", "logout"],
    "scripts_assets": {"scripts": [], "assets": []},
    "ccc_signals": {"top_files": [], "available": False},
    "strategy_used": "ast-grep",
    "confidence": "T1",
    "warnings": ["extraction gap: refresh at src/token.ts:40"],
}


def _folder(tmp_path: Path, replies: dict[str, str]) -> Path:
    folder = tmp_path / "unit-records"
    folder.mkdir()
    for name, text in replies.items():
        (folder / name).write_bytes(text.encode("utf-8"))
    return folder


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, timeout=60)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(json.dumps(GOOD), id="plain"),
        pytest.param("```json\n" + json.dumps(GOOD, indent=2) + "\n```\n", id="json-fence"),
        pytest.param("```\r\n" + json.dumps(GOOD) + "\r\n```", id="bare-fence-crlf"),
        pytest.param("Here is the record:\n" + json.dumps(GOOD) + "\nDone.", id="prose-around"),
        pytest.param("﻿" + json.dumps(GOOD), id="byte-order-mark"),
    ],
)
def test_a_good_reply_gives_its_record_unchanged(tmp_path, text):
    out = mod.check_folder(_folder(tmp_path, {"auth.json": text}))
    assert out["records"] == [GOOD]
    assert (out["problems"], out["unreadable"]) == ([], [])
    assert out["warnings"] == ["auth: extraction gap: refresh at src/token.ts:40"]


def test_a_missing_or_wrong_key_degrades_the_record_and_names_the_problem(tmp_path):
    record = {k: v for k, v in GOOD.items() if k != "exports_count"}
    record.update({"confidence": "T2", "api_surface": "login", "extra": 1})
    out = mod.check_folder(_folder(tmp_path, {"auth.json": json.dumps(record)}))
    [checked] = out["records"]
    assert (checked["exports_count"], checked["confidence"], checked["api_surface"]) == (0, "T1-low", [])
    assert checked["extra"] == 1, "a key the contract does not name is kept"
    problems = [p["problem"] for p in out["problems"]]
    assert problems[0] == "missing key exports_count"
    assert any(p.startswith("key api_surface has the wrong type") for p in problems)
    assert any(p.startswith("key confidence has the wrong type") for p in problems)
    assert {p["unit_name"] for p in out["problems"]} == {"auth"}


def test_counts_reject_booleans_and_negatives(tmp_path):
    out = mod.check_folder(_folder(tmp_path, {"a.json": json.dumps({**GOOD, "files_count": True,
                                                                     "exports_count": -1})}))
    assert (out["records"][0]["files_count"], out["records"][0]["exports_count"]) == (0, 0)
    assert len(out["problems"]) == 2


def test_a_reply_with_no_object_is_unreadable(tmp_path):
    folder = _folder(tmp_path, {"a.json": json.dumps(GOOD), "b.json": "I could not read the unit.",
                                "c.json": "[1, 2]", "d.json": ""})
    out = mod.check_folder(folder)
    assert [r["unit_name"] for r in out["records"]] == ["auth"]
    assert out["unreadable"] == ["b.json", "c.json", "d.json"]


def test_records_come_in_file_name_order(tmp_path):
    folder = _folder(tmp_path, {f"{n}.json": json.dumps({**GOOD, "unit_name": n}) for n in ("zeta", "alpha", "mid")})
    assert [r["unit_name"] for r in mod.check_folder(folder)["records"]] == ["alpha", "mid", "zeta"]


def test_the_cli_prints_the_result_and_refuses_a_missing_folder(tmp_path):
    folder = _folder(tmp_path, {"auth.json": "```json\n" + json.dumps({**GOOD, "unit_name": "café"}) + "\n```"})
    proc = subprocess.run([sys.executable, str(SCRIPT), "--dir", str(folder)], capture_output=True, timeout=60,
                          env={**os.environ, "PYTHONIOENCODING": "cp1252"})
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.decode("utf-8"))["records"][0]["unit_name"] == "café"
    missing = _run("--dir", str(tmp_path / "absent"))
    assert missing.returncode == 2 and b"is not a folder" in missing.stderr


def test_map_and_detect_runs_the_check_instead_of_stripping_fences_by_hand():
    # map-and-detect resolves the helper; the export mapping it loads (as the
    # [D] file does) runs it.
    assert ("checkUnitRecordsProbeOrder:\n  - '{project-root}/_bmad/skf/shared/scripts/skf-check-unit-records.py'"
            in MAP.read_text(encoding="utf-8"))
    text = UNIT_EXPORTS.read_text(encoding="utf-8")
    assert 'uv run {checkUnitRecordsHelper} --dir "{run_dir}/unit-records"' in text
    assert "Strip any wrapping markdown fences" not in text
    assert "Validate each payload against the contract" not in text
    # The contract the script checks is the one the prose shows the subagents.
    block = text.split("## 3. Record Contract", 1)[1].split("```json\n", 1)[1].split("```", 1)[0]
    keys = re.findall(r'^\s*"([a-z_]+)":', block, re.M)
    assert keys == list(mod.CONTRACT)
