#!/usr/bin/env python3
"""Tests for skf-detect-language.py.

Pure-function rule-walk tests against an inline file tree, plus a few
subprocess cases to verify CLI wiring (stdin/argparse/exit-code).
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "shared"
    / "scripts"
    / "skf-detect-language.py"
)

spec = importlib.util.spec_from_file_location("skf_detect_language", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def assert_result_shape(out: dict) -> None:
    assert set(out.keys()) >= {
        "language",
        "confidence",
        "detection_source",
        "fallback_to_extension_frequency",
    }, out
    assert out["confidence"] in {"high", "medium", "low"}
    assert isinstance(out["detection_source"], str) and out["detection_source"]
    assert isinstance(out["fallback_to_extension_frequency"], bool)
    assert isinstance(out["source_language"], str) and out["source_language"], out
    assert "detected_languages" in out, out
    assert isinstance(out["detected_languages"], list)
    assert all(isinstance(x, str) for x in out["detected_languages"])
    # No duplicates — the accumulator dedups in priority order.
    assert len(out["detected_languages"]) == len(set(out["detected_languages"]))


# --------------------------------------------------------------------------
# Rule 1 — package.json + tsconfig.json disambiguation
# --------------------------------------------------------------------------


def test_package_json_only_returns_javascript_high():
    result = mod.detect({"tree": ["package.json", "src/index.js"]})
    assert_result_shape(result)
    assert result["language"] == "javascript"
    assert result["confidence"] == "high"
    assert result["fallback_to_extension_frequency"] is False


def test_package_json_with_tsconfig_returns_typescript_high():
    result = mod.detect({"tree": ["package.json", "tsconfig.json", "src/index.ts"]})
    assert result["language"] == "typescript"
    assert result["confidence"] == "high"
    assert "tsconfig.json" in result["detection_source"]


def test_package_json_in_subdir_still_matches():
    result = mod.detect({"tree": ["packages/foo/package.json", "packages/foo/src/index.js"]})
    assert result["language"] == "javascript"


# --------------------------------------------------------------------------
# Rule 0 — workspace_signal precedence
# --------------------------------------------------------------------------


def test_cargo_workspace_signal_wins_over_nested_package_json_tsconfig():
    """The reported bug: a Rust cargo-workspace root with a docs/ TS site must detect rust, not typescript."""
    tree = [
        "Cargo.toml",
        "crates/core/src/lib.rs",
        "docs/package.json",
        "docs/tsconfig.json",
        "docs/pages/index.tsx",
    ]
    result = mod.detect({"tree": tree, "workspace_signal": "cargo-workspace"})
    assert_result_shape(result)
    assert result["language"] == "rust"
    assert result["confidence"] == "high"
    assert result["fallback_to_extension_frequency"] is False
    assert "cargo-workspace" in result["detection_source"]


def test_python_multi_package_signal_returns_python():
    tree = ["packages/a/pyproject.toml", "docs/package.json", "docs/tsconfig.json"]
    result = mod.detect({"tree": tree, "workspace_signal": "python-multi-package"})
    assert result["language"] == "python"
    assert result["confidence"] == "high"


def test_npm_workspace_signal_falls_through_to_package_json_rule():
    """JS-family workspace kinds carry no override; a root package.json+tsconfig still resolves typescript."""
    tree = ["package.json", "tsconfig.json", "packages/a/src/index.ts"]
    result = mod.detect({"tree": tree, "workspace_signal": "npm-workspaces"})
    assert result["language"] == "typescript"
    assert result["confidence"] == "high"


def test_unknown_or_null_workspace_signal_is_ignored():
    """generic-folders / unexpected values fall through to the normal rule walk."""
    tree = ["package.json", "src/index.js"]
    assert mod.detect({"tree": tree, "workspace_signal": "generic-folders"})["language"] == "javascript"
    assert mod.detect({"tree": tree, "workspace_signal": None})["language"] == "javascript"


def test_no_workspace_signal_a_docs_package_json_does_not_decide():
    """Absent workspace_signal: the root Cargo.toml decides, not the docs/ site's
    package.json (rule 1 used to fire on it from any depth and give javascript)."""
    result = mod.detect({"tree": ["docs/package.json", "Cargo.toml", "src/lib.rs"]})
    assert (result["language"], result["confidence"]) == ("rust", "high")
    assert result["detected_languages"] == ["rust", "javascript"]


# --------------------------------------------------------------------------
# Rules 2-6 — single-basename manifests
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "manifest,expected_lang",
    [
        ("Cargo.toml", "rust"),
        ("pyproject.toml", "python"),
        ("setup.py", "python"),
        ("setup.cfg", "python"),
        ("go.mod", "go"),
        ("pom.xml", "java"),
        ("build.gradle.kts", "kotlin"),
        ("Package.swift", "swift"),
        ("Gemfile", "ruby"),
    ],
)
def test_manifest_rules_high_confidence(manifest, expected_lang):
    tree = [manifest, "src/main.unknown"]
    result = mod.detect({"tree": tree})
    assert result["language"] == expected_lang
    assert result["confidence"] == "high"
    assert result["fallback_to_extension_frequency"] is False
    assert manifest in result["detection_source"]


# --------------------------------------------------------------------------
# Rule 7 — build.gradle (Groovy) Java/Kotlin disambiguation
# --------------------------------------------------------------------------


def test_build_gradle_with_kotlin_path_returns_kotlin_medium():
    result = mod.detect(
        {"tree": ["build.gradle", "src/main/kotlin/com/example/App.kt"]}
    )
    assert result["language"] == "kotlin"
    assert result["confidence"] == "medium"
    assert "src/main/kotlin/" in result["detection_source"]


def test_build_gradle_without_kotlin_path_defaults_to_java_medium():
    result = mod.detect(
        {"tree": ["build.gradle", "src/main/java/com/example/App.java"]}
    )
    assert result["language"] == "java"
    assert result["confidence"] == "medium"
    assert "defaulting to java" in result["detection_source"]


def test_build_gradle_kts_takes_precedence_over_groovy_when_both_present():
    """Kotlin .kts manifest hits the basename loop first — even with a sibling Groovy build.gradle."""
    result = mod.detect(
        {"tree": ["build.gradle", "build.gradle.kts", "src/main/kotlin/A.kt"]}
    )
    assert result["language"] == "kotlin"
    assert result["confidence"] == "high"


# --------------------------------------------------------------------------
# Rule 8 — csproj / sln
# --------------------------------------------------------------------------


def test_csproj_returns_csharp():
    result = mod.detect({"tree": ["MyApp.csproj", "Program.cs"]})
    assert result["language"] == "csharp"
    assert result["confidence"] == "high"


def test_sln_returns_csharp():
    result = mod.detect({"tree": ["MyApp.sln", "src/Program.cs"]})
    assert result["language"] == "csharp"


# --------------------------------------------------------------------------
# Rule 10 — extension-frequency fallback
# --------------------------------------------------------------------------


def test_dominant_extension_returns_medium_confidence():
    tree = ["a.swift", "b.swift", "c.swift", "README.md", "LICENSE"]
    result = mod.detect({"tree": tree})
    assert result["language"] == "swift"
    assert result["confidence"] == "medium"
    assert result["fallback_to_extension_frequency"] is True
    assert "extension frequency" in result["detection_source"]


def test_no_clear_winner_returns_low_confidence():
    tree = ["a.py", "b.py", "c.js", "d.js", "e.rb"]  # 2/2/1, top is 40% (below 50%)
    result = mod.detect({"tree": tree})
    assert result["confidence"] == "low"
    assert result["fallback_to_extension_frequency"] is True


def test_no_recognized_source_extensions_returns_unknown():
    tree = ["README.md", "LICENSE", "Dockerfile", "data.json"]
    result = mod.detect({"tree": tree})
    assert result["language"] == "unknown"
    assert result["confidence"] == "low"
    assert result["fallback_to_extension_frequency"] is True


def test_php_via_extension_frequency():
    tree = ["index.php", "lib.php", "config.php", "README.md"]
    result = mod.detect({"tree": tree})
    assert result["language"] == "php"


# --------------------------------------------------------------------------
# Rule precedence
# --------------------------------------------------------------------------


def test_package_json_takes_precedence_over_dominant_python_extensions():
    """Manifest rule 1 fires before extension fallback."""
    tree = ["package.json", "main.py", "lib.py", "test.py"]
    result = mod.detect({"tree": tree})
    assert result["language"] == "javascript"
    assert result["confidence"] == "high"
    assert result["fallback_to_extension_frequency"] is False


def test_cargo_toml_takes_precedence_over_python_files():
    tree = ["Cargo.toml", "scripts/build.py", "scripts/release.py"]
    result = mod.detect({"tree": tree})
    assert result["language"] == "rust"


def test_pom_xml_takes_precedence_over_build_gradle():
    """pom.xml fires in the manifest loop (java, high); build.gradle is post-loop and never reached."""
    result = mod.detect(
        {"tree": ["pom.xml", "build.gradle", "src/main/java/com/example/App.java"]}
    )
    assert result["language"] == "java"
    assert result["confidence"] == "high"
    assert result["fallback_to_extension_frequency"] is False


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def test_missing_tree_dies_with_2():
    with pytest.raises(SystemExit) as exc_info:
        mod.detect({})
    assert exc_info.value.code == 2


def test_empty_tree_dies_with_2():
    with pytest.raises(SystemExit) as exc_info:
        mod.detect({"tree": []})
    assert exc_info.value.code == 2


def test_tree_not_a_list_dies():
    with pytest.raises(SystemExit) as exc_info:
        mod.detect({"tree": "package.json"})
    assert exc_info.value.code == 2


# --------------------------------------------------------------------------
# CLI wiring
# --------------------------------------------------------------------------


def test_cli_stdin_payload_round_trip():
    payload = {"tree": ["Cargo.toml", "src/lib.rs"]}
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["language"] == "rust"


def test_cli_json_arg():
    payload = {"tree": ["pyproject.toml"]}
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--json", json.dumps(payload)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["language"] == "python"


def test_cli_empty_stdin_dies_with_2():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        input="",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 2
    assert "empty input" in proc.stderr


def test_cli_invalid_json_dies_with_2():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        input="{not valid",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 2
    assert "invalid JSON" in proc.stderr


def test_cli_raw_utf8_stdin_survives_cp1252_stdio():
    # Issue #465, stdin half: raw UTF-8 bytes (emoji NOT ASCII-escaped) piped
    # in under a cp1252 console (PYTHONIOENCODING simulates it on any
    # platform). \U0001F60D encodes to a byte (0x8D) undefined in cp1252, so
    # without the sys.stdin reconfigure the read raises UnicodeDecodeError
    # and the process exits non-zero.
    payload = {"tree": ["Cargo.toml", "src/\U0001F60D.rs"]}
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        timeout=10,
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    out = json.loads(proc.stdout.decode("utf-8"))
    assert out["language"] == "rust"


# --------------------------------------------------------------------------
# detected_languages[] — full manifest match set for the multi-language gate
# --------------------------------------------------------------------------


def test_multi_manifest_reports_all_matches_in_priority_order():
    """package.json(+tsconfig) + pyproject.toml — the gate must see both, TS-first."""
    tree = [
        "package.json",
        "tsconfig.json",
        "src/index.ts",
        "bindings/pyproject.toml",
        "bindings/mod.py",
    ]
    result = mod.detect({"tree": tree})
    assert_result_shape(result)
    # Winner is unchanged — rule 1 fires first.
    assert result["language"] == "typescript"
    assert result["confidence"] == "high"
    # Full match set, priority order (package.json rule 1 before pyproject rule 3).
    assert result["detected_languages"] == ["typescript", "python"]
    assert len(result["detected_languages"]) > 1  # the multi-language gate can fire
    assert result["detected_languages"][0] == result["language"]


def test_single_manifest_reports_one_language_and_preserves_envelope():
    """Only go.mod — detected_languages==['go'] and the legacy envelope is verbatim."""
    tree = ["go.mod", "main.go", "internal/util.go"]
    result = mod.detect({"tree": tree})
    assert result["detected_languages"] == ["go"]
    # Legacy single-winner fields preserved exactly (no-regression for delegating siblings).
    assert result["language"] == "go"
    assert result["confidence"] == "high"
    assert result["detection_source"] == "go.mod present"
    assert result["fallback_to_extension_frequency"] is False
    assert result["detected_languages"][0] == result["language"]


def test_multi_manifest_three_ecosystems_in_priority_order():
    """package.json (no tsconfig) + Cargo.toml + go.mod — javascript, then rust, then go."""
    tree = ["package.json", "Cargo.toml", "go.mod", "src/lib.rs"]
    result = mod.detect({"tree": tree})
    assert result["language"] == "javascript"  # winner unchanged (rule 1 first)
    assert result["detected_languages"] == ["javascript", "rust", "go"]


def test_dedup_of_same_language_manifests():
    """pyproject.toml + setup.cfg both map to python — python appears once."""
    tree = ["pyproject.toml", "setup.cfg", "pkg/__init__.py"]
    result = mod.detect({"tree": tree})
    assert result["detected_languages"] == ["python"]
    assert result["language"] == "python"


def test_extension_fallback_reports_single_element():
    """Rule 10 best guess — detected_languages stays within one element."""
    tree = ["a.swift", "b.swift", "c.swift", "README.md", "LICENSE"]
    result = mod.detect({"tree": tree})
    assert_result_shape(result)
    assert result["fallback_to_extension_frequency"] is True
    assert result["language"] == "swift"
    assert result["detected_languages"] == ["swift"]
    assert len(result["detected_languages"]) <= 1


def test_unknown_language_reports_empty_detected_languages():
    """No recognized manifests or source extensions — empty list, len <= 1, no spurious gate."""
    tree = ["README.md", "LICENSE", "Dockerfile", "data.json"]
    result = mod.detect({"tree": tree})
    assert result["language"] == "unknown"
    assert result["detected_languages"] == []
    assert len(result["detected_languages"]) <= 1


def test_workspace_signal_override_reports_single_decisive_language():
    """Rule 0 is authoritative — a cargo-workspace with a nested TS docs site is [rust] only."""
    tree = [
        "Cargo.toml",
        "crates/core/src/lib.rs",
        "docs/package.json",
        "docs/tsconfig.json",
        "docs/pages/index.tsx",
    ]
    result = mod.detect({"tree": tree, "workspace_signal": "cargo-workspace"})
    assert result["language"] == "rust"
    # Decisive: the nested package.json+tsconfig must NOT surface a multi-language gate.
    assert result["detected_languages"] == ["rust"]
    assert len(result["detected_languages"]) <= 1


def test_cli_stdin_emits_detected_languages():
    """detected_languages round-trips through the CLI/JSON boundary."""
    payload = {"tree": ["package.json", "tsconfig.json", "Cargo.toml", "src/lib.rs"]}
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["language"] == "typescript"
    assert out["detected_languages"] == ["typescript", "rust"]


# --------------------------------------------------------------------------
# --tree-file (issue #592): the tree comes from a staged listing, whole
# --------------------------------------------------------------------------

RECOMMENDER_PATH = SCRIPT_PATH.parent / "skf-recommend-scope-type.py"
TS_TREE = ["package.json", "tsconfig.json", "src/index.ts"]


def _load(path: Path, name: str):
    loaded = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(loaded)
    loaded.loader.exec_module(module)
    return module


def _tree_file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "tree.json"
    path.write_bytes(text.encode("utf-8"))
    return path


def run_cli(*args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        input=stdin.encode("utf-8"),
        capture_output=True,
        timeout=60,
    )


def _out(proc: subprocess.CompletedProcess) -> dict:
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    return json.loads(proc.stdout.decode("utf-8"))


# Every listing skf-recommend-scope-type.py's --tree-file reads.
LISTINGS = [
    pytest.param(
        json.dumps({"status": "ok", "repo": "o/r", "ref": "HEAD", "tree": TS_TREE, "count": 3, "truncated": False}),
        id="github-probe-output",
    ),
    pytest.param(
        json.dumps({"sha": "abc", "truncated": False, "tree": [
            {"path": "src", "type": "tree"},
            *({"path": p, "type": "blob", "mode": "100644"} for p in TS_TREE),
        ]}),
        id="git-trees-response",
    ),
    pytest.param(json.dumps({"tree": TS_TREE}), id="gh-jq-object"),
    pytest.param(json.dumps(TS_TREE), id="json-list"),
    pytest.param("".join(f"{p}\n" for p in TS_TREE), id="git-ls-files-lines"),
    pytest.param("".join(f"./{p}\r\n" for p in TS_TREE) + "\r\n", id="find-dot-lines-crlf"),
    pytest.param("[locale]/page.tsx\n{slug}/view.ts\n" + "\n".join(TS_TREE), id="lines-opening-with-brackets"),
    pytest.param("\ufeff" + json.dumps({"tree": TS_TREE}), id="json-with-bom"),
]


@pytest.mark.parametrize("listing", LISTINGS)
def test_tree_file_formats_reach_the_rule_walk(tmp_path, listing):
    out = _out(run_cli("--tree-file", str(_tree_file(tmp_path, listing))))
    assert (out["language"], out["detection_source"]) == ("typescript", "package.json + tsconfig.json present")


@pytest.mark.parametrize("listing", LISTINGS)
def test_the_listing_reader_reads_what_the_recommender_reads(tmp_path, listing):
    """skf-recommend-scope-type.py's --tree-file and this reader take the
    same listings to the same paths."""
    recommender = _load(RECOMMENDER_PATH, "skf_recommend_scope_type_for_parity")
    text = _tree_file(tmp_path, listing).read_text(encoding="utf-8-sig")
    assert mod.parse_tree_listing(text, "in t")[0] == recommender._parse_tree_listing(text, "in t")


@pytest.mark.parametrize(
    "listing",
    [
        pytest.param("\ufeff" + json.dumps({"tree": TS_TREE}), id="json"),
        pytest.param("\ufeff" + "".join(f"{p}\r\n" for p in TS_TREE), id="lines"),
    ],
)
def test_a_byte_order_mark_on_stdin_is_dropped(listing):
    """Windows PowerShell 5.1 writes a byte order mark into a pipe: the
    listing read through `--tree-file -` is the same listing."""
    out = _out(run_cli("--tree-file", "-", stdin=listing))
    assert (out["language"], out["detection_source"]) == ("typescript", "package.json + tsconfig.json present")
    assert mod.parse_tree_listing(listing, "on stdin") == (TS_TREE, False)


def test_the_listing_reader_reports_a_cut_short_github_tree():
    paths, truncated = mod.parse_tree_listing(json.dumps({"status": "ok", "tree": ["a.py"], "truncated": True}), "x")
    assert (paths, truncated) == (["a.py"], True)
    assert mod.parse_tree_listing(json.dumps({"tree": [{"path": "a.py", "type": "blob"}], "truncated": True}),
                                  "x") == (["a.py"], True)
    # a line listing cannot say it was cut short
    assert mod.parse_tree_listing("a.py\nb.py\n", "x") == (["a.py", "b.py"], False)


def test_tree_file_dash_reads_the_listing_from_stdin():
    listing = "\n".join(["Cargo.toml", "docs/package.json", "docs/tsconfig.json"])
    out = _out(run_cli("--tree-file", "-", "--json", json.dumps({"workspace_signal": "cargo-workspace"}),
                       stdin=listing))
    assert (out["language"], out["detected_languages"]) == ("rust", ["rust"])


def test_tree_file_takes_the_signal_from_a_flag_never_from_stdin(tmp_path):
    """With --tree-file, stdin is never read for the payload: a
    workspace_signal piped in changes nothing (the help says so), while
    --workspace-signal or --json decides, and passing it twice is refused."""
    # A root package.json beside a nested crate: typescript, unless the
    # workspace signal says the repository is a cargo workspace.
    tree_file = _tree_file(tmp_path, "package.json\ntsconfig.json\ncrates/core/Cargo.toml\n")
    signal = json.dumps({"workspace_signal": "cargo-workspace"})
    assert _out(run_cli("--tree-file", str(tree_file), stdin=signal))["language"] == "typescript"
    assert _out(run_cli("--tree-file", str(tree_file), "--workspace-signal", "cargo-workspace"))["language"] == "rust"
    assert _out(run_cli("--tree-file", str(tree_file), "--json", signal))["language"] == "rust"
    # a JS-family manifest_kind carries no override, as in the payload
    assert _out(run_cli("--tree-file", str(tree_file), "--workspace-signal", "npm-workspaces"))["language"] == "typescript"
    # A docs/ site no longer needs the signal: the root Cargo.toml decides.
    docs_site = _tree_file(tmp_path, "Cargo.toml\ndocs/package.json\ndocs/tsconfig.json\n")
    assert _out(run_cli("--tree-file", str(docs_site)))["language"] == "rust"
    assert _out(run_cli("--tree-file", str(docs_site), "--workspace-signal", "npm-workspaces"))["language"] == "rust"
    twice = run_cli("--tree-file", str(tree_file), "--workspace-signal", "cargo-workspace", "--json", signal)
    assert twice.returncode == 2
    assert "pass workspace_signal once" in twice.stderr.decode("utf-8")
    help_text = run_cli("--help").stdout.decode("utf-8")
    assert "stdin is not read" in " ".join(help_text.split())


def test_the_workspace_signal_flag_joins_a_stdin_payload():
    out = _out(run_cli("--workspace-signal", "python-multi-package",
                       stdin=json.dumps({"tree": ["pyproject.toml", "web/package.json"]})))
    assert (out["language"], out["detected_languages"]) == ("python", ["python"])


def test_a_tree_past_10000_files_is_read_whole(tmp_path):
    """A tree of more than 10,000 files reaches the rule walk whole: the
    manifests that decide are the last two paths, after 12,000 Python files
    that would win the extension count on their own."""
    paths = [f"pkg{i // 100}/mod{i}.py" for i in range(12000)] + ["package.json", "tsconfig.json"]
    probe = _tree_file(tmp_path, json.dumps({"status": "ok", "tree": paths, "count": len(paths), "truncated": False}))
    assert _out(run_cli("--tree-file", str(probe)))["language"] == "typescript"
    lines = tmp_path / "tree.txt"
    lines.write_bytes("".join(f"{p}\n" for p in paths).encode("utf-8"))
    assert _out(run_cli("--tree-file", str(lines)))["language"] == "typescript"
    # the same list cut at 10,000 paths misses them
    assert mod.detect({"tree": paths[:10000]})["language"] == "python"


def test_a_non_ascii_path_survives_a_cp1252_console(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--tree-file", "-"],
        input="Cargo.toml\nsrc/café.rs\n".encode("utf-8"),
        capture_output=True,
        timeout=60,
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert json.loads(proc.stdout.decode("utf-8"))["language"] == "rust"


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
        pytest.param("[]", "holds no file path", id="no-path"),
        pytest.param(json.dumps({"status": "ok", "repo": "o/r", "tree": [], "count": 0, "truncated": False}),
                     "holds no file path", id="probe-with-no-path"),
        pytest.param(json.dumps({"sha": "abc", "truncated": False, "tree": [{"path": "src", "type": "tree"}]}),
                     "holds no file path", id="git-trees-with-no-blob"),
        pytest.param("./\n./\n", "holds no file path", id="lines-with-no-path"),
    ],
)
def test_unusable_tree_file_dies_with_2(tmp_path, listing, message):
    proc = run_cli("--tree-file", str(_tree_file(tmp_path, listing)))
    assert proc.returncode == 2
    assert message in proc.stderr.decode("utf-8")
    assert proc.stdout == b""


def test_missing_tree_file_dies_with_2(tmp_path):
    proc = run_cli("--tree-file", str(tmp_path / "absent.json"))
    assert proc.returncode == 2
    assert "cannot read --tree-file" in proc.stderr.decode("utf-8")


def test_tree_given_twice_dies_with_2(tmp_path):
    proc = run_cli("--tree-file", str(_tree_file(tmp_path, "Cargo.toml\n")), "--json", json.dumps({"tree": ["go.mod"]}))
    assert proc.returncode == 2
    assert "pass the tree once" in proc.stderr.decode("utf-8")


def test_the_reader_raises_on_a_failed_listing():
    with pytest.raises(mod.TreeListingError, match="reports a failure"):
        mod.parse_tree_listing(json.dumps({"status": "unavailable", "message": "gone"}), "on stdin")


@pytest.mark.parametrize(
    "path,source",
    [
        pytest.param("src/app.TS", True, id="upper-case-extension"),
        pytest.param("lib/mod.py", True, id="python"),
        pytest.param("README.md", False, id="docs"),
        pytest.param("src/.py", False, id="hidden-name"),
        pytest.param("Makefile", False, id="no-extension"),
    ],
)
def test_is_source_file_follows_the_extension_rule(path, source):
    """skf-detect-workspaces.py's tree snapshot counts source files with it."""
    assert mod.is_source_file(path) is source


