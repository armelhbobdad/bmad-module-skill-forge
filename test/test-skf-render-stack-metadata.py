#!/usr/bin/env python3
"""Tests for src/shared/scripts/skf-render-stack-metadata.py.

The helper create-stack-skill runs for a stack's tiers and metadata.json
(detect-integrations section 3, generate-output section 6):
  - combine_pair_tier gives a pair the weaker of its two tiers, the same
    rule in code mode and compose mode, for the six cases of the old compose
    matrix and every pair with a T3 member
  - dominant_tier picks the largest bin, a tie going to the weaker tier,
    T1-low with no positive bin; a copy of skf-enumerate-stack-skills.py's
  - `metadata` counts each library once, so confidence_distribution sums to
    library_count, and takes the lowest source_authority (internal lowest, a
    library that records none counting as community)
  - `pair-tiers` and `metadata` read a file or stdin, stdin as UTF-8 even
    where the console's code page is cp1252; a malformed input exits 2 with
    one line on stderr and no JSON

test-skf-stack-step-rules.py runs the calls the step files make.
"""

from __future__ import annotations

import ast
import importlib.util
import itertools
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "src" / "shared" / "scripts"
SCRIPT = SCRIPTS / "skf-render-stack-metadata.py"
ENUMERATE = SCRIPTS / "skf-enumerate-stack-skills.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load(SCRIPT, "skf_render_stack_metadata")
enumerate_mod = _load(ENUMERATE, "skf_enumerate_stack_skills_for_stack_metadata")

MODES = ("code", "compose")

# The six cases of the compose matrix the one rule replaced, and the tier each
# gives: the weaker of the two. A T2 member lowers the pair like any other.
SIX_CASES = [
    ("T1", "T1", "T1"),
    ("T1", "T1-low", "T1-low"),
    ("T1-low", "T1-low", "T1-low"),
    ("T1", "T2", "T2"),
    ("T1-low", "T2", "T2"),
    ("T2", "T2", "T2"),
]


def run(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True, text=True,
    )


def stack(libraries, integrations=(), mode="compose") -> dict:
    return {
        "mode": mode,
        "libraries": [
            dict({"name": name, "confidence": tier}, **({"source_authority": auth} if auth else {}))
            for name, tier, auth in libraries
        ],
        "integrations": [{"a": a, "b": b} for a, b in integrations],
    }


# --------------------------------------------------------------------------
# combine_pair_tier
# --------------------------------------------------------------------------


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("a, b, tier", SIX_CASES, ids=[f"{a}+{b}" for a, b, _ in SIX_CASES])
def test_a_pair_takes_the_weaker_tier_in_both_modes(a, b, tier, mode):
    assert mod.combine_pair_tier(a, b, mode) == tier
    assert mod.combine_pair_tier(b, a, mode) == tier


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("other", ["T1", "T1-low", "T2", "T3"])
def test_a_t3_member_makes_the_pair_t3(other, mode):
    assert mod.combine_pair_tier(other, "T3", mode) == "T3"
    assert mod.combine_pair_tier("T3", other, mode) == "T3"


def test_both_modes_take_one_rule():
    for a, b in itertools.product(mod.TIERS, repeat=2):
        assert mod.combine_pair_tier(a, b, "code") == mod.combine_pair_tier(a, b, "compose")


def test_the_pair_tier_never_outranks_either_member():
    for a, b in itertools.product(mod.TIERS, repeat=2):
        tier = mod.combine_pair_tier(a, b, "code")
        assert tier in (a, b)
        assert mod.TIERS.index(tier) >= max(mod.TIERS.index(a), mod.TIERS.index(b))


def test_tokens_compare_case_insensitively():
    assert mod.combine_pair_tier("t1", "T1-LOW", "Compose") == "T1-low"


@pytest.mark.parametrize("a, b, mode", [
    ("T4", "T1", "code"),
    ("T1", None, "code"),
    ("Deep", "T1", "compose"),
    ("T1", "T1", "stack"),
    ("T1", "T1", None),
])
def test_an_unknown_tier_or_mode_is_an_input_error(a, b, mode):
    with pytest.raises(ValueError):
        mod.combine_pair_tier(a, b, mode)


