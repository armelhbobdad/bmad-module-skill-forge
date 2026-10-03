#!/usr/bin/env python3
"""Tests for skf-recommend-scope-type.py.

The script is pure: it walks a fixed ladder over a payload of analysis
facts and the intent signals the caller classified, and returns a
recommendation. It reads no free text. Tests build payloads inline and
call recommend() directly, plus subprocess cases for the CLI and its
--tree-file, --registry-files and --entry-dir inputs, and checks that the
call scope-definition.md documents works: its payload is one the script
accepts, and its bash block, run on the file list step 2 staged in the run
folder with skf-github-fetch.py reading from a local folder, fetches and
reads the registry file, counts step 2's exports from its --extract-file
and exits with the script's status.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
SCRIPT_PATH = REPO / "src" / "shared" / "scripts" / "skf-recommend-scope-type.py"
SCOPE_DEFINITION = REPO / "src" / "skf-brief-skill" / "references" / "scope-definition.md"
ANALYZE_TARGET = REPO / "src" / "skf-brief-skill" / "references" / "analyze-target.md"
BASH = shutil.which("bash")
GIT = shutil.which("git")
# The documented block is POSIX shell; on Windows `bash` may be WSL's launcher.
POSIX_BASH = BASH is not None and sys.platform != "win32"

spec = importlib.util.spec_from_file_location("skf_recommend_scope_type", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

VALID_SCOPE_TYPES = {
    "full-library",
    "specific-modules",
    "public-api",
    "component-library",
    "reference-app",
    "docs-only",
}

VALID_HEURISTICS = {
    "component-registry",
    "reference-app-intent",
    "specific-modules-naming",
    "specific-modules-count",
    "narrow-public-api",
    "default-full-library",
    "docs-only-shortcircuit",
}

NO_SIGNALS = {"wants_wiring_pattern": False, "named_module_subset": [], "wants_narrow_api": False}


def signals(**overrides) -> dict:
    return {**NO_SIGNALS, **overrides}


def payload(**fields) -> dict:
    """A source payload whose intent asks for nothing narrower, plus `fields`."""
    return {"signals": signals(), "tree": [], "mode": "interactive", **fields}


def assert_result_shape(result: dict) -> None:
    assert set(result.keys()) >= {"scope_type", "matched_heuristic", "signals", "rationale"}
    assert result["scope_type"] in VALID_SCOPE_TYPES
    assert result["matched_heuristic"] in VALID_HEURISTICS
    assert isinstance(result["signals"], dict)
    assert isinstance(result["rationale"], str) and result["rationale"]
    assert chr(0x2014) not in result["rationale"]  # no em dash: the reason is written into briefs


def run_cli(*args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )


# --------------------------------------------------------------------------
# Short-circuit: docs-only
# --------------------------------------------------------------------------


def test_docs_only_short_circuits_before_any_other_rule():
    result = mod.recommend(
        payload(
            signals=signals(wants_wiring_pattern=True, named_module_subset=["auth"]),
            module_count=99,
            export_count=3,
            tree=["src/components/registry.ts"],
            source_type="docs-only",
        )
    )
    assert_result_shape(result)
    assert result["scope_type"] == "docs-only"
    assert result["matched_heuristic"] == "docs-only-shortcircuit"


def test_docs_only_needs_no_signals():
    result = mod.recommend({"source_type": "docs-only", "mode": "headless"})
    assert result["scope_type"] == "docs-only"


# --------------------------------------------------------------------------
# Rule 1: component-registry
# --------------------------------------------------------------------------


def test_interactive_registry_with_10_plus_entries():
    content = "export const registry: Component[] = [" + ",".join(["{ id: 'x' }"] * 12) + "];"
    result = mod.recommend(
        payload(
            tree=["src/components/registry.ts"],
            entry_files=[{"path": "src/components/registry.ts", "content": content}],
        )
    )
    assert_result_shape(result)
    assert result["scope_type"] == "component-library"
    assert result["matched_heuristic"] == "component-registry"
    assert result["signals"]["registry_path"] == "src/components/registry.ts"
    assert result["signals"]["contents_inspected"] is True


def test_interactive_registry_with_component_array_annotation_passes_even_with_few_entries():
    content = "const registry: Component[] = [{id:'a'},{id:'b'}];"
    result = mod.recommend(
        payload(
            tree=["src/components/registry.tsx"],
            entry_files=[{"path": "src/components/registry.tsx", "content": content}],
        )
    )
    assert result["scope_type"] == "component-library"
    assert result["signals"]["component_array_annotation"] is True


def test_interactive_registry_with_few_entries_and_no_annotation_does_not_match():
    content = "const x = [{a:1},{b:2}];"
    result = mod.recommend(
        payload(
            tree=["src/components/registry.ts"],
            entry_files=[{"path": "src/components/registry.ts", "content": content}],
            module_count=0,
            export_count=5,
        )
    )
    assert result["scope_type"] == "full-library"


def test_headless_falls_back_to_presence_only_when_no_contents():
    result = mod.recommend(payload(tree=["src/components/registry.ts"], entry_files=None, mode="headless"))
    assert_result_shape(result)
    assert result["scope_type"] == "component-library"
    assert result["signals"]["contents_inspected"] is False


def test_interactive_without_contents_does_not_match_component_library():
    result = mod.recommend(payload(tree=["src/components/registry.ts"], entry_files=None))
    assert result["scope_type"] == "full-library"


def test_headless_contents_that_disqualify_do_not_match():
    """Headless counts a registry file by presence only when its contents were not given."""
    result = mod.recommend(
        payload(
            tree=["src/components/registry.ts"],
            entry_files=[{"path": "src/components/registry.ts", "content": "const x = [{a:1}];"}],
            mode="headless",
        )
    )
    assert result["scope_type"] == "full-library"


def test_headless_presence_match_names_a_registry_file_without_contents():
    result = mod.recommend(
        payload(
            tree=["a/registry.ts", "b/components.ts"],
            entry_files=[{"path": "a/registry.ts", "content": "const x = [{a:1}];"}],
            mode="headless",
        )
    )
    assert result["scope_type"] == "component-library"
    assert result["signals"]["registry_path"] == "b/components.ts"
    assert result["signals"]["contents_inspected"] is False


def test_paths_outside_the_repository_are_not_registry_files():
    tree = ["../x/registry.ts", "/abs/components.ts", "a/../registry.ts", "ok/registry.tsx"]
    assert mod._find_registry_files(tree) == ["ok/registry.tsx"]


# --------------------------------------------------------------------------
# Rule 2: reference-app, from the wants_wiring_pattern signal
# --------------------------------------------------------------------------


def test_wiring_pattern_signal_recommends_reference_app():
    result = mod.recommend(payload(signals=signals(wants_wiring_pattern=True)))
    assert_result_shape(result)
    assert result["scope_type"] == "reference-app"
    assert result["matched_heuristic"] == "reference-app-intent"
    assert result["signals"] == {"wants_wiring_pattern": True}


def test_structural_count_rule_fires_when_no_wiring_is_wanted():
    """An intent about a library's lifecycle API is no wiring pattern, so the
    structural specific-modules rule decides."""
    result = mod.recommend(payload(module_count=6))
    assert result["scope_type"] == "specific-modules"
    assert result["matched_heuristic"] == "specific-modules-count"
    assert result["signals"]["module_count"] == 6


# --------------------------------------------------------------------------
# Rule 3: specific-modules, from named_module_subset or the module count
# --------------------------------------------------------------------------


def test_named_module_subset_recommends_specific_modules():
    result = mod.recommend(payload(signals=signals(named_module_subset=["auth", " streaming "])))
    assert_result_shape(result)
    assert result["scope_type"] == "specific-modules"
    assert result["matched_heuristic"] == "specific-modules-naming"
    assert result["signals"] == {"named_module_subset": ["auth", "streaming"]}
    assert "auth, streaming" in result["rationale"]


def test_specific_modules_count_when_no_module_is_named():
    result = mod.recommend(payload(module_count=8))
    assert result["scope_type"] == "specific-modules"
    assert result["matched_heuristic"] == "specific-modules-count"
    assert result["signals"]["module_count"] == 8


def test_module_count_below_threshold_does_not_trigger():
    result = mod.recommend(payload(module_count=5, export_count=50))
    assert result["scope_type"] == "full-library"


# --------------------------------------------------------------------------
# Rule 4: narrow-public-api, from wants_narrow_api and the export count
# --------------------------------------------------------------------------


def test_narrow_public_api_match_with_signal_and_small_export_count():
    result = mod.recommend(payload(signals=signals(wants_narrow_api=True), export_count=6))
    assert_result_shape(result)
    assert result["scope_type"] == "public-api"
    assert result["matched_heuristic"] == "narrow-public-api"
    assert result["signals"] == {"wants_narrow_api": True, "export_count": 6}


def test_narrow_public_api_signal_without_small_exports_does_not_trigger():
    result = mod.recommend(payload(signals=signals(wants_narrow_api=True), export_count=47))
    assert result["scope_type"] == "full-library"


def test_narrow_public_api_signal_with_unknown_export_count_does_not_trigger():
    result = mod.recommend(payload(signals=signals(wants_narrow_api=True), export_count=0))
    assert result["scope_type"] == "full-library"


def test_small_exports_without_signal_does_not_trigger():
    result = mod.recommend(payload(export_count=4))
    assert result["scope_type"] == "full-library"


# --------------------------------------------------------------------------
# Rule 5: default-full-library
# --------------------------------------------------------------------------


def test_default_full_library_when_no_signal_matches():
    result = mod.recommend(payload(module_count=2, export_count=30))
    assert_result_shape(result)
    assert result["scope_type"] == "full-library"
    assert result["matched_heuristic"] == "default-full-library"


# --------------------------------------------------------------------------
# Rule precedence
# --------------------------------------------------------------------------


def test_component_registry_takes_precedence_over_wiring_pattern():
    """When both fire, component-registry wins (rule 1 before rule 2)."""
    content = "const r: Component[] = [];"
    result = mod.recommend(
        payload(
            signals=signals(wants_wiring_pattern=True),
            tree=["src/components/registry.ts"],
            entry_files=[{"path": "src/components/registry.ts", "content": content}],
        )
    )
    assert result["scope_type"] == "component-library"


def test_wiring_pattern_takes_precedence_over_named_modules():
    """When both fire, reference-app wins (rule 2 before rule 3)."""
    result = mod.recommend(
        payload(signals=signals(wants_wiring_pattern=True, named_module_subset=["auth"]), module_count=99)
    )
    assert result["scope_type"] == "reference-app"


def test_named_modules_take_precedence_over_narrow_api():
    """When both fire, specific-modules wins (rule 3 before rule 4)."""
    result = mod.recommend(
        payload(signals=signals(named_module_subset=["client"], wants_narrow_api=True), export_count=4)
    )
    assert result["scope_type"] == "specific-modules"


# --------------------------------------------------------------------------
# The script reads no free text (issue #582)
# --------------------------------------------------------------------------

# The intents the issue reproduced: substring and negated mentions that the
# keyword matcher misread. The caller classifies each one by meaning (the
# signals below are what scope-definition.md section 2c tells it to set),
# and the script only applies the ladder.
ISSUE_INTENTS = [
    pytest.param(
        "Cover the whole library, not just the parser module",
        signals(),
        {},
        "full-library",
        id="negated-subset",
    ),
    pytest.param(
        "Document the Kickstarter-style campaign SDK",
        signals(),
        {},
        "full-library",
        id="starter-substring",
    ),
    pytest.param(
        "I want the public API of the client library, not a demo app or starter template",
        signals(wants_narrow_api=True),
        {"export_count": 5},
        "public-api",
        id="negated-demo-app",
    ),
    pytest.param(
        "narrow to the auth module",
        signals(named_module_subset=["auth"]),
        {"module_count": 0},
        "specific-modules",
        id="ratify-narrowing",
    ),
]


@pytest.mark.parametrize("intent,classified,facts,expected", ISSUE_INTENTS)
def test_issue_intents_follow_their_classified_signals(intent, classified, facts, expected):
    result = mod.recommend(payload(signals=classified, **facts))
    assert result["scope_type"] == expected


@pytest.mark.parametrize("intent,classified,facts,expected", ISSUE_INTENTS)
def test_issue_intents_are_refused_as_free_text(intent, classified, facts, expected, capsys):
    with pytest.raises(SystemExit) as exc_info:
        mod.recommend({"intent": intent, **payload(**facts)})
    assert exc_info.value.code == 2
    assert "intent is free text" in capsys.readouterr().err


def test_scope_hint_is_refused_as_free_text():
    with pytest.raises(SystemExit) as exc_info:
        mod.recommend(payload(scope_hint="just the parser"))
    assert exc_info.value.code == 2


def test_no_keyword_tables_remain():
    for name in ("REFERENCE_APP_KEYWORDS", "NARROW_PUBLIC_API_KEYWORDS", "SPECIFIC_MODULE_NAMING_PATTERNS"):
        assert not hasattr(mod, name), name


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def test_invalid_source_type_dies():
    with pytest.raises(SystemExit) as exc_info:
        mod.recommend(payload(source_type="weird"))
    assert exc_info.value.code == 2


def test_invalid_mode_dies():
    with pytest.raises(SystemExit) as exc_info:
        mod.recommend(payload(mode="background"))
    assert exc_info.value.code == 2


@pytest.mark.parametrize(
    "bad_signals",
    [
        pytest.param(None, id="absent"),
        pytest.param([], id="not-an-object"),
        pytest.param({"wants_wiring_pattern": False, "wants_narrow_api": False}, id="missing-key"),
        pytest.param({**NO_SIGNALS, "wants_whole_library": True}, id="unknown-key"),
        pytest.param({**NO_SIGNALS, "wants_wiring_pattern": "yes"}, id="string-for-bool"),
        pytest.param({**NO_SIGNALS, "wants_narrow_api": 1}, id="int-for-bool"),
        pytest.param({**NO_SIGNALS, "named_module_subset": True}, id="bool-for-list"),
        pytest.param({**NO_SIGNALS, "named_module_subset": "auth"}, id="string-for-list"),
        pytest.param({**NO_SIGNALS, "named_module_subset": ["auth", " "]}, id="blank-name"),
    ],
)
def test_malformed_signals_die(bad_signals):
    body = payload()
    if bad_signals is None:
        del body["signals"]
    else:
        body["signals"] = bad_signals
    with pytest.raises(SystemExit) as exc_info:
        mod.recommend(body)
    assert exc_info.value.code == 2


@pytest.mark.parametrize(
    "field,value",
    [
        pytest.param("module_count", -1, id="negative"),
        pytest.param("module_count", "7", id="string"),
        pytest.param("export_count", True, id="bool"),
        pytest.param("export_count", 2.5, id="float"),
    ],
)
def test_malformed_counts_die(field, value):
    with pytest.raises(SystemExit) as exc_info:
        mod.recommend(payload(**{field: value}))
    assert exc_info.value.code == 2


def test_unknown_payload_key_dies():
    with pytest.raises(SystemExit) as exc_info:
        mod.recommend(payload(module_counts=7))
    assert exc_info.value.code == 2


def test_tree_that_is_not_a_list_dies():
    with pytest.raises(SystemExit) as exc_info:
        mod.recommend(payload(tree="src/components/registry.ts"))
    assert exc_info.value.code == 2


# --------------------------------------------------------------------------
# --tree-file (issue #592)
# --------------------------------------------------------------------------

REGISTRY = "packages/ui/src/registry.ts"
HEADLESS = json.dumps({"signals": NO_SIGNALS, "mode": "headless"})


def _tree_file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "tree.json"
    path.write_bytes(text.encode("utf-8"))
    return path


@pytest.mark.parametrize(
    "listing",
    [
        pytest.param(
            json.dumps({"status": "ok", "repo": "o/r", "ref": "HEAD", "tree": ["README.md", REGISTRY],
                        "count": 2, "truncated": False}),
            id="github-probe-output",
        ),
        pytest.param(
            json.dumps({"sha": "abc", "truncated": False, "tree": [
                {"path": "packages", "type": "tree"},
                {"path": REGISTRY, "type": "blob", "mode": "100644"},
            ]}),
            id="git-trees-response",
        ),
        pytest.param(json.dumps({"tree": ["README.md", REGISTRY]}), id="gh-jq-object"),
        pytest.param(json.dumps(["README.md", REGISTRY]), id="json-list"),
        pytest.param(f"README.md\n{REGISTRY}\n", id="git-ls-files-lines"),
        pytest.param(f"./README.md\r\n./{REGISTRY}\r\n\r\n", id="find-dot-lines-crlf"),
        pytest.param(f"[locale]/page.tsx\n{{slug}}/view.ts\n{REGISTRY}\n", id="lines-opening-with-brackets"),
        pytest.param("\ufeff" + json.dumps({"tree": [REGISTRY]}), id="json-with-bom"),
    ],
)
def test_tree_file_formats_reach_the_registry_rule(tmp_path, listing):
    tree_file = _tree_file(tmp_path, listing)
    proc = run_cli("--tree-file", str(tree_file), stdin=HEADLESS)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["scope_type"] == "component-library"
    assert out["signals"]["registry_path"] == REGISTRY


def test_tree_file_directory_entries_do_not_count(tmp_path):
    listing = json.dumps({"tree": [{"path": "src/registry.ts", "type": "tree"}]})
    proc = run_cli("--tree-file", str(_tree_file(tmp_path, listing)), stdin=HEADLESS)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["scope_type"] == "full-library"


def test_tree_file_dash_reads_the_listing_from_stdin():
    listing = json.dumps({"status": "ok", "tree": [REGISTRY]})
    proc = run_cli("--tree-file", "-", "--json", HEADLESS, stdin=listing)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["signals"]["registry_path"] == REGISTRY


def test_tree_file_dash_needs_the_payload_from_json():
    proc = run_cli("--tree-file", "-", stdin=HEADLESS)
    assert proc.returncode == 2
    assert "--json" in proc.stderr


def test_large_tree_file_is_read_whole(tmp_path):
    """A tree past 10,000 files reaches the script whole: the registry is the last path."""
    paths = [f"src/pkg{i // 100}/mod{i}.ts" for i in range(12000)] + ["src/deep/ui/components.tsx"]
    tree_file = _tree_file(tmp_path, json.dumps({"status": "ok", "tree": paths}))
    proc = run_cli("--tree-file", str(tree_file), stdin=HEADLESS)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["signals"]["registry_path"] == "src/deep/ui/components.tsx"


def test_payload_with_an_apostrophe_reaches_the_script_through_stdin(tmp_path):
    """The payload travels on stdin (a quoted heredoc in the prose), so a
    registry file's quotes cannot break a shell string."""
    content = "export const registry: Component[] = [{ name: 'button' }]; // it's the list"
    body = json.dumps({"signals": NO_SIGNALS, "mode": "interactive",
                       "entry_files": [{"path": REGISTRY, "content": content}]})
    proc = run_cli("--tree-file", str(_tree_file(tmp_path, f"{REGISTRY}\n")), stdin=body)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["scope_type"] == "component-library"
    assert out["signals"]["contents_inspected"] is True


