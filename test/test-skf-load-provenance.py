#!/usr/bin/env python3
"""Tests for skf-load-provenance.py.

Covers:
  - normalize: bounded_scan_files union, dedup, POSIX, sorted
  - stack detection: v2 + libraries, v2 + skill_type=stack, v1 + libraries
    (legacy), v1 + skill_type=stack (legacy), neither (single skill)
  - reexport_map: top-level form, per-entry reexported_as form, mixed
  - source_root / baseline_commit / baseline_ref pass-through (and null when
    absent)
  - audit baseline: export_count, generated_at in UTC, age_days from
    generated_at or the file mtime (--now pins the clock)
  - --age-from-last-update (update-skill's baseline, and audit-skill's
    since `baseline` counts the same way): age_days from last_update first,
    the output unchanged without the flag
  - error paths: missing file, malformed JSON, non-object top-level
  - CLI smoke: exit 0 + JSON shape; exit 1 on malformed input
  - baseline (#1132): the compile tier, the scope type and its source
    (metadata.json, else the brief), docs-only from metadata.json alone, the
    no-baseline reason, the tier drop and the 90-day age audit-skill init
    routes on; a docs-only skill never reads its map, and the module still
    loads with no PyYAML
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-load-provenance.py"

spec = importlib.util.spec_from_file_location("skf_load_provenance", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# bounded_scan_files
# --------------------------------------------------------------------------


class TestBoundedScanFiles:
    def test_union_of_entries_and_file_entries(self) -> None:
        data = {
            "entries": [
                {"source_file": "src/auth.ts"},
                {"source_file": "src/util.ts"},
            ],
            "file_entries": [
                {"source_file": "scripts/build.sh"},
                {"source_file": "src/auth.ts"},  # duplicate across both lists
            ],
        }
        assert mod.bounded_scan_files(data) == [
            "scripts/build.sh",
            "src/auth.ts",
            "src/util.ts",
        ]

    def test_empty_map(self) -> None:
        assert mod.bounded_scan_files({}) == []

    def test_normalizes_backslashes_to_posix(self) -> None:
        data = {"entries": [{"source_file": "src\\windows\\thing.ts"}]}
        assert mod.bounded_scan_files(data) == ["src/windows/thing.ts"]

    def test_skips_non_string_source_file(self) -> None:
        data = {
            "entries": [
                {"source_file": None},
                {"source_file": 42},
                {"source_file": "valid.ts"},
                {},
            ],
        }
        assert mod.bounded_scan_files(data) == ["valid.ts"]

    def test_skips_non_dict_entries(self) -> None:
        data = {"entries": ["not an object", {"source_file": "ok.ts"}]}
        assert mod.bounded_scan_files(data) == ["ok.ts"]

    def test_entries_field_not_list_is_ignored(self) -> None:
        data = {"entries": "not a list", "file_entries": [{"source_file": "a.ts"}]}
        assert mod.bounded_scan_files(data) == ["a.ts"]


# --------------------------------------------------------------------------
# detect_stack_flags
# --------------------------------------------------------------------------


class TestDetectStackFlags:
    def test_v2_with_skill_type_stack(self) -> None:
        is_stack, legacy = mod.detect_stack_flags(
            {"provenance_version": "2.0", "skill_type": "stack"}
        )
        assert (is_stack, legacy) == (True, False)

    def test_v2_with_libraries_key(self) -> None:
        is_stack, legacy = mod.detect_stack_flags(
            {"provenance_version": "2.0", "libraries": {"lib-a": {}}}
        )
        assert (is_stack, legacy) == (True, False)

    def test_v1_with_libraries_is_legacy(self) -> None:
        is_stack, legacy = mod.detect_stack_flags(
            {"provenance_version": "1.0", "libraries": ["lib-a"]}
        )
        assert (is_stack, legacy) == (True, True)

    def test_v1_with_skill_type_stack_is_legacy(self) -> None:
        is_stack, legacy = mod.detect_stack_flags(
            {"provenance_version": "1.0", "skill_type": "stack"}
        )
        assert (is_stack, legacy) == (True, True)

    def test_unversioned_with_libraries_is_legacy(self) -> None:
        # absent provenance_version treated as v1
        is_stack, legacy = mod.detect_stack_flags({"libraries": {"x": {}}})
        assert (is_stack, legacy) == (True, True)

    def test_single_skill_not_stack(self) -> None:
        is_stack, legacy = mod.detect_stack_flags(
            {"provenance_version": "2.0", "skill_type": "single"}
        )
        assert (is_stack, legacy) == (False, False)

    def test_empty_map_not_stack(self) -> None:
        assert mod.detect_stack_flags({}) == (False, False)


# --------------------------------------------------------------------------
# extract_reexport_map
# --------------------------------------------------------------------------


class TestExtractReexportMap:
    def test_top_level_reexport_map(self) -> None:
        data = {"reexport_map": {"_Impl": "Public", "_X": "Y"}}
        assert mod.extract_reexport_map(data) == {"_Impl": "Public", "_X": "Y"}

    def test_per_entry_reexported_as(self) -> None:
        data = {
            "entries": [
                {"export_name": "_Internal", "reexported_as": "Public"},
                {"export_name": "AlsoInternal", "reexported_as": "Visible"},
                {"export_name": "NoReexport"},  # skipped
            ],
        }
        assert mod.extract_reexport_map(data) == {
            "_Internal": "Public",
            "AlsoInternal": "Visible",
        }

    def test_top_level_wins_over_per_entry_collision(self) -> None:
        data = {
            "reexport_map": {"_X": "FromTop"},
            "entries": [{"export_name": "_X", "reexported_as": "FromEntry"}],
        }
        assert mod.extract_reexport_map(data) == {"_X": "FromTop"}

    def test_empty_when_neither_form_present(self) -> None:
        assert mod.extract_reexport_map({"entries": [{"export_name": "X"}]}) == {}

    def test_non_dict_reexport_map_ignored(self) -> None:
        assert mod.extract_reexport_map({"reexport_map": "not an object"}) == {}


# --------------------------------------------------------------------------
# File-to-library map (a stack's per-library diff)
# --------------------------------------------------------------------------


class TestSourceLibraryByFile:
    def test_each_file_takes_its_entries_library(self) -> None:
        data = {"entries": [
            {"source_file": "lib-b\\b.ts", "source_library": "lib-b"},
            {"source_file": "lib-a/a.ts", "source_library": "lib-a"},
            {"source_file": "lib-a/a.ts", "source_library": "lib-a"},
            {"source_file": "shared/x.ts", "source_library": "lib-a"},
            {"source_file": "shared/x.ts", "source_library": "lib-b"},
        ]}
        assert mod.source_library_by_file(data) == {"lib-a/a.ts": "lib-a", "lib-b/b.ts": "lib-b",
                                                    "shared/x.ts": "lib-a"}

    @pytest.mark.parametrize("data", [
        {},
        {"entries": "x"},
        {"entries": [{"source_file": "a.ts"}, {"source_file": "b.ts", "source_library": ""},
                     {"source_file": 3, "source_library": "lib"}, "junk"]},
    ], ids=["no-entries", "entries-not-a-list", "no-usable-library"])
    def test_files_without_a_library_are_left_out(self, data) -> None:
        assert mod.source_library_by_file(data) == {}

    def test_normalize_carries_the_map(self) -> None:
        data = {"provenance_version": "2.0", "skill_type": "stack",
                "entries": [{"source_file": "lib-a/a.ts", "source_library": "lib-a"}]}
        assert mod.normalize(data)["source_library_by_file"] == {"lib-a/a.ts": "lib-a"}


# --------------------------------------------------------------------------
# normalize end-to-end
# --------------------------------------------------------------------------


class TestNormalize:
    def test_single_skill_v2(self) -> None:
        data = {
            "provenance_version": "2.0",
            "source_root": "/path/to/src",
            "source_commit": "abc123",
            "source_ref": "v1.0.0",
            "entries": [{"source_file": "src/a.ts"}],
            "file_entries": [{"source_file": "scripts/b.sh"}],
        }
        result = mod.normalize(data)
        assert result == {
            "bounded_scan_files": ["scripts/b.sh", "src/a.ts"],
            "is_stack_skill": False,
            "legacy_stack_provenance": False,
            "compose_mode_stack": False,
            "source_root": "/path/to/src",
            "baseline_commit": "abc123",
            "baseline_ref": "v1.0.0",
            "reexport_map": {},
            "source_library_by_file": {},
            "export_count": 1,
            "generated_at": None,
            "age_days": None,
            "age_source": None,
        }

    def test_stack_skill_v2(self) -> None:
        data = {
            "provenance_version": "2.0",
            "skill_type": "stack",
            "source_root": "/path/to/multi",
            "source_commit": "deadbeef",
            "source_ref": "main",
            "entries": [{"source_file": "lib-a/x.ts"}],
            "reexport_map": {"_X": "Y"},
        }
        result = mod.normalize(data)
        assert result["is_stack_skill"] is True
        assert result["legacy_stack_provenance"] is False
        assert result["compose_mode_stack"] is False
        assert result["reexport_map"] == {"_X": "Y"}

    def test_compose_mode_stack(self) -> None:
        # create-stack-skill's compose-mode variant: null source anchors,
        # entries recorded from constituent skills, and a constituents list.
        data = {
            "provenance_version": "2.0",
            "skill_type": "stack",
            "source_repo": None,
            "source_commit": None,
            "source_ref": None,
            "entries": [{"export_name": "connect", "source_library": "lib-a", "source_file": "src/db.ts",
                         "extraction_method": "compose-from-skill"}],
            "constituents": [{"skill_name": "lib-a", "skill_path": "skills/lib-a/",
                              "metadata_hash": "sha256:" + "0" * 64}],
        }
        result = mod.normalize(data)
        assert (result["is_stack_skill"], result["compose_mode_stack"]) == (True, True)
        assert (result["source_root"], result["baseline_commit"], result["baseline_ref"]) == (None, None, None)

    @pytest.mark.parametrize("data", [
        {"provenance_version": "2.0", "skill_type": "single", "constituents": []},
        {"provenance_version": "2.0", "skill_type": "stack", "constituents": "lib-a"},
    ], ids=["single-skill", "constituents-not-a-list"])
    def test_not_a_compose_mode_stack(self, data) -> None:
        assert mod.normalize(data)["compose_mode_stack"] is False

    def test_legacy_v1_stack(self) -> None:
        data = {
            "provenance_version": "1",
            "libraries": ["lib-a", "lib-b"],
            "entries": [],
        }
        result = mod.normalize(data)
        assert result["is_stack_skill"] is True
        assert result["legacy_stack_provenance"] is True

    def test_empty_map_defaults(self) -> None:
        result = mod.normalize({})
        assert result == {
            "bounded_scan_files": [],
            "is_stack_skill": False,
            "legacy_stack_provenance": False,
            "compose_mode_stack": False,
            "source_root": None,
            "baseline_commit": None,
            "baseline_ref": None,
            "reexport_map": {},
            "source_library_by_file": {},
            "export_count": 0,
            "generated_at": None,
            "age_days": None,
            "age_source": None,
        }

    def test_non_string_scalars_become_null(self) -> None:
        data = {"source_root": 42, "source_commit": None, "source_ref": True}
        result = mod.normalize(data)
        assert result["source_root"] is None
        assert result["baseline_commit"] is None
        assert result["baseline_ref"] is None


# --------------------------------------------------------------------------
# Audit baseline: export_count, generated_at, age_days
# --------------------------------------------------------------------------


NOW = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)


class TestBaselineFacts:
    def test_export_count_counts_entry_objects(self) -> None:
        data = {
            "entries": [{"export_name": "a"}, {"export_name": "b"}, "junk", None],
            "file_entries": [{"source_file": "scripts/x.sh"}],
        }
        assert mod.export_count(data) == 2
        assert mod.export_count({"entries": "not a list"}) == 0
        assert mod.export_count({}) == 0

    def test_generated_at_in_utc_and_age(self) -> None:
        out = mod.provenance_age({"generated_at": "2026-04-04T10:00:00+02:00"}, now=NOW)
        assert out == {"generated_at": "2026-04-04T08:00:00Z", "age_days": 27, "age_source": "generated_at"}

    def test_age_counts_whole_days(self) -> None:
        # 23 hours earlier is 0 days old; the time zone decides the day, not the text.
        out = mod.provenance_age({"generated_at": "2026-05-01T08:00:00-03:00"}, now=NOW)
        assert (out["generated_at"], out["age_days"]) == ("2026-05-01T11:00:00Z", 0)
        out = mod.provenance_age({"generated_at": "2026-04-30T11:59:59Z"}, now=NOW)
        assert out["age_days"] == 1

    def test_future_generated_at_is_zero_days(self) -> None:
        out = mod.provenance_age({"generated_at": "2026-06-01T00:00:00Z"}, now=NOW)
        assert out["age_days"] == 0

    def test_date_only_and_naive_times_read_as_utc(self) -> None:
        assert mod.provenance_age({"generated_at": "2026-04-21"}, now=NOW)["generated_at"] == (
            "2026-04-21T00:00:00Z")
        assert mod.provenance_age({"generated_at": "2026-04-21T06:30:00"}, now=NOW)["generated_at"] == (
            "2026-04-21T06:30:00Z")

    @pytest.mark.parametrize("value", [None, 42, "", "last tuesday", "2026-02-30T00:00:00Z"])
    def test_mtime_fallback(self, value) -> None:
        mtime = datetime(2026, 4, 1, tzinfo=timezone.utc)
        out = mod.provenance_age({"generated_at": value}, mtime=mtime, now=NOW)
        assert out == {"generated_at": None, "age_days": 30, "age_source": "mtime"}

    def test_no_time_known(self) -> None:
        assert mod.provenance_age({}, now=NOW) == {
            "generated_at": None, "age_days": None, "age_source": None}

    def test_normalize_carries_the_facts(self) -> None:
        data = {"generated_at": "2026-04-01T12:00:00Z", "entries": [{"export_name": "a"}]}
        out = mod.normalize(data, now=NOW)
        assert (out["export_count"], out["generated_at"], out["age_days"], out["age_source"]) == (
            1, "2026-04-01T12:00:00Z", 30, "generated_at")


class TestAgeFromLastUpdate:
    """#1193: update-skill's baseline counts the days since the last extraction, the map's `last_update`."""

    MAP = {"generated_at": "2025-07-05T12:00:00Z", "last_update": "2026-04-01T12:00:00Z"}

    def test_last_update_wins_with_the_flag(self) -> None:
        out = mod.provenance_age(self.MAP, now=NOW, from_last_update=True)
        assert out == {"generated_at": "2025-07-05T12:00:00Z", "age_days": 30, "age_source": "last_update"}

    def test_without_the_flag_the_output_is_unchanged(self) -> None:
        out = mod.provenance_age(self.MAP, now=NOW)
        assert out == {"generated_at": "2025-07-05T12:00:00Z", "age_days": 300, "age_source": "generated_at"}
        assert mod.normalize(self.MAP, now=NOW) == mod.normalize(self.MAP, now=NOW, from_last_update=False)

    def test_a_date_alone_reads_as_its_midnight_utc(self) -> None:
        out = mod.provenance_age({**self.MAP, "last_update": "2026-04-01"}, now=NOW, from_last_update=True)
        assert (out["age_days"], out["age_source"]) == (30, "last_update")
        out = mod.provenance_age({**self.MAP, "last_update": "2026-05-01"}, now=NOW, from_last_update=True)
        assert (out["age_days"], out["age_source"]) == (0, "last_update")

    @pytest.mark.parametrize("value", [None, 7, "", "yesterday", "2026-02-30"])
    def test_an_unreadable_last_update_falls_back_to_generated_at(self, value) -> None:
        out = mod.provenance_age({**self.MAP, "last_update": value}, now=NOW, from_last_update=True)
        assert out == {"generated_at": "2025-07-05T12:00:00Z", "age_days": 300, "age_source": "generated_at"}

    def test_then_the_mtime(self) -> None:
        mtime = datetime(2026, 4, 1, tzinfo=timezone.utc)
        out = mod.provenance_age({"last_update": "soon"}, mtime=mtime, now=NOW, from_last_update=True)
        assert out == {"generated_at": None, "age_days": 30, "age_source": "mtime"}


