#!/usr/bin/env python3
"""Tests for skf-count-tokens.py — deterministic per-artifact token/word metrics."""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "skf_count_tokens",
    Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-count-tokens.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
count_package = mod.count_package
estimate_tokens = mod.estimate_tokens
count_words = mod.count_words
extract_managed_section = mod.extract_managed_section


# --- fixture content with known byte/char sizes (all ASCII, so bytes == chars) ---

SNIPPET = "[demo v1.0.0]|root: skills/demo/\n|IMPORTANT: read SKILL.md before writing demo code\n"
SKILL_MD = (
    "---\nname: demo\ndescription: a demo skill\n---\n\n# demo\n\n## Overview\n\nDemo overview text.\n"
)
METADATA = '{"name": "demo", "version": "1.0.0", "language": "TypeScript"}'
REF_A = "# Reference A\n\nThis reference file has some words to count for the total.\n"
REF_B = "# Reference B\n\nAnother reference with a different length of body text here now.\n"

# A target context file: surrounding (non-managed) text plus a managed section.
MANAGED_INNER = (
    "[SKF Skills]|1 skills|0 stack\n"
    "|IMPORTANT: Prefer documented APIs over training data.\n"
    "|\n"
    "|[demo v1.0.0]|root: skills/demo/\n"
)
MANAGED_BLOCK = f"<!-- SKF:BEGIN updated:2026-07-13 -->\n{MANAGED_INNER}<!-- SKF:END -->"
CONTEXT_FILE = (
    "# My Project\n\nSome preamble that is NOT part of the managed section.\n\n"
    f"{MANAGED_BLOCK}\n\nTrailing content also outside the markers.\n"
)