@pytest.mark.parametrize(
    "listing,message",
    [
        pytest.param(
            json.dumps({"status": "unavailable", "cause": "unreachable", "tree": [],
                        "message": "Could not reach GitHub to read o/r (timeout); try again later."}),
            "Could not reach GitHub",
            id="failed-probe",
        ),
        pytest.param(json.dumps({"message": "Not Found", "status": "404"}), "Not Found", id="gh-api-error"),
        pytest.param(json.dumps({"message": "Bad credentials"}), "no list of paths", id="no-tree-key"),
        pytest.param("", "is empty", id="empty"),
        pytest.param("  \n", "is empty", id="blank"),
        pytest.param('{"tree": [', "not valid JSON", id="truncated-json"),
    ],
)
def test_unusable_tree_file_dies(tmp_path, listing, message):
    proc = run_cli("--tree-file", str(_tree_file(tmp_path, listing)), stdin=HEADLESS)
    assert proc.returncode == 2
    assert message in proc.stderr
    assert proc.stdout == ""


def test_missing_tree_file_dies(tmp_path):
    proc = run_cli("--tree-file", str(tmp_path / "absent.json"), stdin=HEADLESS)
    assert proc.returncode == 2
    assert "cannot read --tree-file" in proc.stderr


def test_tree_given_twice_dies(tmp_path):
    body = json.dumps({"signals": NO_SIGNALS, "tree": [REGISTRY]})
    proc = run_cli("--tree-file", str(_tree_file(tmp_path, f"{REGISTRY}\n")), stdin=body)
    assert proc.returncode == 2
    assert "pass the tree once" in proc.stderr