# --------------------------------------------------------------------------
# load_provenance error paths
# --------------------------------------------------------------------------


class TestLoadProvenance:
    def test_loads_object(self, tmp_path: Path) -> None:
        path = _write_json(tmp_path / "p.json", {"source_root": "/x"})
        assert mod.load_provenance(path) == {"source_root": "/x"}

    def test_malformed_json_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        import pytest

        with pytest.raises(ValueError, match="malformed JSON"):
            mod.load_provenance(path)

    def test_top_level_array_raises(self, tmp_path: Path) -> None:
        path = _write_json(tmp_path / "arr.json", [])
        import pytest

        with pytest.raises(ValueError, match="must be a JSON object"):
            mod.load_provenance(path)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        import pytest

        with pytest.raises(ValueError, match="failed to read"):
            mod.load_provenance(tmp_path / "nope.json")


# --------------------------------------------------------------------------
# CLI integration
# --------------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


class TestCli:
    def test_normalize_emits_json(self, tmp_path: Path) -> None:
        path = _write_json(
            tmp_path / "p.json",
            {
                "provenance_version": "2.0",
                "source_root": "/r",
                "source_commit": "abc",
                "source_ref": "v1",
                "entries": [{"source_file": "src/a.ts"}],
            },
        )
        result = _run_cli("normalize", str(path))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["bounded_scan_files"] == ["src/a.ts"]
        assert payload["source_root"] == "/r"
        assert payload["baseline_commit"] == "abc"
        assert payload["baseline_ref"] == "v1"
        assert payload["is_stack_skill"] is False

    def test_normalize_missing_file_exits_1(self, tmp_path: Path) -> None:
        result = _run_cli("normalize", str(tmp_path / "missing.json"))
        assert result.returncode == 1
        assert "not found" in result.stderr

    def test_normalize_malformed_exits_1(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("{nope", encoding="utf-8")
        result = _run_cli("normalize", str(path))
        assert result.returncode == 1
        assert "malformed JSON" in result.stderr

    def test_normalize_empty_object_succeeds(self, tmp_path: Path) -> None:
        # well-formed but empty input should produce empty/null defaults
        path = _write_json(tmp_path / "p.json", {})
        result = _run_cli("normalize", str(path))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["bounded_scan_files"] == []
        assert payload["source_root"] is None

    def test_normalize_now_pins_the_age(self, tmp_path: Path) -> None:
        path = _write_json(
            tmp_path / "p.json",
            {"generated_at": "2026-04-04T10:00:00+02:00", "entries": [{}, {}, {}]},
        )
        result = _run_cli("normalize", str(path), "--now", "2026-05-01T00:00:00Z")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert (payload["export_count"], payload["generated_at"], payload["age_days"], payload["age_source"]) == (
            3, "2026-04-04T08:00:00Z", 26, "generated_at")

    def test_normalize_falls_back_to_mtime(self, tmp_path: Path) -> None:
        path = _write_json(tmp_path / "p.json", {"entries": []})
        os.utime(path, (1767225600, 1767225600))  # 2026-01-01T00:00:00Z
        result = _run_cli("normalize", str(path), "--now", "2026-01-11T06:00:00+00:00")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert (payload["generated_at"], payload["age_days"], payload["age_source"]) == (None, 10, "mtime")

    def test_normalize_age_from_last_update(self, tmp_path: Path) -> None:
        path = _write_json(tmp_path / "p.json", {"generated_at": "2025-07-05T00:00:00Z",
                                                 "last_update": "2026-04-01T00:00:00Z", "entries": [{}]})
        flagged = _run_cli("normalize", str(path), "--now", "2026-05-01T00:00:00Z", "--age-from-last-update")
        plain = _run_cli("normalize", str(path), "--now", "2026-05-01T00:00:00Z")
        assert flagged.returncode == 0 and plain.returncode == 0, (flagged.stderr, plain.stderr)
        flagged, plain = json.loads(flagged.stdout), json.loads(plain.stdout)
        assert (flagged["export_count"], flagged["age_days"], flagged["age_source"]) == (1, 30, "last_update")
        assert (plain["age_days"], plain["age_source"]) == (300, "generated_at")
        assert {k: v for k, v in flagged.items() if k not in ("age_days", "age_source")} == \
            {k: v for k, v in plain.items() if k not in ("age_days", "age_source")}

    def test_normalize_bad_now_exits_1(self, tmp_path: Path) -> None:
        path = _write_json(tmp_path / "p.json", {})
        result = _run_cli("normalize", str(path), "--now", "soon")
        assert result.returncode == 1
        assert "--now" in result.stderr


# --------------------------------------------------------------------------
# baseline (#1132): the facts audit-skill init.md §3 and §7 route on
# --------------------------------------------------------------------------

BASELINE_KEYS = ["original_tier", "scope_type", "scope_type_source", "brief_error", "docs_only_skill",
                 "no_baseline", "compose_mode_stack", "provenance_age_days", "tier_dropped", "baseline_old"]
BASELINE_NOW = "2026-05-01T00:00:00Z"
# A map 30 days old at BASELINE_NOW.
FRESH_MAP = {"generated_at": "2026-04-01T00:00:00Z", "entries": [{"source_file": "src/a.py"}]}
COMPOSE_MAP = {"provenance_version": "2.0", "skill_type": "stack", "generated_at": "2026-04-01T00:00:00Z",
               "constituents": [{"skill_name": "a"}], "entries": []}
# A stack built from code: libraries, no constituents, so steps 2 to 4 run.
CODE_STACK_MAP = {"provenance_version": "2.0", "skill_type": "stack", "generated_at": "2026-04-01T00:00:00Z",
                  "libraries": {"a": {}}, "entries": [{"source_file": "a/x.py", "source_library": "a"}]}


def _skill(tmp_path: Path, metadata: dict, provenance: dict | None = None,
           brief: str | None = None) -> dict[str, Path | None]:
    """metadata.json, and the map and brief when given, in tmp_path."""
    paths = {"metadata": _write_json(tmp_path / "metadata.json", metadata), "provenance": None,
             "brief": tmp_path / "skill-brief.yaml"}
    if provenance is not None:
        paths["provenance"] = _write_json(tmp_path / "provenance-map.json", provenance)
    if brief is not None:
        paths["brief"].write_text(brief, encoding="utf-8")
    return paths


def _baseline(paths: dict, tier: str = "Forge", now: str = BASELINE_NOW, *extra: str) -> dict:
    """The CLI's JSON, as init.md §3 runs it (a null map passed as an empty string)."""
    provenance = paths["provenance"]
    result = _run_cli("baseline", "--metadata", str(paths["metadata"]), "--current-tier", tier,
                      "--brief", str(paths["brief"]), "--provenance-map", str(provenance) if provenance else "",
                      "--now", now, *extra)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert list(payload) == BASELINE_KEYS
    return payload


class TestBaselineCommand:
    @pytest.mark.parametrize("metadata, expected", [
        ({"forge_tier": "Deep", "confidence_tier": "Forge"}, "Deep"),
        ({"forge_tier": "deep", "confidence_tier": "Forge+"}, "Forge+"),
        ({"confidence_tier": "Quick"}, "Quick"),
        ({"forge_tier": "Ultra", "confidence_tier": "T1"}, None),
        ({}, None),
    ], ids=["forge-tier", "invalid-forge-tier-then-confidence", "confidence-tier", "neither-valid", "none"])
    def test_original_tier_chain(self, tmp_path: Path, metadata, expected) -> None:
        payload = _baseline(_skill(tmp_path, metadata, FRESH_MAP))
        assert payload["original_tier"] == expected

    def test_scope_type_from_metadata_wins_over_the_brief(self, tmp_path: Path) -> None:
        paths = _skill(tmp_path, {"scope_type": "component-library"}, FRESH_MAP,
                       "scope:\n  type: public-api\n")
        payload = _baseline(paths)
        assert (payload["scope_type"], payload["scope_type_source"], payload["brief_error"]) == (
            "component-library", "metadata", None)

    @pytest.mark.parametrize("brief", ["scope:\n  type: public-api\n", "scope:\n  type: public-api\n---\n"],
                             ids=["plain", "skf-1x-trailing-separator"])
    def test_scope_type_falls_back_to_the_brief(self, tmp_path: Path, brief) -> None:
        payload = _baseline(_skill(tmp_path, {"name": "demo"}, FRESH_MAP, brief))
        assert (payload["scope_type"], payload["scope_type_source"], payload["brief_error"]) == (
            "public-api", "brief", None)

    @pytest.mark.parametrize("brief", [None, "name: demo\n", "scope:\n  include: [src]\n", "scope: []\n"],
                             ids=["no-brief", "no-scope", "no-type", "scope-not-a-mapping"])
    def test_no_scope_type_anywhere(self, tmp_path: Path, brief) -> None:
        payload = _baseline(_skill(tmp_path, {"name": "demo"}, FRESH_MAP, brief))
        assert (payload["scope_type"], payload["scope_type_source"], payload["brief_error"]) == (None, None, None)

    @pytest.mark.parametrize("brief, needle", [("scope: [\n", "is not valid YAML"),
                                               ("- public-api\n", "must be a YAML mapping"),
                                               ("a: 1\n---\nb: 2\n", "is not valid YAML")],
                             ids=["unparseable", "not-a-mapping", "two-documents"])
    def test_a_brief_that_cannot_be_read_sets_brief_error(self, tmp_path: Path, brief, needle) -> None:
        paths = _skill(tmp_path, {"name": "demo"}, FRESH_MAP, brief)
        payload = _baseline(paths)
        assert payload["scope_type"] is None and payload["scope_type_source"] is None
        assert needle in payload["brief_error"] and str(paths["brief"]) in payload["brief_error"]
        assert "\n" not in payload["brief_error"]

    def test_a_brief_folder_sets_brief_error(self, tmp_path: Path) -> None:
        paths = _skill(tmp_path, {"name": "demo"}, FRESH_MAP)
        paths["brief"].mkdir()
        assert "cannot read brief" in _baseline(paths)["brief_error"]

    def test_a_docs_only_skill_is_never_made_by_the_brief(self, tmp_path: Path) -> None:
        payload = _baseline(_skill(tmp_path, {"name": "demo"}, FRESH_MAP, "scope:\n  type: docs-only\n"))
        assert (payload["scope_type"], payload["scope_type_source"]) == ("docs-only", "brief")
        assert payload["docs_only_skill"] is False and payload["no_baseline"] is None

    @pytest.mark.parametrize("metadata", [{"scope_type": "docs-only"}, {"source_type": "docs-only"}],
                             ids=["scope-type", "older-source-type"])
    def test_a_docs_only_skill_with_hashes_never_reads_its_map(self, tmp_path: Path, metadata) -> None:
        sources = [{"url": "https://x/a.md", "content_hash": None},
                   {"url": "https://x/b.md", "content_hash": "sha256:ab"}]
        paths = _skill(tmp_path, {**metadata, "confidence_tier": "Deep", "doc_sources": sources})
        # A map that would exit 1 if it were read.
        (tmp_path / "provenance-map.json").write_text("[", encoding="utf-8")
        paths["provenance"] = tmp_path / "provenance-map.json"
        payload = _baseline(paths, "Quick")
        assert payload["docs_only_skill"] is True and payload["no_baseline"] is None
        assert (payload["compose_mode_stack"], payload["provenance_age_days"]) == (None, None)
        assert (payload["tier_dropped"], payload["baseline_old"]) == (False, False)

    @pytest.mark.parametrize("sources", [None, [], "x", [{"url": "a", "content_hash": None}],
                                         [{"url": "a"}, "junk", {"url": "b", "content_hash": ""}]],
                             ids=["missing", "empty", "not-a-list", "only-null", "no-hash-string"])
    def test_a_docs_only_skill_without_hashes_has_no_baseline(self, tmp_path: Path, sources) -> None:
        metadata = {"scope_type": "docs-only"}
        if sources is not None:
            metadata["doc_sources"] = sources
        payload = _baseline(_skill(tmp_path, metadata))
        assert payload["docs_only_skill"] is True and payload["no_baseline"] == "no-doc-hashes"

    def test_a_skill_without_a_map_has_no_baseline(self, tmp_path: Path) -> None:
        payload = _baseline(_skill(tmp_path, {"confidence_tier": "Deep"}), "Quick")
        assert payload["no_baseline"] == "no-provenance-map" and payload["docs_only_skill"] is False
        assert (payload["compose_mode_stack"], payload["provenance_age_days"]) == (None, None)
        assert (payload["tier_dropped"], payload["baseline_old"]) == (False, False)

    @pytest.mark.parametrize("metadata, tier, provenance, dropped", [
        ({"confidence_tier": "Forge+"}, "Forge", FRESH_MAP, True),
        ({"forge_tier": "Deep"}, "Quick", FRESH_MAP, True),
        ({"confidence_tier": "Forge+"}, "Forge+", FRESH_MAP, False),
        ({"confidence_tier": "Forge"}, "Deep", FRESH_MAP, False),
        ({"forge_tier": "Forge+"}, "Forge", COMPOSE_MAP, False),
        ({"forge_tier": "Deep"}, "Quick", CODE_STACK_MAP, True),
        ({}, "Quick", FRESH_MAP, False),
    ], ids=["compiled-forge-plus-run-forge", "compiled-deep-run-quick", "same-tier", "higher-tier",
            "compose-stack", "code-mode-stack", "no-original-tier"])
    def test_tier_dropped(self, tmp_path: Path, metadata, tier, provenance, dropped) -> None:
        payload = _baseline(_skill(tmp_path, metadata, provenance), tier)
        assert payload["tier_dropped"] is dropped
        assert payload["compose_mode_stack"] is (provenance is COMPOSE_MAP)

    @pytest.mark.parametrize("now, age, old", [("2026-07-01T00:00:00Z", 91, True),
                                               ("2026-06-30T00:00:00Z", 90, False),
                                               ("2026-06-30T23:59:59Z", 90, False)],
                             ids=["91-days", "90-days", "90-days-and-hours"])
    def test_baseline_old_is_above_90_days(self, tmp_path: Path, now, age, old) -> None:
        payload = _baseline(_skill(tmp_path, {}, FRESH_MAP), "Forge", now)
        assert (payload["provenance_age_days"], payload["baseline_old"]) == (age, old)

    def test_the_age_falls_back_to_the_maps_mtime(self, tmp_path: Path) -> None:
        paths = _skill(tmp_path, {}, {"entries": []})
        os.utime(paths["provenance"], (1767225600, 1767225600))  # 2026-01-01T00:00:00Z
        payload = _baseline(paths, "Forge", "2026-04-11T00:00:00Z")
        assert (payload["provenance_age_days"], payload["baseline_old"]) == (100, True)

    @pytest.mark.parametrize("provenance, compose", [(FRESH_MAP, False), (CODE_STACK_MAP, False),
                                                     (COMPOSE_MAP, True)],
                             ids=["single", "code-mode-stack", "compose-stack"])
    def test_the_function_matches_normalize(self, tmp_path: Path, provenance, compose) -> None:
        """compose_mode_stack and the age are the ones normalize gives for the map, so the
        tier drop §7 asks about and the route §4 takes read the same compose mode."""
        paths = _skill(tmp_path, {"confidence_tier": "Forge"}, provenance)
        now = datetime(2026, 5, 1, tzinfo=timezone.utc)
        facts = mod.baseline(json.loads(paths["metadata"].read_text(encoding="utf-8")), "Forge", None,
                             paths["provenance"], now)
        mtime = datetime.fromtimestamp(paths["provenance"].stat().st_mtime, timezone.utc)
        normalized = mod.normalize(provenance, mtime, now, from_last_update=True)
        assert (facts["compose_mode_stack"], facts["provenance_age_days"]) == (
            normalized["compose_mode_stack"], normalized["age_days"]) == (compose, 30)

    def test_the_age_counts_from_the_last_update(self, tmp_path: Path) -> None:
        """An Update Skill run writes last_update and leaves generated_at as Create Skill wrote it: the
        audit right after it reads the age Update Skill's baseline shows, and never asks to run it again."""
        updated = {**FRESH_MAP, "last_update": "2026-11-12T00:00:00Z"}
        payload = _baseline(_skill(tmp_path, {}, updated), "Forge", "2026-11-14T00:00:00Z")
        assert (payload["provenance_age_days"], payload["baseline_old"]) == (2, False)
        flagged = _run_cli("normalize", str(tmp_path / "provenance-map.json"), "--now", "2026-11-14T00:00:00Z",
                           "--age-from-last-update")
        assert json.loads(flagged.stdout)["age_days"] == 2

    @pytest.mark.parametrize("which, content, needle", [
        ("metadata", None, "metadata.json not found"),
        ("metadata", "{nope", "malformed JSON in metadata.json"),
        ("metadata", "[]", "must be a JSON object"),
        ("provenance", None, "provenance map not found"),
        ("provenance", "{nope", "malformed JSON in provenance map"),
        ("provenance", "[]", "must be a JSON object"),
    ], ids=["metadata-missing", "metadata-malformed", "metadata-not-object", "map-missing", "map-malformed",
            "map-not-object"])
    def test_a_file_it_cannot_use_exits_1(self, tmp_path: Path, which, content, needle) -> None:
        paths = _skill(tmp_path, {"name": "demo"}, FRESH_MAP)
        target = paths[which]
        if content is None:
            target.unlink()
        else:
            target.write_text(content, encoding="utf-8")
        result = _run_cli("baseline", "--metadata", str(paths["metadata"]), "--current-tier", "Forge",
                          "--provenance-map", str(paths["provenance"]))
        assert result.returncode == 1 and result.stdout == ""
        assert result.stderr.startswith("error: ") and needle in result.stderr, result.stderr

    def test_a_folder_in_place_of_metadata_exits_1(self, tmp_path: Path) -> None:
        (tmp_path / "metadata.json").mkdir()
        result = _run_cli("baseline", "--metadata", str(tmp_path / "metadata.json"), "--current-tier", "Forge")
        assert result.returncode == 1 and "failed to read metadata.json" in result.stderr

    def test_a_bad_now_exits_1(self, tmp_path: Path) -> None:
        paths = _skill(tmp_path, {}, FRESH_MAP)
        result = _run_cli("baseline", "--metadata", str(paths["metadata"]), "--current-tier", "Forge",
                          "--now", "soon")
        assert result.returncode == 1 and "--now" in result.stderr

    @pytest.mark.parametrize("tier", ["forge", "Ultra", ""])
    def test_the_current_tier_must_be_a_tier(self, tmp_path: Path, tier) -> None:
        paths = _skill(tmp_path, {}, FRESH_MAP)
        result = _run_cli("baseline", "--metadata", str(paths["metadata"]), "--current-tier", tier)
        assert result.returncode == 2 and "invalid choice" in result.stderr

    def test_the_module_loads_without_pyyaml_and_a_brief_then_reports_it(self, tmp_path: Path) -> None:
        """skf-extraction-snapshot.py loads this module with no dependencies, so its top level stays
        standard-library only; reading a brief then needs PyYAML, and its absence is a brief_error."""
        paths = _skill(tmp_path, {"name": "demo"}, FRESH_MAP, "scope:\n  type: public-api\n")
        code = (
            "import importlib.util, json, sys\n"
            "from pathlib import Path\n"
            "sys.modules['yaml'] = None\n"
            f"spec = importlib.util.spec_from_file_location('m', {str(SCRIPT_PATH)!r})\n"
            "m = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(m)\n"
            "assert m.bounded_scan_files({'entries': [{'source_file': 'a'}]}) == ['a']\n"
            f"facts = m.baseline({{'name': 'demo'}}, 'Forge', Path({str(paths['brief'])!r}), "
            f"Path({str(paths['provenance'])!r}))\n"
            "print(json.dumps(facts))\n"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
        facts = json.loads(result.stdout)
        assert facts["scope_type"] is None
        assert facts["brief_error"].startswith("cannot load skf-resolve-authoritative-files.py beside "
                                               "skf-load-provenance.py")


class TestScriptPEP723:
    """`baseline` reads a brief through skf-resolve-authoritative-files.py, which imports PyYAML:
    under `uv run` only the header's dependencies are there, so it must declare it."""

    def test_pyyaml_dependency(self) -> None:
        text = SCRIPT_PATH.read_text(encoding="utf-8")
        header = text[: text.index("# ///", text.index("# /// script") + 1)]
        assert '# requires-python = ">=3.11"' in header and 'dependencies = ["pyyaml"]' in header
