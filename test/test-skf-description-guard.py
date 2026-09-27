#!/usr/bin/env python3
"""Tests for skf-description-guard.py.

Covers:
  - capture: happy path, missing file, no frontmatter, missing description
  - classify_divergence: identical, whitespace-only, replaced, truncated, deleted
  - restore_description: inline/quoted/block-scalar shapes; key order preserved
  - empty/whitespace-only captured value is refused, never written (#474)
  - CLI integration via subprocess for capture and verify-restore
  - calling-step prose: both steps resolve the protocol by probe order and
    state the restore and empty-snapshot record rules themselves
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


def _parse_frontmatter(text: str) -> dict:
    """Extract the frontmatter mapping from a SKILL.md text blob."""
    assert text.startswith("---\n"), "expected leading frontmatter fence"
    rest = text[4:]
    close = rest.find("\n---\n")
    assert close != -1, "expected closing frontmatter fence"
    return yaml.safe_load(rest[:close])


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-description-guard.py"

spec = importlib.util.spec_from_file_location("skf_description_guard", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


SAMPLE_DESC = "Compiles a verified agent skill from a brief and source code."


def _write_skill(tmp_path: Path, description: str, *, shape: str = "inline") -> Path:
    """Write a SKILL.md with given description in one of three frontmatter shapes."""
    if shape == "inline":
        fm = f"""---
name: my-skill
description: {description}
---

# My Skill

Body content.
"""
    elif shape == "quoted":
        fm = f'''---
name: my-skill
description: "{description}"
---

# My Skill

Body content.
'''
    elif shape == "block":
        fm = f"""---
name: my-skill
description: |
  {description}
---

# My Skill

Body content.
"""
    else:
        raise ValueError(shape)
    path = tmp_path / "SKILL.md"
    path.write_text(fm, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# read_description / capture
# --------------------------------------------------------------------------


class TestReadDescription:
    def test_inline_description(self, tmp_path: Path) -> None:
        skill = _write_skill(tmp_path, SAMPLE_DESC, shape="inline")
        desc, hash_ = mod.read_description(skill)
        assert desc == SAMPLE_DESC
        assert hash_.startswith("sha256:")
        assert len(hash_) == len("sha256:") + 64

    def test_quoted_description(self, tmp_path: Path) -> None:
        skill = _write_skill(tmp_path, SAMPLE_DESC, shape="quoted")
        desc, _ = mod.read_description(skill)
        assert desc == SAMPLE_DESC

    def test_block_description(self, tmp_path: Path) -> None:
        skill = _write_skill(tmp_path, SAMPLE_DESC, shape="block")
        desc, _ = mod.read_description(skill)
        # block scalar preserves a trailing newline by default
        assert desc.strip() == SAMPLE_DESC

    def test_no_frontmatter_raises(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text("# My Skill\n\nNo frontmatter here.\n", encoding="utf-8")
        with pytest.raises(ValueError, match="no frontmatter"):
            mod.read_description(skill)

    def test_missing_description_raises(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text("---\nname: foo\n---\n\nBody\n", encoding="utf-8")
        with pytest.raises(ValueError, match="no `description`"):
            mod.read_description(skill)

    def test_malformed_yaml_raises(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text("---\nname: : :\n---\nBody\n", encoding="utf-8")
        with pytest.raises(ValueError, match="not valid YAML"):
            mod.read_description(skill)


# --------------------------------------------------------------------------
# classify_divergence
# --------------------------------------------------------------------------


class TestClassifyDivergence:
    def test_byte_identical(self) -> None:
        assert mod.classify_divergence("hello world", "hello world") == "none"

    def test_whitespace_only_trailing_newline(self) -> None:
        assert mod.classify_divergence("hello world", "hello world\n") == "whitespace-only"

    def test_whitespace_only_collapsed_runs(self) -> None:
        assert mod.classify_divergence("hello  world", "hello world") == "whitespace-only"

    def test_whitespace_only_trim(self) -> None:
        assert mod.classify_divergence("hello world", "  hello world  ") == "whitespace-only"

    def test_replaced(self) -> None:
        assert mod.classify_divergence("hello world", "goodbye world") == "replaced"

    def test_truncated(self) -> None:
        assert mod.classify_divergence("hello world today", "hello world") == "truncated"

    def test_truncated_single_word(self) -> None:
        assert mod.classify_divergence("hello world", "hello") == "truncated"

    def test_deleted(self) -> None:
        assert mod.classify_divergence("hello world", "") == "deleted"
        assert mod.classify_divergence("hello world", "   \t  ") == "deleted"

    def test_angle_bracket_reintroduction_is_replaced(self) -> None:
        # post-tool description re-introduces an angle-bracket token —
        # token-stream comparison sees a different word
        captured = "Use when running tests"
        current = "Use when running tests <component>"
        assert mod.classify_divergence(captured, current) == "replaced"

    def test_is_diverged_true_for_real_changes(self) -> None:
        assert mod.is_diverged("replaced") is True
        assert mod.is_diverged("truncated") is True
        assert mod.is_diverged("deleted") is True

    def test_is_diverged_false_for_non_changes(self) -> None:
        assert mod.is_diverged("none") is False
        assert mod.is_diverged("whitespace-only") is False


# --------------------------------------------------------------------------
# restore_description
# --------------------------------------------------------------------------


class TestRestoreDescription:
    def test_restore_inline_preserves_other_keys(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text(
            """---