# --------------------------------------------------------------------------
# --registry-files and --entry-dir: the script finds and reads the registry
# files, so the caller only fetches the paths it lists
# --------------------------------------------------------------------------

LISTING = f"README.md\n{REGISTRY}\nsrc/ui/components.tsx\n"
REGISTRY_12 = "export const registry = [" + ",".join(["{ name: 'x' }"] * 12) + "];"


def _entry_dir(tmp_path: Path, files: dict[str, str]) -> Path:
    """A folder laid out like the repository, holding `files` (repo path -> contents)."""
    root = tmp_path / "checkout"
    root.mkdir()
    for rel, content in files.items():
        path = root.joinpath(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))
    return root


def test_registry_files_prints_one_path_per_line(tmp_path):
    tree_file = _tree_file(tmp_path, LISTING + "../outside/registry.ts\n")
    proc = subprocess.run([sys.executable, str(SCRIPT_PATH), "--tree-file", str(tree_file), "--registry-files"],
                          capture_output=True, timeout=30, check=False)
    assert proc.returncode == 0, proc.stderr
    # Bytes, not text: a shell loop reads these lines, so no CR on Windows.
    assert proc.stdout == f"{REGISTRY}\nsrc/ui/components.tsx\n".encode()


def test_registry_files_prints_nothing_without_a_registry(tmp_path):
    proc = run_cli("--tree-file", str(_tree_file(tmp_path, "README.md\nsrc/index.ts\n")), "--registry-files")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""