# --------------------------------------------------------------------------
# Which manifests decide: the manifests nearest the root, never a non-core
# folder's (the wave-3 re-check of skf-analyze-source, determinism-1)
# --------------------------------------------------------------------------


def test_a_root_pyproject_beats_a_docs_package_json():
    """A Python library whose docs site carries a package.json is python (it
    was javascript, high: rule 1 fired on a manifest at any depth)."""
    result = mod.detect({"tree": ["pyproject.toml", "docs/package.json", "src/pkg/core.py"]})
    assert_result_shape(result)
    assert (result["language"], result["confidence"]) == ("python", "high")
    assert result["detection_source"] == "pyproject.toml present"
    assert result["detected_languages"] == ["python", "javascript"]


def test_a_root_pyproject_beats_a_nested_rust_core():
    """pydantic: the root pyproject.toml decides over pydantic-core/Cargo.toml
    (it was rust, high), and rust stays in detected_languages."""
    tree = ["pydantic-core/Cargo.toml", "pydantic-core/pyproject.toml", "pyproject.toml", "pydantic/main.py"]
    result = mod.detect({"tree": tree})
    assert (result["language"], result["confidence"]) == ("python", "high")
    assert result["detected_languages"] == ["python", "rust"]


# python/cpython at the root: no manifest, so the shallowest one below
# decides, at medium confidence, and the language of its source files ends
# detected_languages.
CPYTHON_TREE = [
    "PCbuild/pcbuild.sln", "PCbuild/python.vcxproj",
    "Platforms/Android/testbed/build.gradle.kts",
    "Platforms/emscripten/browser_test/package.json", "Platforms/emscripten/browser_test/tsconfig.json",
    "Platforms/emscripten/browser_test/run_test.ts",
    "Doc/conf.py", "Tools/build/freeze.py", "configure", "README.rst",
    "Python/ceval.c", "Parser/parser.c", "Include/Python.h",
    *(f"Lib/mod{i}.py" for i in range(40)),
    *(f"Lib/test/test_mod{i}.py" for i in range(40)),
]