# --------------------------------------------------------------------------
# dominant_tier
# --------------------------------------------------------------------------


@pytest.mark.parametrize("distribution, tier", [
    ({"t1": 3, "t1_low": 1, "t2": 0, "t3": 0}, "T1"),
    ({"t1": 1, "t1_low": 3, "t2": 0, "t3": 0}, "T1-low"),
    ({"t1": 0, "t1_low": 0, "t2": 2, "t3": 1}, "T2"),
    ({"t1": 0, "t1_low": 0, "t2": 0, "t3": 5}, "T3"),
])
def test_the_largest_bin_is_the_dominant_tier(distribution, tier):
    assert mod.dominant_tier(distribution) == tier


@pytest.mark.parametrize("distribution, tier", [
    ({"t1": 2, "t1_low": 2, "t2": 0, "t3": 0}, "T1-low"),
    ({"t1": 0, "t1_low": 2, "t2": 2, "t3": 0}, "T2"),
    ({"t1": 1, "t1_low": 0, "t2": 0, "t3": 1}, "T3"),
    ({"t1": 1, "t1_low": 1, "t2": 1, "t3": 0}, "T2"),
])
def test_a_tie_goes_to_the_weaker_tier(distribution, tier):
    assert mod.dominant_tier(distribution) == tier


@pytest.mark.parametrize("distribution", [None, {}, [], "T1", {"t1": 0, "t1_low": 0, "t2": 0, "t3": 0}],
                         ids=["none", "empty", "list", "string", "all-zero"])
def test_no_library_reads_t1_low(distribution):
    assert mod.dominant_tier(distribution) == "T1-low"


def _top_level_node(path: Path, name: str) -> str:
    """ast.dump of the top-level def or assignment named `name` (comments ignored)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.dump(node)
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.dump(node)
    raise AssertionError(f"{name} not found at the top level of {path.name}")


@pytest.mark.parametrize("name", ["_bin_count", "dominant_tier", "_DISTRIBUTION_BINS", "_NO_EVIDENCE_TIER"])
def test_the_dominant_tier_is_a_copy_of_the_enumerate_helper(name):
    """A constituent's evidence_tier and a stack's confidence_tier follow one rule."""
    assert _top_level_node(SCRIPT, name) == _top_level_node(ENUMERATE, name), (
        f"{name} in skf-render-stack-metadata.py differs from skf-enumerate-stack-skills.py; keep the copies identical")
    text = SCRIPT.read_text(encoding="utf-8")
    assert "Keep identical to _bin_count and dominant_tier in skf-enumerate-stack-skills.py" in text
    assert "test/test-skf-render-stack-metadata.py pins the copies" in text


def test_the_copies_agree_on_every_small_distribution():
    odd = [True, "9", -1, None, float("nan"), float("inf"), 2.5]
    for values in itertools.product([0, 1, 2, 3], repeat=4):
        distribution = dict(zip(("t1", "t1_low", "t2", "t3"), values))
        assert mod.dominant_tier(distribution) == enumerate_mod.dominant_tier(distribution), distribution
    for value in odd:
        distribution = {"t1": value, "t1_low": 1}
        assert mod.dominant_tier(distribution) == enumerate_mod.dominant_tier(distribution), distribution


# --------------------------------------------------------------------------
# metadata
# --------------------------------------------------------------------------


def _metadata(data: dict) -> dict:
    return mod.stack_metadata(*mod.parse_stack(data))


@pytest.mark.parametrize("tiers", [
    ["T1"],
    ["T1", "T1-low", "T2"],
    ["T3", "T3", "T1-low", "T1", "T2", "T2"],
    [],
], ids=["one", "three", "six", "none"])
def test_the_distribution_counts_each_library_once(tiers):
    """#528: the bins sum to library_count, whatever the stack holds."""
    out = _metadata(stack([(f"lib{i}", tier, None) for i, tier in enumerate(tiers)]))
    assert out["library_count"] == len(tiers)
    assert sum(out["confidence_distribution"].values()) == out["library_count"]
    assert list(out["confidence_distribution"]) == ["t1", "t1_low", "t2", "t3"]
    assert out["confidence_tier"] == mod.dominant_tier(out["confidence_distribution"])