def test_registry_files_refuses_a_failed_listing(tmp_path):
    listing = json.dumps({"status": "unavailable", "tree": [], "message": "Could not reach GitHub to read o/r."})
    proc = run_cli("--tree-file", str(_tree_file(tmp_path, listing)), "--registry-files")
    assert proc.returncode == 2
    assert "Could not reach GitHub" in proc.stderr
    assert proc.stdout == ""


@pytest.mark.parametrize(
    "extra",
    [
        pytest.param([], id="no-tree-file"),
        pytest.param(["--json", "{}"], id="with-payload"),
        pytest.param(["--entry-dir", "."], id="with-entry-dir"),
        pytest.param(["--extract-file", "extract.json"], id="with-extract-file"),
    ],
)
def test_registry_files_reads_only_the_tree_file(tmp_path, extra):
    tree = [] if not extra else ["--tree-file", str(_tree_file(tmp_path, LISTING))]
    proc = run_cli(*tree, "--registry-files", *extra)
    assert proc.returncode == 2
    assert "--registry-files" in proc.stderr


@pytest.mark.parametrize("mode", ["interactive", "headless"])
def test_entry_dir_contents_decide_the_registry_rule(tmp_path, mode):
    folder = _entry_dir(tmp_path, {REGISTRY: REGISTRY_12})
    body = json.dumps({"signals": NO_SIGNALS, "mode": mode})
    proc = run_cli("--tree-file", str(_tree_file(tmp_path, LISTING)), "--entry-dir", str(folder), stdin=body)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["scope_type"] == "component-library"
    assert out["signals"] == {"registry_path": REGISTRY, "entry_count": 12,
                              "component_array_annotation": False, "contents_inspected": True}