name: my-skill
description: tool-rewritten short version
version: 1.2.3
---

# Body
""",
            encoding="utf-8",
        )
        mod.restore_description(skill, "the authoritative original description")
        text = skill.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        # frontmatter parses as valid YAML with all expected keys
        assert fm["name"] == "my-skill"
        assert fm["description"] == "the authoritative original description"
        assert fm["version"] == "1.2.3"
        # key order preserved (name → description → version)
        assert list(fm.keys()) == ["name", "description", "version"]
        # body untouched
        assert "# Body" in text

    def test_restore_quoted(self, tmp_path: Path) -> None:
        skill = _write_skill(tmp_path, "tool wrote this", shape="quoted")
        mod.restore_description(skill, "original")
        fm = _parse_frontmatter(skill.read_text(encoding="utf-8"))
        assert fm["description"] == "original"

    def test_restore_block_scalar_collapses_to_inline(self, tmp_path: Path) -> None:
        skill = _write_skill(tmp_path, "tool wrote this", shape="block")
        mod.restore_description(skill, "original")
        text = skill.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        assert fm["description"] == "original"
        # the prior block-scalar shape (`description: |` with continuation lines)
        # MUST NOT survive — its leftover continuation block was the original
        # failure mode this fix targets
        assert "description: |" not in text
        assert "description: >" not in text

    def test_restore_escapes_embedded_quotes(self, tmp_path: Path) -> None:
        skill = _write_skill(tmp_path, "x", shape="inline")
        mod.restore_description(skill, 'has "double" quotes and \\ backslash')
        fm = _parse_frontmatter(skill.read_text(encoding="utf-8"))
        # round-trip through YAML emit/parse preserves the value verbatim,
        # regardless of which quoting style safe_dump chose
        assert fm["description"] == 'has "double" quotes and \\ backslash'

    def test_restore_atomic_no_partial_file(self, tmp_path: Path) -> None:
        # after restore, no .skf-guard.tmp files remain in the directory
        skill = _write_skill(tmp_path, "tool wrote this", shape="inline")
        mod.restore_description(skill, "original")
        leftover = [p for p in tmp_path.iterdir() if ".skf-guard.tmp" in p.name]
        assert leftover == []

    def test_restore_roundtrip_via_read(self, tmp_path: Path) -> None:
        skill = _write_skill(tmp_path, "tool wrote this", shape="inline")
        mod.restore_description(skill, "the original")
        desc, _ = mod.read_description(skill)
        assert desc == "the original"

    def test_restore_block_scalar_with_keys_after(self, tmp_path: Path) -> None:
        """Regression: folded `>` description followed by sibling keys.

        The previous line-rewrite implementation could leave continuation
        lines on disk in certain layouts, producing invalid YAML where the
        new inline `description:` was followed by orphan indented text.
        With YAML round-trip, the output is always parseable.
        """
        skill = tmp_path / "SKILL.md"
        skill.write_text(
            """---