def test_the_projection_keeps_the_order_given():
    data = stack(
        [("react", "T1", "community"), ("express", "T1-low", "official"), ("zod", "T2", None)],
        [("react", "express"), ("zod", "react")],
    )
    out = _metadata(data)
    assert out == {
        "mode": "compose",
        "library_count": 3,
        "integration_count": 2,
        "libraries": ["react", "express", "zod"],
        "integration_pairs": [["react", "express"], ["zod", "react"]],
        "confidence_distribution": {"t1": 1, "t1_low": 1, "t2": 1, "t3": 0},
        "confidence_tier": "T2",
        "source_authority": "community",
        "integrations": [
            {"a": "react", "b": "express", "tier": "T1-low"},
            {"a": "zod", "b": "react", "tier": "T2"},
        ],
    }


@pytest.mark.parametrize("authorities, expected", [
    (["community", "internal"], "internal"),
    (["internal", "community"], "internal"),
    (["official", "community"], "community"),
    (["official", "official"], "official"),
    (["official", "internal", "community"], "internal"),
    (["official", None], "community"),
    (["internal", None], "internal"),
    ([None, None], "community"),
], ids=["community-internal", "internal-community", "official-community", "official", "all-three",
        "official-unrecorded", "internal-unrecorded", "none-recorded"])
def test_source_authority_is_the_lowest(authorities, expected):
    """internal ranks lowest: a community and an internal library give internal.

    A library that records no authority counts as community, so a constituent
    without one never lifts a stack to official.
    """
    libraries = [(f"lib{i}", "T1", authority) for i, authority in enumerate(authorities)]
    assert _metadata(stack(libraries))["source_authority"] == expected


def test_a_stack_with_no_library_records_community():
    assert mod.lowest_authority([]) == "community"


def test_a_code_mode_stack_records_community():
    out = _metadata(stack([("react", "T1", None), ("express", "T1-low", None)], mode="code"))
    assert out["source_authority"] == "community"
    assert out["mode"] == "code"


def test_the_metadata_pairs_have_the_pair_tiers():
    data = stack([("a", "T1", None), ("b", "T3", None), ("c", "T1", None)], [("a", "b"), ("a", "c")], mode="code")
    mode, libraries, pairs = mod.parse_stack(data)
    assert _metadata(data)["integrations"] == mod.pair_tiers(mode, libraries, pairs) == [
        {"a": "a", "b": "b", "tier": "T3"},
        {"a": "a", "b": "c", "tier": "T1"},
    ]


def test_tokens_are_printed_in_their_canonical_spelling():
    out = _metadata({"mode": "CODE", "libraries": [
        {"name": "a", "confidence": "t1-low", "source_authority": "Internal"},
        {"name": "b", "confidence": " T1 "},
    ]})
    assert (out["mode"], out["confidence_tier"], out["source_authority"]) == ("code", "T1-low", "internal")