@pytest.mark.parametrize("mode", ["interactive", "headless"])
def test_entry_dir_contents_that_disqualify_decide_in_both_modes(tmp_path, mode):
    folder = _entry_dir(tmp_path, {REGISTRY: "export const x = [{ a: 1 }];", "src/ui/components.tsx": "export {};"})
    body = json.dumps({"signals": NO_SIGNALS, "mode": mode})
    proc = run_cli("--tree-file", str(_tree_file(tmp_path, LISTING)), "--entry-dir", str(folder), stdin=body)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["scope_type"] == "full-library"


@pytest.mark.parametrize(
    "mode,expected",
    [
        pytest.param("interactive", "full-library", id="interactive"),
        pytest.param("headless", "component-library", id="headless"),
    ],
)
def test_registry_file_missing_under_entry_dir(tmp_path, mode, expected):
    """A registry file the fetch missed: interactive does not count it, headless counts it by presence."""
    body = json.dumps({"signals": NO_SIGNALS, "mode": mode})
    proc = run_cli("--tree-file", str(_tree_file(tmp_path, LISTING)), "--entry-dir", str(tmp_path / "absent"),
                   stdin=body)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["scope_type"] == expected
    if expected == "component-library":
        assert out["signals"]["contents_inspected"] is False


def test_registry_contents_given_twice_dies(tmp_path):
    body = json.dumps({"signals": NO_SIGNALS, "entry_files": []})
    proc = run_cli("--tree-file", str(_tree_file(tmp_path, LISTING)), "--entry-dir", str(tmp_path), stdin=body)
    assert proc.returncode == 2
    assert "pass the registry contents once" in proc.stderr