def test_a_cpython_shaped_tree_decides_below_the_root_at_medium_confidence():
    result = mod.detect({"tree": CPYTHON_TREE})
    assert_result_shape(result)
    assert result["confidence"] == "medium"
    assert result["language"] != "python"
    assert result["language"] == result["detected_languages"][0]
    assert "PCbuild/pcbuild.sln" in result["detection_source"]
    assert "no manifest at the tree's root" in result["detection_source"]
    assert result["source_language"] == "python"
    assert result["detected_languages"][-1] == "python"
    assert set(result["detected_languages"]) == {"csharp", "typescript", "kotlin", "python"}


def test_a_root_manifest_keeps_the_source_language_out_of_detected_languages():
    """The extension count joins detected_languages only when no manifest sits at the root."""
    result = mod.detect({"tree": ["package.json", "a.py", "b.py", "c.py"]})
    assert (result["language"], result["source_language"]) == ("javascript", "python")
    assert result["detected_languages"] == ["javascript"]


@pytest.mark.parametrize(
    "tree,language,detected",
    [
        pytest.param(["Cargo.toml", "examples/demo/package.json", "benchmarks/x/go.mod"], "rust",
                     ["rust", "javascript", "go"], id="examples-and-benches"),
        pytest.param(["go.mod", ".github/actions/setup/package.json", "main.go"], "go", ["go", "javascript"],
                     id="hidden-folder"),
        pytest.param(["pyproject.toml", "tests/fixtures/app/package.json", "website/package.json"], "python",
                     ["python", "javascript"], id="fixtures-and-website"),
        pytest.param(["setup.py", "Tools/node/package.json"], "python", ["python", "javascript"],
                     id="upper-case-tools"),
    ],
)
def test_a_non_core_folder_never_decides(tree, language, detected):
    result = mod.detect({"tree": tree})
    assert (result["language"], result["confidence"]) == (language, "high")
    assert result["detected_languages"] == detected