name: my-skill
description: >
  Tool-rewritten short
  version on multiple
  lines.
license: MIT
metadata:
  version: 1.2.3
---

# Body
""",
            encoding="utf-8",
        )
        mod.restore_description(skill, "the authoritative original")
        text = skill.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        assert fm["description"] == "the authoritative original"
        assert fm["name"] == "my-skill"
        assert fm["license"] == "MIT"
        assert fm["metadata"] == {"version": "1.2.3"}

    def test_restore_does_not_touch_nested_description_key(self, tmp_path: Path) -> None:
        """Regression: a `description:` inside a nested mapping must not
        be mistaken for the top-level field, and must be left untouched.
        """
        skill = tmp_path / "SKILL.md"
        skill.write_text(
            """---
metadata:
  description: nested — must not be touched
name: my-skill
description: top-level tool-rewritten
---

# Body
""",
            encoding="utf-8",
        )
        mod.restore_description(skill, "top-level original")
        fm = _parse_frontmatter(skill.read_text(encoding="utf-8"))
        assert fm["description"] == "top-level original"
        assert fm["metadata"]["description"] == "nested — must not be touched"

    def test_restore_when_only_nested_description_exists_raises(
        self, tmp_path: Path
    ) -> None:
        """Regression: if the top-level frontmatter has no `description`
        field (only a nested one), restore must fail loudly rather than
        silently rewriting the nested key.
        """
        skill = tmp_path / "SKILL.md"
        skill.write_text(
            """---
name: my-skill
related:
  description: nested only
---