# --------------------------------------------------------------------------
# --extract-file: the export count read from the extractor's output (gate run 2
# determinism-1), so no caller counts the exports by hand
# --------------------------------------------------------------------------


def _extract_file(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "extract.json"
    path.write_bytes(json.dumps(data).encode("utf-8"))
    return path


def _exports(*names: str) -> dict:
    return {"package_name": "demo", "exports": [{"name": n, "type": "function", "source_file": "src/a.ts"}
                                                for n in names]}


def test_extract_file_counts_the_distinct_export_names(tmp_path):
    data = _exports("a", "b", "a", "")
    data["exports"].append("not-an-object")
    body = json.dumps({"signals": signals(wants_narrow_api=True), "module_count": 1, "mode": "interactive"})
    proc = run_cli("--tree-file", str(_tree_file(tmp_path, "src/a.ts\n")),
                   "--extract-file", str(_extract_file(tmp_path, data)), stdin=body)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert (out["scope_type"], out["signals"]) == ("public-api", {"wants_narrow_api": True, "export_count": 2})


def test_extract_file_with_a_large_surface_gives_no_narrow_recommendation(tmp_path):
    body = json.dumps({"signals": signals(wants_narrow_api=True), "mode": "headless"})
    proc = run_cli("--tree-file", str(_tree_file(tmp_path, "src/a.ts\n")),
                   "--extract-file", str(_extract_file(tmp_path, _exports(*[f"e{i}" for i in range(9)]))), stdin=body)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert (out["scope_type"], out["signals"]["export_count"]) == ("full-library", 9)


def test_export_count_given_twice_dies(tmp_path):
    body = json.dumps({"signals": NO_SIGNALS, "export_count": 3})
    proc = run_cli("--tree-file", str(_tree_file(tmp_path, "src/a.ts\n")),
                   "--extract-file", str(_extract_file(tmp_path, _exports("a"))), stdin=body)
    assert proc.returncode == 2
    assert "pass the export count once" in proc.stderr


@pytest.mark.parametrize(
    "content,message",
    [
        pytest.param(None, "cannot read --extract-file", id="missing"),
        pytest.param(b"{not json", "is not valid JSON", id="invalid-json"),
        pytest.param(b'{"package_name": "demo"}', "holds no `exports` list", id="no-exports"),
        pytest.param(b"[]", "holds no `exports` list", id="a-list"),
    ],
)
def test_unusable_extract_file_dies(tmp_path, content, message):
    extract = tmp_path / "extract.json"
    if content is not None:
        extract.write_bytes(content)
    proc = run_cli("--tree-file", str(_tree_file(tmp_path, "src/a.ts\n")), "--extract-file", str(extract),
                   stdin=json.dumps({"signals": NO_SIGNALS}))
    assert proc.returncode == 2
    assert message in proc.stderr


# --------------------------------------------------------------------------
# CLI wiring
# --------------------------------------------------------------------------


def test_cli_stdin_payload_round_trip():
    body = {"signals": signals(wants_wiring_pattern=True), "tree": [], "mode": "headless"}
    proc = run_cli(stdin=json.dumps(body))
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["scope_type"] == "reference-app"


def test_cli_json_arg():
    body = {"source_type": "docs-only", "tree": [], "mode": "headless"}
    proc = run_cli("--json", json.dumps(body))
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["scope_type"] == "docs-only"


def test_cli_empty_stdin_dies_with_2():
    proc = run_cli(stdin="")
    assert proc.returncode == 2
    assert "empty input" in proc.stderr


def test_cli_invalid_json_dies_with_2():
    proc = run_cli(stdin="{not valid")
    assert proc.returncode == 2
    assert "invalid JSON" in proc.stderr


def test_cli_intent_payload_dies_with_2():
    body = {"intent": "Document the Kickstarter-style campaign SDK", "tree": [], "mode": "headless"}
    proc = run_cli(stdin=json.dumps(body))
    assert proc.returncode == 2
    assert "intent is free text" in proc.stderr


# --------------------------------------------------------------------------
# The call scope-definition.md documents works
# --------------------------------------------------------------------------

HEREDOC_RE = re.compile(r"<<'(?P<tag>[A-Z_]+)'\n(?P<body>.*?)\n(?P=tag)\n", re.DOTALL)


def _fill(body: str) -> str:
    """The documented payload with its placeholders filled in."""
    body = re.sub(r'"<[^"<>]*>"', '"x"', body)  # "<a name>" -> a string
    body = re.sub(r"\[<[^<>]*>\]", "[]", body)  # [<module names ...>] -> a list
    body = re.sub(r"<true\|false>", "false", body)
    return re.sub(r"<[^<>]*>", "3", body)  # <count from ...> -> a number


def _documented_block() -> str:
    """The bash block of scope-definition's recommender call."""
    text = SCOPE_DEFINITION.read_text(encoding="utf-8")
    blocks = [b for b in re.findall(r"```bash\n(.*?)```", text, re.DOTALL) if "{recommendScopeTypeHelper}" in b]
    assert len(blocks) == 1, "scope-definition.md must call {recommendScopeTypeHelper} in one bash block"
    return blocks[0]


def _documented_payload() -> dict:
    """The heredoc payload of scope-definition's recommender call, placeholders filled in."""
    block = _documented_block()
    calls = [m for m in HEREDOC_RE.finditer(block)
             if "{recommendScopeTypeHelper}" in block[block.rfind("\n", 0, m.start()) + 1:m.start()]]
    assert len(calls) == 1, "the block must pass the payload to {recommendScopeTypeHelper} in a heredoc"
    return json.loads(_fill(calls[0].group("body")))


def test_documented_payload_is_accepted():
    body = _documented_payload()
    assert set(body) <= mod.PAYLOAD_KEYS
    assert tuple(body["signals"]) == mod.SIGNAL_KEYS
    assert not set(body) & set(mod.FREE_TEXT_KEYS)
    assert not {"tree", "entry_files"} & set(body)  # the script reads both itself
    result = mod.recommend({**body, "tree": []})
    assert result["scope_type"] in VALID_SCOPE_TYPES


def test_documented_calls_pass_the_tree_and_registry_files_by_file_and_no_free_text():
    text = SCOPE_DEFINITION.read_text(encoding="utf-8")
    calls = re.findall(r"\{recommendScopeTypeHelper\} (--[^\n`]*)", text)
    source_calls = [call for call in calls if '"docs-only"' not in call]
    docs_only_calls = [call for call in calls if '"docs-only"' in call]
    assert source_calls and all(call.startswith("--tree-file ") for call in source_calls), calls
    assert any("--registry-files" in call for call in source_calls), calls
    assert any("--entry-dir" in call and "<<'" in call for call in source_calls), calls
    assert '"intent"' not in text
    for call in docs_only_calls:  # the headless docs-only call needs no tree or signals
        body = json.loads(re.fullmatch(r"--json '(\{.*\})'", call.strip()).group(1))
        assert mod.recommend(body)["scope_type"] == "docs-only"


def _fetch_shim(tmp_path: Path, served: Path) -> str:
    """The command that stands in for `uv run {githubFetchHelper}`: skf-github-fetch.py itself, its raw read
    served from `served` (o/r at main, laid out like the repository) and no gh."""
    shim = tmp_path / "fetch-shim.py"
    fetch = REPO / "src" / "shared" / "scripts" / "skf-github-fetch.py"
    shim.write_bytes((
        "import importlib.util, sys\nfrom pathlib import Path\n"
        f"spec = importlib.util.spec_from_file_location('fetch', {str(fetch)!r})\n"
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


def _run_documented_block(tmp_path: Path, listing: str) -> subprocess.CompletedProcess:
    """Run the GitHub block on step 2's staged listing and exports, the fetch serving a registry file."""
    block = _documented_block()
    heredoc = HEREDOC_RE.search(block)
    block = block[:heredoc.start("body")] + _fill(heredoc.group("body")) + block[heredoc.end("body"):]
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "tree.json").write_bytes(listing.encode("utf-8"))
    (run_dir / "extract.json").write_bytes(json.dumps(
        {"exports": [{"name": n, "type": "function", "source_file": "src/index.ts"} for n in "abc"]}).encode("utf-8"))
    served = _entry_dir(tmp_path, {REGISTRY: "export const registry: Component[] = [];\n"})
    block = block.replace("uv run {recommendScopeTypeHelper}", f'"{sys.executable}" "{SCRIPT_PATH}"')
    block = block.replace("uv run {githubFetchHelper}", _fetch_shim(tmp_path, served))
    block = block.replace("{run_dir}", run_dir.as_posix())
    block = block.replace("{owner}/{repo}", "o/r").replace("{analysis_ref}", "main")
    assert "{recommendScopeTypeHelper}" not in block and "{githubProbeHelper}" not in block
    assert not re.findall(r"\{[A-Za-z_]+\}", block), "every placeholder of the block is filled"
    return subprocess.run([BASH, "-c", block], capture_output=True, text=True, encoding="utf-8",
                          timeout=60, check=False)


def test_documented_block_reads_the_staged_listing_and_lists_nothing_itself():
    """Step 2 staged the file list in the run folder: the block reads it there and never lists the repository again."""
    block = _documented_block()
    assert "{githubProbeHelper}" not in block and "mktemp" not in block and "gh api" not in block
    assert block.count('--tree-file "{run_dir}/tree.json"') == 3
    assert '--entry-dir "{run_dir}/files" --extract-file "{run_dir}/extract.json"' in block, "step 2 always wrote it"
    assert '"export_count"' not in block, "step 3 never types the export count"
    text = SCOPE_DEFINITION.read_text(encoding="utf-8")
    assert "githubProbeProbeOrder" not in text
    [local] = [line for line in text.splitlines() if line.startswith("- **A local source, or step 2's clone.**")]
    assert '--entry-dir "{source_path}"' in local and "{run_dir}/clone" in local


@pytest.mark.skipif(not POSIX_BASH, reason="runs the documented block in a POSIX bash")
def test_documented_block_reads_the_fetched_registry_file(tmp_path):
    listing = json.dumps({"status": "ok", "repo": "o/r", "ref": "main", "tree": ["README.md", REGISTRY]})
    proc = _run_documented_block(tmp_path, listing)
    assert proc.returncode == 0, proc.stderr
    fetched, out = (json.loads(line) for line in proc.stdout.strip().splitlines())
    assert (fetched["status"], fetched["fetched"]) == ("ok", [REGISTRY])
    assert out["scope_type"] == "component-library"
    assert out["signals"]["registry_path"] == REGISTRY
    assert out["signals"]["contents_inspected"] is True
    # the registry file was fetched into the run folder, laid out like the repository
    assert (tmp_path / "run" / "files").joinpath(*REGISTRY.split("/")).is_file()


@pytest.mark.skipif(not POSIX_BASH, reason="runs the documented block in a POSIX bash")
def test_documented_block_exits_with_the_scripts_status(tmp_path):
    """A listing the script refuses: the call exits 2 with the listing's message, as the failed-call bullet says."""
    listing = json.dumps({"status": "unavailable", "cause": "unreachable", "tree": [],
                          "message": "Could not reach GitHub to read o/r (timeout); try again later."})
    proc = _run_documented_block(tmp_path, listing)
    assert proc.returncode == 2
    assert "Could not reach GitHub" in proc.stderr
    assert proc.stdout == ""


@pytest.mark.skipif(not POSIX_BASH or GIT is None, reason="runs the documented git listing in a POSIX bash")
def test_documented_local_listing_keeps_a_non_ascii_path(tmp_path):
    """git quotes a non-ASCII path unless core.quotePath is off; step 2's listing must name the file as it is."""
    text = ANALYZE_TARGET.read_text(encoding="utf-8")
    [command] = [line.strip() for line in text.splitlines() if line.strip().startswith('git -C "{source_path}"')]
    registry = "src/ui-ü/registry.ts"
    repo = _entry_dir(tmp_path, {registry: "export const registry: Component[] = [];\n"})
    subprocess.run([GIT, "init", "-q", str(repo)], check=True, capture_output=True)
    subprocess.run([GIT, "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    subprocess.run([BASH, "-c", command.replace("{source_path}", str(repo)).replace("{run_dir}", str(run_dir))],
                   check=True, capture_output=True)
    body = json.dumps({"signals": NO_SIGNALS, "mode": "interactive"})
    proc = run_cli("--tree-file", str(run_dir / "tree.json"), "--entry-dir", str(repo), stdin=body)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["scope_type"] == "component-library"
    assert out["signals"]["registry_path"] == registry


@pytest.mark.parametrize(
    "phrase",
    [
        pytest.param("not just the parser", id="negated-subset"),
        pytest.param("Kickstarter-style", id="starter-substring"),
        pytest.param("not a demo app or starter template", id="negated-demo-app"),
    ],
)
def test_classification_rule_names_the_issue_intents(phrase):
    """Section 2c tells the model how to classify the intents the keyword matcher misread."""
    text = SCOPE_DEFINITION.read_text(encoding="utf-8")
    section = text[text.index("**Classify the intent into signals.**"):text.index("**Run the recommender")]
    assert phrase in section
    for key in mod.SIGNAL_KEYS:
        assert f"`{key}`" in section