def test_the_shallowest_core_folder_decides_before_rule_order():
    """packages/a/package.json at depth 2 loses to crates/go.mod at depth 1,
    though rule 1 comes first in the table."""
    result = mod.detect({"tree": ["packages/a/package.json", "crates/go.mod", "README.md"]})
    assert (result["language"], result["confidence"]) == ("go", "medium")
    assert result["detected_languages"] == ["go", "javascript"]


def test_rule_order_decides_within_one_depth():
    result = mod.detect({"tree": ["x/Cargo.toml", "y/package.json", "y/tsconfig.json", "README.md"]})
    assert (result["language"], result["confidence"]) == ("typescript", "medium")
    assert result["detected_languages"] == ["typescript", "rust"]


def test_a_docs_tsconfig_does_not_turn_a_root_package_into_typescript():
    result = mod.detect({"tree": ["package.json", "index.js", "website/tsconfig.json", "website/package.json"]})
    assert (result["language"], result["confidence"]) == ("javascript", "high")
    assert result["detected_languages"] == ["javascript", "typescript"]


def test_a_unit_under_a_non_core_folder_reads_from_its_own_folder():
    """One unit's files (identify-units section 4) sit under its folder: that
    folder is the tree's root, so tools/cli's own package.json decides."""
    result = mod.detect({"tree": ["tools/cli/package.json", "tools/cli/bin/run.js", "tools/cli/lib/a.js"]})
    assert (result["language"], result["confidence"]) == ("javascript", "high")
    assert result["detected_languages"] == ["javascript"]