@pytest.mark.parametrize("data, needle", [
    ([], "must be a JSON object"),
    ({"libraries": []}, "mode"),
    ({"mode": "compose"}, "`libraries`"),
    ({"mode": "compose", "libraries": ["react"]}, "libraries[0] must be an object"),
    ({"mode": "compose", "libraries": [{"name": "", "confidence": "T1"}]}, "libraries[0].name"),
    ({"mode": "compose", "libraries": [{"name": "a", "confidence": "Deep"}]}, "libraries[0].confidence"),
    ({"mode": "compose", "libraries": [{"name": "a", "confidence": "T1", "source_authority": "vendor"}]},
     "libraries[0].source_authority"),
    ({"mode": "compose", "libraries": [{"name": "a", "confidence": "T1"}, {"name": "a", "confidence": "T2"}]},
     "listed twice"),
    ({"mode": "compose", "libraries": [{"name": "a", "confidence": "T1"}], "integrations": {"a": "a"}},
     "`integrations`"),
    ({"mode": "compose", "libraries": [{"name": "a", "confidence": "T1"}], "integrations": [["a", "b"]]},
     "integrations[0] must be an object"),
    ({"mode": "compose", "libraries": [{"name": "a", "confidence": "T1"}], "integrations": [{"a": "a", "b": "z"}]},
     "integrations[0].b 'z' is not one of the libraries"),
    ({"mode": "compose", "libraries": [{"name": "a", "confidence": "T1"}], "integrations": [{"a": ["a"], "b": "a"}]},
     "integrations[0].a ['a'] is not one of the libraries"),
    ({"mode": "compose", "libraries": [{"name": "a", "confidence": "T1"}], "integrations": [{"a": "a", "b": "a"}]},
     "with itself"),
    ({"mode": "compose", "libraries": [{"name": "a", "confidence": "T1"}, {"name": "b", "confidence": "T1"}],
      "integrations": [{"a": "a", "b": "b"}, {"a": "b", "b": "a"}]}, "listed twice"),
], ids=["not-an-object", "no-mode", "no-libraries", "library-not-an-object", "empty-name", "forge-tier",
        "unknown-authority", "duplicate-library", "integrations-not-a-list", "pair-not-an-object",
        "unknown-pair-member", "unhashable-pair-member", "self-pair", "duplicate-pair"])
def test_a_malformed_input_is_refused(data, needle):
    with pytest.raises(ValueError) as caught:
        mod.parse_stack(data)
    assert needle in str(caught.value)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_pair_tiers_reads_stdin():
    data = stack([("react", "T1", None), ("express", "T2", None)], [("react", "express")])
    result = run("pair-tiers", "--input", "-", stdin=json.dumps(data))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "mode": "compose", "integrations": [{"a": "react", "b": "express", "tier": "T2"}],
    }


def test_metadata_reads_a_file(tmp_path):
    path = tmp_path / "stack.json"
    path.write_bytes(json.dumps(stack([("café", "T3", "internal")]), ensure_ascii=False).encode("utf-8"))
    result = run("metadata", "--input", str(path))
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["libraries"] == ["café"]
    assert (out["confidence_tier"], out["source_authority"]) == ("T3", "internal")
    assert result.stdout.isascii(), "non-ASCII names are escaped for a Windows console"


def test_stdin_is_read_as_utf8_under_a_cp1252_console():
    """A Windows pipe hands stdin over as cp1252: `--input -` still reads the UTF-8 a step pipes."""
    data = stack([("café", "T1", None), ("ŝkf", "T2", None)], [("café", "ŝkf")])
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    result = subprocess.run([sys.executable, str(SCRIPT), "metadata", "--input", "-"],
                            input=json.dumps(data, ensure_ascii=False).encode("utf-8"),
                            capture_output=True, env=env)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    out = json.loads(result.stdout.decode("ascii"))
    assert out["libraries"] == ["café", "ŝkf"]  # U+015D is C5 9D in UTF-8; cp1252 has no 0x9D
    assert out["integration_pairs"] == [["café", "ŝkf"]]


@pytest.mark.parametrize("args, stdin, needle", [
    (("metadata", "--input", "-"), "{not json", "not valid JSON"),
    (("metadata", "--input", "-"), '{"mode": "compose", "libraries": [{"name": "a", "confidence": "T9"}]}',
     "libraries[0].confidence"),
    (("pair-tiers", "--input", "missing.json"), None, "cannot read the input"),
], ids=["bad-json", "bad-tier", "missing-file"])
def test_an_input_error_exits_2_with_one_line(args, stdin, needle, tmp_path):
    result = subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True, text=True,
                            cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == ""
    assert needle in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1


@pytest.mark.parametrize("args", [(), ("metadata",), ("pair-tiers", "--input"), ("render", "--input", "-")],
                         ids=["no-command", "no-input", "input-without-value", "unknown-command"])
def test_a_usage_error_exits_2(args):
    result = run(*args, stdin="")
    assert result.returncode == 2
    assert result.stdout == ""


def test_help_names_both_commands():
    result = run("--help")
    assert result.returncode == 0
    assert "pair-tiers" in result.stdout and "metadata" in result.stdout