# Body
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="no `description`"):
            mod.restore_description(skill, "should not be written anywhere")

    @pytest.mark.parametrize("captured", ["", "   ", "\n\t "])
    def test_restore_refuses_empty_captured(self, tmp_path: Path, captured: str) -> None:
        """Regression (#474): no code path may write an empty description —
        library callers are refused at the same boundary as the CLI."""
        skill = _write_skill(tmp_path, SAMPLE_DESC, shape="inline")
        before = skill.read_bytes()
        with pytest.raises(ValueError, match="empty"):
            mod.restore_description(skill, captured)
        assert skill.read_bytes() == before
        leftover = [p for p in tmp_path.iterdir() if ".skf-guard.tmp" in p.name]
        assert leftover == []


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
    def test_capture_emits_json(self, tmp_path: Path) -> None:
        skill = _write_skill(tmp_path, SAMPLE_DESC, shape="inline")
        result = _run_cli("capture", str(skill))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["description"] == SAMPLE_DESC
        assert payload["schema_hash"].startswith("sha256:")

    def test_capture_missing_file_exits_1(self, tmp_path: Path) -> None:
        result = _run_cli("capture", str(tmp_path / "missing.md"))
        assert result.returncode == 1
        assert "file not found" in result.stderr

    def test_verify_restore_no_divergence(self, tmp_path: Path) -> None:
        skill = _write_skill(tmp_path, SAMPLE_DESC, shape="inline")
        result = _run_cli(
            "verify-restore", str(skill), "--captured-description", SAMPLE_DESC
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["diverged"] is False
        assert payload["restored"] is False
        assert payload["diff_kind"] == "none"

    def test_verify_restore_whitespace_only_no_restore(self, tmp_path: Path) -> None:
        # disk has trailing whitespace, captured doesn't — token streams match
        skill = _write_skill(tmp_path, SAMPLE_DESC + "  ", shape="quoted")
        result = _run_cli(
            "verify-restore", str(skill), "--captured-description", SAMPLE_DESC
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["diverged"] is False
        assert payload["diff_kind"] == "whitespace-only"

    def test_verify_restore_replaced_restores(self, tmp_path: Path) -> None:
        # disk has tool-rewritten short version; captured is the real one
        skill = _write_skill(tmp_path, "tool short version", shape="inline")
        result = _run_cli(
            "verify-restore", str(skill), "--captured-description", SAMPLE_DESC
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["diverged"] is True
        assert payload["restored"] is True
        assert payload["diff_kind"] == "replaced"
        # file now has the captured description
        text = skill.read_text(encoding="utf-8")
        assert SAMPLE_DESC in text

    def test_verify_restore_truncated_restores(self, tmp_path: Path) -> None:
        # disk has a truncated version of the captured description
        skill = _write_skill(tmp_path, "Compiles a verified agent skill", shape="inline")
        result = _run_cli(
            "verify-restore", str(skill), "--captured-description", SAMPLE_DESC
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["diff_kind"] == "truncated"
        assert payload["restored"] is True

    def test_verify_restore_missing_arg_exits_2(self, tmp_path: Path) -> None:
        # argparse missing-required-arg exits 2 by convention
        skill = _write_skill(tmp_path, SAMPLE_DESC, shape="inline")
        result = _run_cli("verify-restore", str(skill))
        assert result.returncode == 2
        assert "captured-description" in result.stderr

    @pytest.mark.parametrize("captured", ["", "   \t "])
    def test_verify_restore_empty_captured_exits_1_and_leaves_file(
        self, tmp_path: Path, captured: str
    ) -> None:
        """Regression (#474): `verify-restore --captured-description ""` used to
        report {"diverged": true, "restored": true, "diff_kind": "replaced"} and
        write `description: ''`, destroying the field the guard exists to protect.
        """
        skill = _write_skill(tmp_path, SAMPLE_DESC, shape="inline")
        before = skill.read_bytes()
        result = _run_cli(
            "verify-restore", str(skill), "--captured-description", captured
        )
        assert result.returncode == 1
        assert result.stdout == ""
        assert "empty or whitespace-only" in result.stderr
        assert skill.read_bytes() == before
        desc, _ = mod.read_description(skill)
        assert desc == SAMPLE_DESC

    def test_verify_restore_empty_captured_refused_before_file_checks(
        self, tmp_path: Path
    ) -> None:
        # the argument is validated before any file I/O, so the empty-capture
        # refusal is what a caller sees even when the path is wrong
        result = _run_cli(
            "verify-restore", str(tmp_path / "missing.md"), "--captured-description", ""
        )
        assert result.returncode == 1
        assert "empty or whitespace-only" in result.stderr


# --------------------------------------------------------------------------
# Calling-step prose: the protocol resolves in an installed project, and each
# step states the guard rules its evidence-report populator depends on
# --------------------------------------------------------------------------

PROTOCOL_MD = REPO_ROOT / "src" / "shared" / "references" / "description-guard-protocol.md"
# (step file, first heading after §0, evidence-report section, description kind)
GUARD_STEPS = {
    "create-skill": (
        REPO_ROOT / "src" / "skf-create-skill" / "references" / "validate.md",
        "### 1. Check Tool Availability",
        "§8",
        "compiled",
    ),
    "update-skill": (
        REPO_ROOT / "src" / "skf-update-skill" / "references" / "write.md",
        "### 1. Verify SKILL.md Write",
        "§4",
        "merged",
    ),
}
# (start, end) of each step's Description Guard evidence-report populator
POPULATORS = {
    "create-skill": ("**Description Guard population:**", "### 9. Auto-Proceed"),
    "update-skill": ("**Description Guard population**", "**Context Snippet population**"),
}
PROTOCOL_PROBE_BLOCK = (
    "# Resolve `{descriptionGuardProtocol}` (the guard's prose protocol, not its\n"
    "# helper script) by probing `{descriptionGuardProtocolProbeOrder}` in order\n"
    "# (installed SKF module path first, src/ dev-checkout fallback); first\n"
    "# existing path wins. Advisory: if neither path exists, skip the load and\n"
    "# continue, because §0 states every guard rule this step acts on and the\n"
    "# protocol only explains them.\n"
    "descriptionGuardProtocolProbeOrder:\n"
    "  - '{project-root}/_bmad/skf/shared/references/description-guard-protocol.md'\n"
    "  - '{project-root}/src/shared/references/description-guard-protocol.md'\n"
)
PROTOCOL_PROBE_ORDER = [
    "{project-root}/_bmad/skf/shared/references/description-guard-protocol.md",
    "{project-root}/src/shared/references/description-guard-protocol.md",
]


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def _slice(text: str, start: str, end: str) -> str:
    assert text.count(start) == 1, f"expected exactly one {start!r}"
    head = text.index(start)
    assert end in text[head:], f"expected {end!r} after {start!r}"
    body = text[head : text.index(end, head)]
    assert body.strip(), f"empty slice after {start!r}"
    return body


def _step_frontmatter(text: str) -> str:
    assert text.startswith("---\n"), "expected leading frontmatter fence"
    return text[4 : text.index("\n---\n", 4) + 1]


def _section0(path: Path, end: str) -> str:
    return _slice(_read(path), "### 0. Description Guard Protocol", end)


@pytest.mark.parametrize("step", sorted(GUARD_STEPS))
class TestGuardStepProse:
    def test_protocol_resolves_by_probe_order(self, step: str) -> None:
        path, _, _, _ = GUARD_STEPS[step]
        fm_text = _step_frontmatter(_read(path))
        assert PROTOCOL_PROBE_BLOCK in fm_text
        fm = yaml.safe_load(fm_text)
        assert fm.get("descriptionGuardProtocolProbeOrder") == PROTOCOL_PROBE_ORDER
        assert "descriptionGuardProtocol" not in fm, "the bare src/ scalar must be gone"
        comment = _slice(
            fm_text,
            "# Resolve `{descriptionGuardProtocol}` (the guard's prose protocol",
            "descriptionGuardProtocolProbeOrder:",
        )
        assert "Advisory" in comment and "HALT" not in comment

    def test_section0_resolves_the_protocol_without_halting(self, step: str) -> None:
        path, end, _, _ = GUARD_STEPS[step]
        section = _section0(path, end)
        assert (
            "Resolve `{descriptionGuardProtocol}` ← first existing path in "
            "`{descriptionGuardProtocolProbeOrder}` and load it" in section
        )
        assert "The load is advisory: if neither path exists, continue" in section
        assert "Load `{descriptionGuardProtocol}`" not in section, "resolve before loading"
        assert "HALT" not in section

    def test_section0_binds_the_helper_outputs(self, step: str) -> None:
        path, end, report, _ = GUARD_STEPS[step]
        section = _section0(path, end)
        for phrase in (
            "Bind `{guarded_description}` ← `description` from each `capture`, run while "
            "the in-context SKILL.md copy matches the file on disk.",
            "Bind `{guard_restored}` ← `restored` and `{guard_diff_kind}` ← `diff_kind` "
            "from each `verify-restore`.",
            "When `{guard_restored}` is true, set the in-context `description` to "
            "`{guarded_description}`",
            "record `description_guard_restored: true` with the tool name and "
            "`description_guard_diff_kind: {guard_diff_kind}` in workflow context for the "
            f"evidence report ({report}).",
            "A later `verify-restore` that exits 0 with `{guard_restored}` false leaves "
            "those records in place.",
        ):
            assert phrase in section, phrase
        # The per-call flag must not share a name with the record the
        # populator reads, or a later clean call would overwrite a restore.
        text = _read(path)
        assert "`{description_guard_restored}`" not in text
        assert "`{description_guard_diff_kind}`" not in text

    def test_section0_states_the_empty_snapshot_rule(self, step: str) -> None:
        path, end, report, kind = GUARD_STEPS[step]
        section = _section0(path, end)
        rule = _slice(section, "**Empty-snapshot rule.**", "\n")
        for phrase in (
            "`verify-restore` refuses an empty or whitespace-only `--captured-description` "
            "(exit 1, file untouched).",
            "Never re-run it with the empty value",
            f"If the {kind} description is still in context (the in-context SKILL.md copy), "
            "re-run `verify-restore` with that value.",
            "Otherwise record `description_guard_restored: false` and "
            "`description_guard_refused: empty-capture` with the tool name",
            f"the evidence report ({report}) renders that as a fired guard, not as a clean run.",
        ):
            assert phrase in rule, phrase

    def test_populator_reads_the_section0_records(self, step: str) -> None:
        path, _, _, _ = GUARD_STEPS[step]
        text = _read(path)
        populator = _slice(text, *POPULATORS[step])
        assert "(§0's empty-snapshot rule" in populator
        assert "based on the recorded `description_guard_diff_kind`" in populator
        assert "the protocol's empty-snapshot rule" not in text
        assert "the §0 protocol's empty-snapshot rule" not in text


def test_protocol_commands_use_the_caller_resolved_helpers() -> None:
    text = _read(PROTOCOL_MD)
    assert "{project-root}/src/" not in text
    assert "`src/shared/scripts/skf-description-guard.py`" not in text
    guard = _slice(text, "## The Four-Phase Guard", "## Why Token-Stream Comparison")
    assert guard.count("uv run {descriptionGuardHelper} \\\n") == 2
    revalidate = _slice(text, "## Post-Restore Re-Validation (Optional)", "## Why This Protocol Is Centralized")
    assert "uv run {frontmatterValidator} <skill-md-path>" in revalidate


def test_protocol_keeps_the_rules_the_steps_repeat() -> None:
    # Each calling step states the restore handling and the empty-snapshot
    # rule in its §0; the protocol must record the same keys and say so.
    text = _read(PROTOCOL_MD)
    verify = _slice(text, "### 3 + 4. Verify and Restore", "**Empty snapshot refusal.**")
    assert "Record `description_guard_restored: true` (with the tool name and the `diff_kind`)" in verify
    rule = _slice(text, "**Empty snapshot refusal.**", "## Why Token-Stream Comparison")
    assert "`description_guard_refused: empty-capture`" in rule
    assert "Never retry with the empty value" in rule
    centralized = _slice(text, "## Why This Protocol Is Centralized", "## Calling Workflows")
    assert "also stated in the stage's §0" in centralized

# --------------------------------------------------------------------------
# sanitize (create-skill step 6 §6)
# --------------------------------------------------------------------------


class TestSanitize:
    def test_substitution_matches_compile_2a(self) -> None:
        assert mod.sanitize_angle_brackets("Meta<typeof X> and <b>x</b>") == ("Meta{typeof X} and {b}x{/b}", 6)
        assert mod.sanitize_angle_brackets("clean") == ("clean", 0)

    def test_cli_rewrites_only_the_description(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_bytes(
            b'---\nname: my-skill\ndescription: "Maps `Array<T>` for $HOME. Use when mapping."\nlicense: MIT\n'
            b"---\n\n# My Skill\n\nBody keeps <T> as is.\n"
        )
        result = _run_cli("sanitize", str(skill))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload == {"substitutions": 2, "sanitized": True,
                           "description": "Maps `Array{T}` for $HOME. Use when mapping."}
        raw = skill.read_bytes()
        assert b"\r\n" not in raw
        text = raw.decode("utf-8")
        fm = _parse_frontmatter(text)
        assert fm == {"name": "my-skill", "description": payload["description"], "license": "MIT"}
        assert text.endswith("# My Skill\n\nBody keeps <T> as is.\n")

    def test_cli_leaves_a_clean_file_untouched(self, tmp_path: Path) -> None:
        skill = _write_skill(tmp_path, SAMPLE_DESC, shape="quoted")
        before = skill.read_bytes()
        result = _run_cli("sanitize", str(skill))
        assert result.returncode == 0
        assert json.loads(result.stdout) == {"substitutions": 0, "sanitized": False, "description": SAMPLE_DESC}
        assert skill.read_bytes() == before

    def test_cli_missing_file_is_a_user_error(self, tmp_path: Path) -> None:
        result = _run_cli("sanitize", str(tmp_path / "SKILL.md"))
        assert result.returncode == 1 and result.stdout == ""

    def test_restore_writes_lf_line_endings(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Text mode would write CRLF on Windows; the writer must pass newline=""."""
        seen = {}
        real_fdopen = mod.os.fdopen

        def fdopen(fd, *args, **kwargs):
            seen.update(kwargs)
            return real_fdopen(fd, *args, **kwargs)

        monkeypatch.setattr(mod.os, "fdopen", fdopen)
        skill = _write_skill(tmp_path, "old value", shape="inline")
        mod.restore_description(skill, "new value")
        assert seen.get("newline") == ""