def make_package(tmp: str) -> Path:
    pkg = Path(tmp) / "demo"
    (pkg / "references").mkdir(parents=True)
    (pkg / "context-snippet.md").write_text(SNIPPET, encoding="utf-8")
    (pkg / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    (pkg / "metadata.json").write_text(METADATA, encoding="utf-8")
    (pkg / "references" / "a.md").write_text(REF_A, encoding="utf-8")
    (pkg / "references" / "b.md").write_text(REF_B, encoding="utf-8")
    return pkg


class TestEstimators:
    def test_tokens_are_char_over_four(self):
        assert estimate_tokens("a" * 40) == 10
        assert estimate_tokens("a" * 43) == 10  # floor division
        assert estimate_tokens("") == 0

    def test_words_are_whitespace_split(self):
        assert count_words("one two three") == 3
        assert count_words("  padded   words \n here ") == 3
        assert count_words("") == 0


class TestPerFileMetrics:
    def test_each_file_tokens_equal_len_over_four(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            r = count_package(pkg)
            rows = {row["path"]: row for row in r["files"]}
            assert rows["context-snippet.md"]["tokens"] == len(SNIPPET) // 4
            assert rows["SKILL.md"]["tokens"] == len(SKILL_MD) // 4
            assert rows["metadata.json"]["tokens"] == len(METADATA) // 4
            assert rows["references/a.md"]["tokens"] == len(REF_A) // 4
            assert rows["references/b.md"]["tokens"] == len(REF_B) // 4
            # words too
            assert rows["context-snippet.md"]["words"] == len(SNIPPET.split())

    def test_missing_core_file_reported_as_absent_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "demo"
            pkg.mkdir()
            (pkg / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
            r = count_package(pkg)
            rows = {row["path"]: row for row in r["files"]}
            assert rows["context-snippet.md"]["exists"] is False
            assert rows["context-snippet.md"]["tokens"] == 0
            assert rows["context-snippet.md"]["words"] == 0


class TestReferencesTotal:
    def test_references_total_is_sum_of_ref_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            r = count_package(pkg)
            assert r["references_total"]["count"] == 2
            assert r["references_total"]["tokens"] == len(REF_A) // 4 + len(REF_B) // 4
            assert r["references_total"]["words"] == len(REF_A.split()) + len(REF_B.split())

    def test_no_references_dir_yields_zero_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "demo"
            pkg.mkdir()
            (pkg / "context-snippet.md").write_text(SNIPPET, encoding="utf-8")
            (pkg / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
            (pkg / "metadata.json").write_text(METADATA, encoding="utf-8")
            r = count_package(pkg)
            assert r["references_total"] == {"count": 0, "words": 0, "tokens": 0}


class TestManagedSection:
    def test_managed_section_counts_only_begin_end_span(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            ctx = Path(tmp) / "CLAUDE.md"
            ctx.write_text(CONTEXT_FILE, encoding="utf-8")
            r = count_package(pkg, [ctx])
            ms = r["managed_section"]
            assert ms["present"] is True
            # Only the BEGIN..END block, NOT the surrounding preamble/trailing text.
            assert ms["tokens"] == len(MANAGED_BLOCK) // 4
            assert ms["words"] == len(MANAGED_BLOCK.split())
            # Sanity: surrounding text must not be folded in.
            assert ms["tokens"] < len(CONTEXT_FILE) // 4

    def test_extract_managed_section_returns_full_block(self):
        assert extract_managed_section(CONTEXT_FILE) == MANAGED_BLOCK

    def test_no_target_file_marks_managed_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            r = count_package(pkg)
            assert r["managed_section"]["present"] is False
            assert r["managed_section"]["tokens"] == 0

    def test_first_target_with_block_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            no_block = Path(tmp) / "AGENTS.md"
            no_block.write_text("# no managed section here\n", encoding="utf-8")
            with_block = Path(tmp) / "CLAUDE.md"
            with_block.write_text(CONTEXT_FILE, encoding="utf-8")
            # AGENTS.md (no block) listed first, CLAUDE.md second — CLAUDE.md must win.
            r = count_package(pkg, [no_block, with_block])
            assert r["managed_section"]["present"] is True
            assert r["managed_section"]["source_file"] == with_block.as_posix()


class TestPackageTotal:
    def test_package_total_excludes_managed_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            ctx = Path(tmp) / "CLAUDE.md"
            ctx.write_text(CONTEXT_FILE, encoding="utf-8")
            r = count_package(pkg, [ctx])
            expected_tokens = (
                len(SNIPPET) // 4
                + len(SKILL_MD) // 4
                + len(METADATA) // 4
                + r["references_total"]["tokens"]
            )
            expected_words = (
                len(SNIPPET.split())
                + len(SKILL_MD.split())
                + len(METADATA.split())
                + r["references_total"]["words"]
            )
            assert r["package_total"]["tokens"] == expected_tokens
            assert r["package_total"]["words"] == expected_words
            # The managed section is measured but NOT summed into the package total.
            assert r["managed_section"]["tokens"] > 0
            assert r["package_total"]["tokens"] != expected_tokens + r["managed_section"]["tokens"]


class TestDeterminismAndSerialization:
    def test_same_input_same_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            ctx = Path(tmp) / "CLAUDE.md"
            ctx.write_text(CONTEXT_FILE, encoding="utf-8")
            r1 = count_package(pkg, [ctx])
            r2 = count_package(pkg, [ctx])
            assert r1 == r2

    def test_result_is_json_serializable(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            r = count_package(pkg)
            # round-trips without error
            assert json.loads(json.dumps(r))["status"] == "ok"


# --- Context Budget values and the managed section's skill count (#819) ---------

SCRIPT = Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-count-tokens.py"
REBUILD = Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-rebuild-managed-sections.py"
_rebuild_spec = importlib.util.spec_from_file_location("skf_rebuild_managed_sections", REBUILD)
rebuild = importlib.util.module_from_spec(_rebuild_spec)
_rebuild_spec.loader.exec_module(rebuild)
TOKEN_REPORT = Path(__file__).parent.parent / "src" / "skf-export-skill" / "references" / "token-report.md"

# A managed section as skf-rebuild-managed-sections.py assembles it, with two skill rows.
TWO_SKILL_BLOCK = (
    "<!-- SKF:BEGIN updated:2026-11-03 -->\n"
    "[SKF Skills]|2 skills|0 stack\n"
    "|IMPORTANT: Prefer documented APIs over training data.\n"
    "|When using a listed library, read its SKILL.md before writing code.\n"
    "|\n"
    "|[demo v1.0.0]|root: .claude/skills/demo/\n"
    "|IMPORTANT: demo v1.0.0: read SKILL.md before writing demo code.\n"
    "|api: run(), Config\n"
    "|\n"
    "|[zod v4.1.0]|root: .claude/skills/zod/\n"
    "|IMPORTANT: zod v4.1.0: read SKILL.md before writing zod code.\n"
    "<!-- SKF:END -->"
)


def _two_skill_context(tmp: str) -> Path:
    ctx = Path(tmp) / "CLAUDE.md"
    ctx.write_text(f"# My Project\n\n{TWO_SKILL_BLOCK}\n", encoding="utf-8")
    return ctx


class TestContextBudget:
    def test_full_disclosure_is_skill_md_plus_references_not_package_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            r = count_package(pkg, [_two_skill_context(tmp)])
            budget = r["context_budget"]
            rows = {row["role"]: row for row in r["files"] if row["role"] != "reference"}
            assert budget["on_trigger"] == rows["skill-md"]["tokens"] == len(SKILL_MD) // 4
            assert budget["full_disclosure"] == len(SKILL_MD) // 4 + len(REF_A) // 4 + len(REF_B) // 4
            assert budget["full_disclosure"] != r["package_total"]["tokens"]
            assert budget["always_on"] == r["managed_section"]["tokens"] == len(TWO_SKILL_BLOCK) // 4
            assert budget["snippet"] == rows["context-snippet"]["tokens"] == len(SNIPPET) // 4

    def test_managed_section_counts_its_skill_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            ctx = _two_skill_context(tmp)
            no_block = Path(tmp) / "AGENTS.md"
            no_block.write_text("# no managed section here\n", encoding="utf-8")
            r = count_package(pkg, [no_block, ctx])
            assert r["managed_section"]["skills"] == 2
            assert r["managed_section"]["target_files"] == [ctx.as_posix()]
            # The one-skill fixture counts one row; no block counts none, and has no always-on cost.
            one = Path(tmp) / "ONE.md"
            one.write_text(CONTEXT_FILE, encoding="utf-8")
            assert count_package(pkg, [one])["managed_section"]["skills"] == 1
            none = count_package(pkg, [no_block])
            assert none["managed_section"]["skills"] == 0 and none["context_budget"]["always_on"] is None

    def test_skill_count_agrees_with_the_managed_section_rebuild(self):
        """The rows skf-rebuild-managed-sections.py parses, a row with no `root:` field included."""
        body = (
            "[SKF Skills]|3 skills|1 stack\n"
            "|IMPORTANT: Prefer documented APIs over training data.\n"
            "|\n"
            "|[demo v1.0.0]|root: .claude/skills/demo/\n"
            "|IMPORTANT: demo v1.0.0: read SKILL.md before writing demo code.\n"
            "|\n"
            "[norooted v2.0.0]\n"
            "|IMPORTANT: a row whose snippet has no root field\n"
            "|\n"
            "|[app-stack v0.3.0]|root: .claude/skills/app-stack/\n"
            "|stack: react@19\n"
            "|\n"
            "[zod v4.1.0]|root: .claude/skills/zod/"
        )
        block = f"<!-- SKF:BEGIN updated:2026-11-03 -->\n{body}\n<!-- SKF:END -->"
        rows = rebuild.parse_managed_rows(body)
        assert [r["skill_name"] for r in rows] == ["demo", "norooted", "app-stack", "zod"]
        assert mod.count_managed_skills(block) == len(rows) == 4
        # And the block an `assemble` of two skills writes reads the same in both scripts.
        assert mod.count_managed_skills(TWO_SKILL_BLOCK) == len(rebuild.parse_managed_rows(TWO_SKILL_BLOCK)) == 2

    def test_several_target_files_measure_the_first_and_list_each_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            claude = _two_skill_context(tmp)
            agents = Path(tmp) / "AGENTS.md"
            agents.write_text(f"# Agents\n\n{MANAGED_BLOCK}\n", encoding="utf-8")  # one skill, a smaller block
            binary = Path(tmp) / ".cursorrules"
            binary.write_bytes(b"\xff\xfe not utf-8 <!-- SKF:BEGIN -->\n<!-- SKF:END -->")
            r = count_package(pkg, [claude, binary, agents, claude, Path(tmp) / "." / "AGENTS.md"])
            ms = r["managed_section"]
            assert ms["target_files"] == [claude.as_posix(), agents.as_posix()]
            assert ms["source_file"] == claude.as_posix()
            assert (ms["skills"], ms["tokens"]) == (2, len(TWO_SKILL_BLOCK) // 4)
            assert len(MANAGED_BLOCK) // 4 != ms["tokens"], "the two blocks differ in size"
            assert r["context_budget"]["always_on"] == ms["tokens"]


def _resolve(data, path: str):
    """The value at a dotted JSON path (`managed_section.skills`); a KeyError when it does not resolve."""
    for key in path.split("."):
        data = data[key]
    return data


class TestTokenReportPlaceholders:
    def test_every_report_placeholder_maps_to_a_helper_field(self):
        """token-report.md §2: each placeholder of the report block names a field of the helper's JSON."""
        text = TOKEN_REPORT.read_text(encoding="utf-8")
        present = text[text.index("### 2. Present Token Report"):text.index("### 3. ")]
        mapping, block = present.split('"**Token Report**')
        placeholders = set(re.findall(r"\{[a-z-]+\}", block))
        assert placeholders == {"{n}", "{t}", "{target-file-list}", "{skill-count}", "{count}",
                                "{managed-section-tokens}", "{measured-file}", "{skill-tokens}", "{total-tokens}",
                                "{snippet-tokens}", "{skill-name}"}
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            proc = subprocess.run([sys.executable, str(SCRIPT), str(pkg), "--target-file",
                                   str(_two_skill_context(tmp))], capture_output=True, text=True, timeout=60)
            assert proc.returncode == 0, proc.stderr
            result = json.loads(proc.stdout)
        # Each row's {n} and {t} are its field's words and tokens.
        assert "`{n}` ← the row's `words` and `{t}` ← its `tokens`" in mapping
        for row in re.findall(r"^- `[^`]+` row → (.+)$", mapping, re.MULTILINE):
            role = re.search(r"for `role: ([\w-]+)`", row)
            if role:
                [field] = [f for f in result["files"] if f["role"] == role.group(1)]
            else:
                field = _resolve(result, re.match(r"`([\w.]+)\.words` / `\.tokens`", row).group(1))
            assert isinstance(field["words"], int) and isinstance(field["tokens"], int), row
        # Every other placeholder names its field.
        for placeholder in sorted(placeholders - {"{n}", "{t}"}):
            match = re.search(rf"`{re.escape(placeholder)}` ← `([\w.]+)`", mapping)
            assert match, f"{placeholder} has no mapping"
            _resolve(result, match.group(1))
        assert _resolve(result, "managed_section.skills") == 2
        assert _resolve(result, "context_budget.full_disclosure") != result["package_total"]["tokens"]


# --- #1166 architecture-6: a dry run measures what it staged, a passive-off run no snippet ------

ASSEMBLED_BODY = TWO_SKILL_BLOCK.split("\n", 1)[1].rsplit("\n", 1)[0]  # the block without its marker lines
DRAFT = "[demo v1.1.0]|root: .claude/skills/demo/\n|IMPORTANT: demo v1.1.0: read SKILL.md before writing demo code.\n"


def _cli(*args, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True,
                          encoding="utf-8", timeout=60, cwd=cwd)


def _rows(result: dict) -> dict:
    return {row["role"]: row for row in result["files"] if row["role"] != "reference"}


def _section_numbers(result: dict) -> tuple:
    ms = result["managed_section"]
    return ms["present"], ms["skills"], ms["words"], ms["tokens"], result["context_budget"]["always_on"]


def _token_report_section_1() -> str:
    text = TOKEN_REPORT.read_text(encoding="utf-8")
    return text[text.index("### 1. Measure Token Counts"):text.index("### 2. Present Token Report")]


def _documented(command: str, values: dict) -> list[str]:
    """The argv of a documented `python3 {countTokensHelper} ...` call, its placeholders filled, run with this Python."""
    filled = re.sub(r"\{([\w-]+)\}", lambda m: values[m.group(1)], command)
    words = shlex.split(filled)
    assert words[0] == "python3", command
    return [sys.executable, *words[1:]]


class TestStagedMeasurement:
    def test_snippet_measures_the_draft_as_the_snippet_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            draft = Path(tmp) / "stage" / "drafts" / "demo" / "context-snippet.md"
            draft.parent.mkdir(parents=True)
            draft.write_text(DRAFT, encoding="utf-8")
            proc = _cli(pkg, "--snippet", draft)
            assert proc.returncode == 0, proc.stderr
            result = json.loads(proc.stdout)
            row = _rows(result)["context-snippet"]
            assert Path(row["path"]) == draft and row["exists"] is True
            assert (row["words"], row["tokens"]) == (len(DRAFT.split()), len(DRAFT) // 4)
            assert result["context_budget"]["snippet"] == len(DRAFT) // 4 != len(SNIPPET) // 4
            assert result["package_total"]["tokens"] == count_package(pkg)["package_total"]["tokens"] \
                - len(SNIPPET) // 4 + len(DRAFT) // 4
            # A draft that is not there is reported as absent, not read from the package.
            absent = json.loads(_cli(pkg, "--snippet", Path(tmp) / "none.md").stdout)
            row = _rows(absent)["context-snippet"]
            assert (row["exists"], row["words"], row["tokens"]) == (False, 0, 0)

    def test_no_snippet_leaves_the_row_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)  # a create-skill snippet sits in the package
            proc = _cli(pkg, "--no-snippet")
            assert proc.returncode == 0, proc.stderr
            result = json.loads(proc.stdout)
            assert "context-snippet" not in _rows(result)
            assert result["package_total"]["tokens"] == count_package(pkg)["package_total"]["tokens"] - len(SNIPPET) // 4
            assert result["context_budget"]["snippet"] is None and result["context_budget"]["always_on"] is None
            assert result["managed_section"]["present"] is False

    def test_the_flags_clash_and_a_bad_section_file_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            clash = _cli(pkg, "--snippet", pkg / "context-snippet.md", "--no-snippet")
            assert clash.returncode == 2 and clash.stdout == ""
            binary = Path(tmp) / "binary.skf-content"
            binary.write_bytes(b"[SKF Skills]\xff\xfe\n")
            for bad in (Path(tmp) / "none.skf-content", Path(tmp), binary):
                proc = _cli(pkg, "--section-file", bad)
                assert proc.returncode == 2 and proc.stdout == "", bad
                assert proc.stderr.startswith("error: "), proc.stderr

    def test_section_file_equals_the_block_insert_writes(self):
        """The staged body measures as the section `insert` writes around it, and lists the targets unread."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            body = Path(tmp) / "previews" / "CLAUDE.md.skf-content"
            body.parent.mkdir()
            body.write_bytes(ASSEMBLED_BODY.encode("utf-8"))
            claude, agents = Path(tmp) / "CLAUDE.md", Path(tmp) / "AGENTS.md"
            proc = _cli(pkg, "--section-file", body, "--target-file", claude, "--target-file", agents,
                        "--target-file", claude)
            assert proc.returncode == 0, proc.stderr
            staged = json.loads(proc.stdout)
            ms = staged["managed_section"]
            assert Path(ms["source_file"]) == body
            assert [Path(p) for p in ms["target_files"]] == [claude, agents], "each target once, in order, unread"
            assert not claude.exists() and not agents.exists()
            claude.write_text("# Project\n\nKept text.\n", encoding="utf-8")
            assert rebuild.cmd_insert(str(claude), ASSEMBLED_BODY)["status"] == "ok"
            written = json.loads(_cli(pkg, "--target-file", claude).stdout)
            assert _section_numbers(staged) == _section_numbers(written)
            assert (ms["present"], ms["skills"]) == (True, 2)
            assert ms["tokens"] == len(extract_managed_section(claude.read_text(encoding="utf-8"))) // 4

    def test_the_dry_run_command_measures_what_a_real_run_writes(self):
        """token-report §1's dry-run call, as documented: its snippet and section rows are those of the run that
        writes the same draft and body (§9's insert, §9c's copy)."""
        section = _token_report_section_1()
        [dry] = [line for line in section.splitlines() if line.startswith("python3") and "--section-file" in line]
        [real] = [line for line in section.splitlines() if line.startswith("python3") and "--snippet" not in line]
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            pkg = make_package(tmp)
            stage = project / "skf-export-abcd"
            draft = stage / "drafts" / "demo" / "context-snippet.md"
            draft.parent.mkdir(parents=True)
            draft.write_text(DRAFT, encoding="utf-8")
            (stage / "previews").mkdir()
            (stage / "previews" / "CLAUDE.md.skf-content").write_bytes(ASSEMBLED_BODY.encode("utf-8"))
            values = {"countTokensHelper": SCRIPT.as_posix(), "resolved_skill_package": pkg.as_posix(),
                      "export_stage_dir": stage.as_posix(), "skill-name": "demo", "context_file_1": "CLAUDE.md",
                      "context_file_2": "AGENTS.md"}
            proc = subprocess.run(_documented(dry, values), capture_output=True, text=True, encoding="utf-8",
                                  timeout=60, cwd=project)
            assert proc.returncode == 0, proc.stderr
            staged = json.loads(proc.stdout)
            # The real run: §9 inserts the body, §9c copies the draft into the package.
            assert rebuild.cmd_insert(str(project / "CLAUDE.md"), ASSEMBLED_BODY)["status"] == "ok"
            (pkg / "context-snippet.md").write_bytes(draft.read_bytes())
            proc = subprocess.run(_documented(real, values), capture_output=True, text=True, encoding="utf-8",
                                  timeout=60, cwd=project)
            written = json.loads(proc.stdout)
            for key in ("words", "tokens"):
                assert _rows(staged)["context-snippet"][key] == _rows(written)["context-snippet"][key]
            assert _section_numbers(staged) == _section_numbers(written)
            assert staged["managed_section"]["target_files"] == ["CLAUDE.md", "AGENTS.md"]
            assert staged["package_total"] == written["package_total"]

    def test_a_re_export_dry_run_measures_the_assembled_section_not_the_one_on_disk(self):
        """A re-export: CLAUDE.md holds an earlier one-skill block. The dry-run call measures the body `assemble --out`
        staged, and §9's `replace < {content_file}` writes a block that measures the same."""
        section = _token_report_section_1()
        [dry] = [line for line in section.splitlines() if line.startswith("python3") and "--section-file" in line]
        [real] = [line for line in section.splitlines() if line.startswith("python3") and "--snippet" not in line]
        older = ("<!-- SKF:BEGIN updated:2026-07-13 -->\n[SKF Skills]|1 skills|0 stack\n"
                 "|IMPORTANT: Prefer documented APIs over training data.\n|\n|[old v0.1.0]|root: skills/old/\n"
                 "<!-- SKF:END -->")
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            pkg = make_package(tmp)
            (project / "skills").mkdir()
            claude = project / "CLAUDE.md"
            claude.write_text(f"# Project\n\n{older}\n\nKept text.\n", encoding="utf-8")
            stage = project / "skf-export-abcd"
            draft = stage / "drafts" / "demo" / "context-snippet.md"
            draft.parent.mkdir(parents=True)
            draft.write_text(DRAFT, encoding="utf-8")
            preview = stage / "previews" / "CLAUDE.md.skf-content"
            assemble = subprocess.run(
                [sys.executable, str(REBUILD), "assemble", "CLAUDE.md", "--skills-folder", "skills",
                 "--skill-root", ".claude/skills/", "--include", "demo@1.1.0",
                 "--snippet-dir", (stage / "drafts").as_posix(), "--orphan-sources", "CLAUDE.md",
                 "--orphans", "keep", "--out", preview.as_posix()],
                capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=project)
            assert assemble.returncode == 0, assemble.stdout + assemble.stderr
            values = {"countTokensHelper": SCRIPT.as_posix(), "resolved_skill_package": pkg.as_posix(),
                      "export_stage_dir": stage.as_posix(), "skill-name": "demo", "context_file_1": "CLAUDE.md",
                      "context_file_2": "AGENTS.md"}
            def run(command):
                proc = subprocess.run(_documented(command, values), capture_output=True, text=True,
                                      encoding="utf-8", timeout=60, cwd=project)
                assert proc.returncode == 0, proc.stderr
                return json.loads(proc.stdout)

            on_disk, staged = run(real), run(dry)
            assert Path(staged["managed_section"]["source_file"]) == preview
            assert (on_disk["managed_section"]["skills"], staged["managed_section"]["skills"]) == (1, 2)
            # §9 regenerates the target from the staged file, by stdin redirection; §9c copies the draft.
            with preview.open("rb") as body:
                write = subprocess.run([sys.executable, str(REBUILD), "CLAUDE.md", "replace"], stdin=body,
                                       capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=project)
            assert write.returncode == 0, write.stdout + write.stderr
            (pkg / "context-snippet.md").write_bytes(draft.read_bytes())
            written = run(real)
            assert _section_numbers(staged) == _section_numbers(written)
            assert staged["package_total"] == written["package_total"]
        mapping = TOKEN_REPORT.read_text(encoding="utf-8")
        assert ("- `{measured-file}` ← `managed_section.source_file`, the target file the helper measured; on a dry "
                "run, which measures the staged preview, `{context_file_1}` instead") in mapping

    def test_a_crlf_body_measures_as_the_block_written_from_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            body = Path(tmp) / "CLAUDE.md.skf-content"
            body.write_bytes(ASSEMBLED_BODY.replace("\n", "\r\n").encode("utf-8"))
            claude = Path(tmp) / "CLAUDE.md"
            staged = json.loads(_cli(pkg, "--section-file", body, "--target-file", claude).stdout)
            with body.open("rb") as stdin:
                write = subprocess.run([sys.executable, str(REBUILD), str(claude), "insert"], stdin=stdin,
                                       capture_output=True, text=True, encoding="utf-8", timeout=60)
            assert write.returncode == 0, write.stdout + write.stderr
            written = json.loads(_cli(pkg, "--target-file", claude).stdout)
            assert _section_numbers(staged) == _section_numbers(written)

    def test_the_passive_off_command_reports_no_snippet_and_no_section(self):
        section = _token_report_section_1()
        line = next(line for line in section.splitlines() if line.startswith("**If `passive_context` was disabled:**"))
        [command] = re.findall(r"`(python3 \{countTokensHelper\}[^`]*)`", line)
        assert "--target-file" not in command and "with no `--target-file`" in line
        assert '"N/A (disabled)", since `{passive_context}` is false' in line
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)  # a create-skill snippet that this run does not publish
            _two_skill_context(tmp)  # and a managed section an earlier run wrote
            proc = subprocess.run(_documented(command, {"countTokensHelper": SCRIPT.as_posix(),
                                                        "resolved_skill_package": pkg.as_posix()}),
                                  capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=tmp)
            assert proc.returncode == 0, proc.stderr
            result = json.loads(proc.stdout)
            assert "context-snippet" not in _rows(result) and result["managed_section"]["present"] is False
            assert (result["context_budget"]["snippet"], result["context_budget"]["always_on"]) == (None, None)

    def test_the_report_states_its_json_once(self):
        """leanness-7: no shape block and no gloss paragraphs; §2's mapping lists say what each value is."""
        text = TOKEN_REPORT.read_text(encoding="utf-8")
        frontmatter = text.split("\n---\n", 1)[0]
        assert frontmatter.endswith("\n# SKILL.md's On Activation resolved {countTokensHelper}.")
        assert "word-counting every file" not in frontmatter
        section = _token_report_section_1()
        assert "```json" not in section and "The helper emits JSON" not in section
        for gloss in ("`managed_section.skills` counts", "**excludes** the `managed_section` row",
                      "Read the JSON", "`context_budget` gives the Context Budget Impact values"):
            assert gloss not in section, gloss
        assert ("Each `tokens` value is a char-over-four estimate (`len(text)//4`, the SKF-wide convention shared "
                "with `skf-validate-output.py`)") in section
        rules = text[text.index("## Rules"):text.index("## MANDATORY SEQUENCE")]
        assert ("- Focus only on token counting and reporting: this step writes nothing, and deletes only a dry "
                "run's stage folder (§3)") in rules
        assert chr(0x2014) not in rules