def test_only_non_core_manifests_still_decide():
    """No core manifest: every manifest takes part again, below the root at medium."""
    result = mod.detect({"tree": ["docs/package.json", "a.py", "b.py", "c.py"]})
    assert (result["language"], result["confidence"]) == ("javascript", "medium")
    assert result["detected_languages"] == ["javascript", "python"]


def test_a_typescript_unit_in_a_cargo_workspace_is_typescript_without_the_signal():
    """identify-units passes no --workspace-signal: rule 0 would answer rust
    for any unit of a cargo workspace."""
    tree = ["packages/node/package.json", "packages/node/tsconfig.json", "packages/node/index.ts"]
    assert mod.detect({"tree": tree})["detected_languages"] == ["typescript"]
    assert mod.detect({"tree": tree, "workspace_signal": "cargo-workspace"})["detected_languages"] == ["rust"]


@pytest.mark.parametrize(
    "tree",
    [
        pytest.param(["pyproject.toml", "docs/package.json"], id="docs"),
        pytest.param(CPYTHON_TREE, id="cpython"),
        pytest.param(["a/b/build.gradle", "a/b/src/main/kotlin/A.kt", "c/pom.xml"], id="gradle"),
        pytest.param(["x.sln", "src/package.json", "src/tsconfig.json"], id="suffix-at-root"),
    ],
)
def test_language_is_the_first_detected_language(tree):
    result = mod.detect({"tree": tree})
    assert result["language"] == result["detected_languages"][0]


def test_the_cli_reads_a_cpython_listing(tmp_path):
    out = _out(run_cli("--tree-file", str(_tree_file(tmp_path, "".join(f"{p}\n" for p in CPYTHON_TREE)))))
    assert (out["confidence"], out["source_language"], out["detected_languages"][-1]) == ("medium", "python", "python")


def test_the_non_core_folders_match_shape_detection():
    """The set is a copy of skf-shape-detect.py's (which loads this script, so
    this one cannot import it): both scripts must call the same folders non-core."""
    path = SCRIPT_PATH.parent / "skf-shape-detect.py"
    spec_shape = importlib.util.spec_from_file_location("skf_shape_detect_parity", path)
    shape = importlib.util.module_from_spec(spec_shape)
    spec_shape.loader.exec_module(shape)
    assert mod._NON_CORE_PATH_SEGMENTS == shape._NON_CORE_PATH_SEGMENTS
