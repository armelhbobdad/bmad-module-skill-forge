#!/usr/bin/env python3
"""Tests for skf-skill-summaries.py (skf-verify-stack integrations.md §3, #1197).

Covers the reply contract (required and optional keys, their types, `language`
and other keys dropped), the inventory join, the rejected replies with their
reasons (no reply, not JSON, not an object, a missing or wrong-typed key), the
20% budget over the subagent reads only, the bad calls (exit 2) and unusable
inputs (exit 1) that write nothing, a re-read that recovers a skill, the CLI
(JSON on stdout, --help), and the stage text that runs the merge, re-reads a
rejected skill, halts on the budget and reports a skill it still cannot read.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILL = REPO_ROOT / "src" / "skf-verify-stack"
REFERENCES = SKILL / "references"
SCRIPT_PATH = SKILL / "scripts" / "skf-skill-summaries.py"
SCHEMA = REPO_ROOT / "src" / "shared" / "scripts" / "schemas" / "skf-verify-stack-result-envelope.v1.json"

spec = importlib.util.spec_from_file_location("skf_skill_summaries", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def _inventory_entry(name, language="TypeScript", exports=None, documented=None):
    exports = [f"{name}Fn"] if exports is None else exports
    return {"name": name, "path": f"{name}/active/{name}", "language": language, "exports": exports,
            "exports_documented": len(exports) if documented is None else documented, "evidence_tier": "T1"}


# An override that leaves the key out of the reply.
_DROP = object()


def _reply(name, **overrides):
    reply = {"skill_name": name, "exports": [f"{name}(x): Y"], "capabilities": [f"{name} things"],
             "protocols_inferred": ["HTTP"], "data_formats_inferred": ["JSON"]}
    reply.update(overrides)
    return {key: value for key, value in reply.items() if value is not _DROP}


class Run:
    """A run folder: the inventory, the summaries folder and the merged file."""

    def __init__(self, root: Path, names, **inventory_overrides):
        self.root = root
        self.dir = root / "summaries"
        self.dir.mkdir()
        self.inventory = root / "skill-inventory.json"
        entries = [inventory_overrides.get(name) or _inventory_entry(name) for name in names]
        self.inventory.write_bytes(json.dumps({"skills": entries, "warnings": []}).encode("utf-8"))
        self.output = root / "skill-summaries.json"

    def write(self, name, reply):
        data = reply if isinstance(reply, (str, bytes)) else json.dumps(reply)
        (self.dir / f"{name}.json").write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))

    def merge(self, skills, subagent_skills=None, output=None):
        args = [sys.executable, str(SCRIPT_PATH), "merge", "--dir", str(self.dir), "--inventory",
                str(self.inventory), "--skills", ",".join(skills), "-o", str(output or self.output)]
        if subagent_skills is not None:
            args += ["--subagent-skills", ",".join(subagent_skills)]
        return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", check=False)

    def merged(self):
        return json.loads(self.output.read_text(encoding="utf-8"))


def _ok(proc):
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


# --- The matrix rows -------------------------------------------------------------


def test_all_valid_replies_are_merged_in_skills_order(tmp_path):
    names = ["zod", "react-query", "next"]
    run = Run(tmp_path, names)
    for name in reversed(names):
        run.write(name, _reply(name))
    out = _ok(run.merge(names, names))
    assert out == {"accepted": names, "rejected": [], "malformed_ratio": 0, "over_budget": False}
    merged = run.merged()
    assert merged["unread"] == []
    assert [record["skill_name"] for record in merged["summaries"]] == names
    assert merged["summaries"][0] == {
        "skill_name": "zod", "language": "TypeScript", "exports": ["zod(x): Y"],
        "protocols_inferred": ["HTTP"], "data_formats_inferred": ["JSON"], "capabilities": ["zod things"],
        "inventory_exports": ["zodFn"], "exports_documented": 1}
    # Written in place, with no temporary file left beside it.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["skill-inventory.json", "skill-summaries.json", "summaries"]


@pytest.mark.parametrize("reply, needle", [
    pytest.param(None, "no reply", id="no-file"),
    pytest.param("{not json", "not JSON", id="not-json"),
    pytest.param(b'{"skill_name": "bad", "exports": [], "capabilities": ["\xe9"]}', "cannot read the reply",
                 id="not-utf8"),
    pytest.param(json.dumps(["zod"]), "not a JSON object", id="not-an-object"),
    pytest.param(_reply("bad", capabilities=_DROP), "missing key capabilities", id="no-capabilities"),
    pytest.param(_reply("bad", exports=_DROP), "missing key exports", id="no-exports"),
    pytest.param(_reply("bad", skill_name=_DROP), "missing key skill_name", id="no-skill-name"),
    pytest.param(_reply("bad", skill_name=" "), "skill_name must be a non-empty string", id="blank-skill-name"),
    pytest.param(_reply("bad", exports="zod()"), "exports must be a list of strings", id="exports-not-a-list"),
    pytest.param(_reply("bad", capabilities=["ok", 3]), "capabilities must be a list of strings",
                 id="capability-not-text"),
    pytest.param(_reply("bad", protocols_inferred="HTTP"), "protocols_inferred must be a list of strings",
                 id="protocols-not-a-list"),
    pytest.param(_reply("bad", data_formats_inferred=None), "data_formats_inferred must be a list of strings",
                 id="formats-null"),
])
def test_a_bad_reply_is_rejected_with_its_reason(tmp_path, reply, needle):
    run = Run(tmp_path, ["zod", "bad"])
    run.write("zod", _reply("zod"))
    if reply is not None:
        run.write("bad", reply)
    out = _ok(run.merge(["zod", "bad"], ["zod", "bad"]))
    assert out["accepted"] == ["zod"]
    [rejected] = out["rejected"]
    assert rejected["skill"] == "bad" and needle in rejected["reason"], rejected
    if reply is None:
        assert rejected["reason"] == "no reply"
    merged = run.merged()
    assert merged["unread"] == ["bad"]
    assert [record["skill_name"] for record in merged["summaries"]] == ["zod"]


def test_a_reply_names_each_problem_it_has():
    fields, reason = mod.check_reply({"skill_name": "x", "exports": 1})
    assert fields is None
    assert reason == "exports must be a list of strings; missing key capabilities"


def test_the_inventory_language_replaces_the_replys(tmp_path):
    run = Run(tmp_path, ["zod"])
    run.write("zod", _reply("zod", language="Python"))
    _ok(run.merge(["zod"], ["zod"]))
    [record] = run.merged()["summaries"]
    assert record["language"] == "TypeScript"


def test_a_reply_without_language_or_optional_lists_is_accepted(tmp_path):
    stack = _inventory_entry("stack", language=["TypeScript", "Rust"], exports=[], documented=0)
    run = Run(tmp_path, ["stack"], stack=stack)
    run.write("stack", {"skill_name": "Stack Skill", "exports": [], "capabilities": [], "summary": "dropped"})
    out = _ok(run.merge(["stack"]))
    assert out["accepted"] == ["stack"]
    [record] = run.merged()["summaries"]
    # The record is named for its file's inventory name, keeps no other key, and
    # takes the inventory's list language for a stack.
    assert record == {"skill_name": "stack", "language": ["TypeScript", "Rust"], "exports": [],
                      "protocols_inferred": [], "data_formats_inferred": [], "capabilities": [],
                      "inventory_exports": [], "exports_documented": 0}


def test_a_reply_with_a_byte_order_mark_is_read(tmp_path):
    run = Run(tmp_path, ["zod"])
    run.write("zod", b"\xef\xbb\xbf" + json.dumps(_reply("zod", capabilities=["état"])).encode("utf-8"))
    out = _ok(run.merge(["zod"], ["zod"]))
    assert out["accepted"] == ["zod"]
    assert run.merged()["summaries"][0]["capabilities"] == ["état"]


@pytest.mark.parametrize("rejected_count, ratio, over", [(0, 0, False), (1, 0.2, False), (2, 0.4, True)])
def test_the_budget_edge_over_five_subagent_reads(tmp_path, rejected_count, ratio, over):
    names = [f"s{i}" for i in range(5)]
    run = Run(tmp_path, names)
    for i, name in enumerate(names):
        run.write(name, _reply(name) if i >= rejected_count else "{")
    out = _ok(run.merge(names, names))
    assert len(out["rejected"]) == rejected_count
    assert out["malformed_ratio"] == ratio and out["over_budget"] is over


def test_only_the_subagent_reads_count_toward_the_budget(tmp_path):
    names = ["a", "b", "c"]
    run = Run(tmp_path, names)
    run.write("c", _reply("c"))
    # a and b have no reply; only c was a subagent's, and it is fine.
    out = _ok(run.merge(names, ["c"]))
    assert [r["skill"] for r in out["rejected"]] == ["a", "b"]
    assert (out["malformed_ratio"], out["over_budget"]) == (0, False)


def test_the_fallback_never_goes_over_the_budget(tmp_path):
    run = Run(tmp_path, ["a", "b"])
    run.write("a", _reply("a"))
    out = _ok(run.merge(["a", "b"]))
    assert [r["skill"] for r in out["rejected"]] == ["b"]
    assert (out["malformed_ratio"], out["over_budget"]) == (0, False)
    assert run.merged()["unread"] == ["b"]


def test_a_re_read_that_recovers_the_skill_is_accepted_on_the_second_merge(tmp_path):
    names = ["a", "b", "c"]
    run = Run(tmp_path, names)
    run.write("a", _reply("a"))
    run.write("b", _reply("b", capabilities=_DROP))
    run.write("c", _reply("c"))
    first = _ok(run.merge(names, names))
    assert [r["skill"] for r in first["rejected"]] == ["b"] and first["over_budget"] is True
    # The parent's re-read overwrites the file; the same merge then accepts it.
    run.write("b", _reply("b"))
    second = _ok(run.merge(names, names))
    assert second == {"accepted": names, "rejected": [], "malformed_ratio": 0, "over_budget": False}
    assert run.merged()["unread"] == []


def test_a_re_read_that_fails_within_the_budget_leaves_the_skill_unread(tmp_path):
    names = [f"s{i}" for i in range(6)]
    run = Run(tmp_path, names)
    for name in names[1:]:
        run.write(name, _reply(name))
    first = _ok(run.merge(names, names))
    assert first["rejected"] == [{"skill": "s0", "reason": "no reply"}]
    # A re-read that cannot open the SKILL.md leaves the file as it was, so the
    # same merge rejects the skill again, now within the budget.
    out = _ok(run.merge(names, names))
    assert out == first
    assert (out["malformed_ratio"], out["over_budget"]) == (round(1 / 6, 4), False)
    assert run.merged()["unread"] == ["s0"]


@pytest.mark.parametrize("skills, subagent_skills, needle", [
    pytest.param(["zod", "ghost"], None, "--skills names ghost", id="skill-not-in-inventory"),
    pytest.param(["zod"], ["zod", "next"], "--subagent-skills names next", id="subagent-outside-skills"),
])
def test_a_bad_call_exits_2_and_writes_nothing(tmp_path, skills, subagent_skills, needle):
    run = Run(tmp_path, ["zod", "next"])
    run.write("zod", _reply("zod"))
    proc = run.merge(skills, subagent_skills)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert out["code"] == "INVALID_INPUT" and needle in out["error"], out
    assert not run.output.exists()


@pytest.mark.parametrize("inventory, needle", [
    pytest.param(None, "cannot read the inventory", id="missing"),
    pytest.param(b"{not json", "is not JSON", id="not-json"),
    pytest.param(b'{"warnings": []}', "no `skills` list", id="no-skills-list"),
    pytest.param(b'[{"name": "zod"}]', "no `skills` list", id="not-an-object"),
])
def test_an_unusable_inventory_exits_1_and_writes_nothing(tmp_path, inventory, needle):
    run = Run(tmp_path, ["zod"])
    run.write("zod", _reply("zod"))
    if inventory is None:
        run.inventory.unlink()
    else:
        run.inventory.write_bytes(inventory)
    proc = run.merge(["zod"], ["zod"])
    assert proc.returncode == 1, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert out["code"] == "UNUSABLE_INPUT" and needle in out["error"], out
    assert not run.output.exists()


def test_an_output_that_cannot_be_written_exits_3(tmp_path):
    # A write failure has its own exit, which the stage halts on as write-failed, not resolution-failure.
    run = Run(tmp_path, ["zod"])
    run.write("zod", _reply("zod"))
    proc = run.merge(["zod"], ["zod"], output=tmp_path / "missing" / "skill-summaries.json")
    assert proc.returncode == 3, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert out["code"] == "WRITE_FAILED" and "cannot write" in out["error"]
    assert not (tmp_path / "missing").exists()


def test_a_run_that_reads_no_skill_writes_empty_lists(tmp_path):
    run = Run(tmp_path, ["zod"])
    out = _ok(run.merge([]))
    assert out == {"accepted": [], "rejected": [], "malformed_ratio": 0, "over_budget": False}
    assert run.merged() == {"summaries": [], "unread": []}


def test_the_names_are_trimmed_and_counted_once(tmp_path):
    run = Run(tmp_path, ["zod", "next"])
    run.write("zod", _reply("zod"))
    run.write("next", _reply("next"))
    args = [sys.executable, str(SCRIPT_PATH), "merge", "--dir", str(run.dir), "--inventory", str(run.inventory),
            "--skills", " zod, next,,zod ", "--subagent-skills", "zod ,zod", "-o", str(run.output)]
    out = _ok(subprocess.run(args, capture_output=True, text=True, encoding="utf-8", check=False))
    assert out["accepted"] == ["zod", "next"]
    assert [r["skill_name"] for r in run.merged()["summaries"]] == ["zod", "next"]


def test_help_names_the_contract_under_a_cp1252_console():
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    proc = subprocess.run([sys.executable, str(SCRIPT_PATH), "--help"], capture_output=True, env=env, check=False)
    assert proc.returncode == 0, proc.stderr
    text = proc.stdout.decode("utf-8")
    for needle in ("merge --dir", "--subagent-skills", "over_budget", "inventory_exports", "unread"):
        assert needle in text, needle
    sub = subprocess.run([sys.executable, str(SCRIPT_PATH), "merge", "--help"], capture_output=True, env=env,
                         check=False)
    assert sub.returncode == 0 and b"--inventory" in sub.stdout


def test_a_missing_subcommand_is_a_usage_error():
    proc = subprocess.run([sys.executable, str(SCRIPT_PATH)], capture_output=True, text=True, check=False)
    assert proc.returncode == 2 and proc.stdout == ""


# --- The stage text ---------------------------------------------------------------


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    at = text.index(start)
    return text[at:text.index(end, at + len(start))]


def _surfaces() -> str:
    return _section(_read(REFERENCES / "integrations.md"), "### 3. Load Skill API Surfaces", "### 4.")


MERGE = ('uv run {skillSummariesScript} merge --dir "{run_dir}/summaries" --inventory "{inventoryFile}" '
         '--skills "<every name>" --subagent-skills "<names>" -o "{run_dir}/skill-summaries.json"')
RECORD = 'uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning '
RATIONALE = '"API surface unreadable: re-run [VS]"'
HALT_7 = ('HALT (exit code 7, `halt_reason: "inventory-unreliable"`) at phase `integrations:api-surfaces` with '
          '"API-surface reads failed for more than 20% of the skills; the skills themselves may be fine: re-run [VS]."')


def test_the_stage_names_the_helper_in_its_frontmatter():
    frontmatter = _read(REFERENCES / "integrations.md").split("\n---\n", 1)[0]
    assert "skillSummariesScript: 'scripts/skf-skill-summaries.py'" in frontmatter


def test_each_read_writes_its_own_summary_file_without_language():
    surfaces = _surfaces()
    assert "Create the folder `{run_dir}/summaries/` first." in surfaces
    assert "`{run_dir}/summaries/<skill>.json` named for the skill as `{inventoryFile}` names it" in surfaces
    assert "replies with nothing else" in surfaces
    block = re.search(r"```json\n(.*?)\n```", surfaces, re.S).group(1)
    assert sorted(json.loads(block)) == ["capabilities", "data_formats_inferred", "exports", "protocols_inferred",
                                         "skill_name"]
    assert "`language`" not in _section(surfaces, "**Extraction rules for subagents:**", "**When subagents")


def test_the_stage_merges_then_re_reads_before_the_budget_check():
    surfaces = _surfaces()
    assert MERGE in surfaces
    merge_at = surfaces.index(MERGE)
    reread_at = surfaces.index("**Re-read each rejected skill once.**")
    budget_at = surfaces.index("**If `over_budget` is true**")
    unreadable_at = surfaces.index("**A skill still rejected is unreadable.**")
    midrun_at = surfaces.index("**Mid-run change check.**")
    assert merge_at < reread_at < budget_at < unreadable_at < midrun_at
    reread = _section(surfaces, "**Re-read each rejected skill once.**", "**If `over_budget`")
    assert "run the same merge again and read only that second result" in reread
    assert "leaves its file as it was" in reread
    assert "the fallback leaves out `--subagent-skills`" in surfaces


def _stage_merge_argv(run, names, subagent_names):
    """The stage's merge call, split as a shell splits it, with its placeholders filled."""
    words = shlex.split(MERGE)[3:]
    if subagent_names is None:
        at = words.index("--subagent-skills")
        del words[at:at + 2]
    fill = {"<every name>": names, "<names>": subagent_names, "{inventoryFile}": str(run.inventory)}
    return [fill[word] if word in fill else word.replace("{run_dir}", str(run.root)) for word in words]


@pytest.mark.parametrize("subagent_names", ["", None], ids=["subagents", "fallback"])
def test_the_stage_merge_call_runs_with_no_skill_to_read(tmp_path, subagent_names):
    # A zero-coverage run still reaches the merge; each quoted list stays one argument.
    run = Run(tmp_path, ["zod"])
    assert MERGE in _surfaces()
    argv = _stage_merge_argv(run, "", subagent_names)
    proc = subprocess.run([sys.executable, str(SCRIPT_PATH), *argv], capture_output=True, text=True,
                          encoding="utf-8", check=False)
    assert _ok(proc) == {"accepted": [], "rejected": [], "malformed_ratio": 0, "over_budget": False}
    assert run.merged() == {"summaries": [], "unread": []}


def test_the_merge_failures_have_their_exits():
    merge = _section(_surfaces(), "**Merge the summaries.**", "**Re-read each rejected skill once.**")
    assert "When it exits 2, its JSON `error` names a skill the call should not hold" in merge
    assert ('When it exits 1 or prints no JSON, HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase '
            '`integrations:api-surfaces`') in merge
    assert ('When it exits 3, it could not write `{run_dir}/skill-summaries.json`: HALT (exit code 4, '
            '`halt_reason: "write-failed"`) at phase `integrations:api-surfaces`') in merge
    assert "3  -o cannot be written (code WRITE_FAILED)" in mod.__doc__
    row = next(line for line in _read(REFERENCES / "exit-codes.md").splitlines() if line.startswith("| 4 "))
    assert "step 3 §3 (the API-surface merge cannot write `{run_dir}/skill-summaries.json`)" in row


def test_the_budget_halt_names_a_read_failure():
    surfaces = _surfaces()
    assert HALT_7 in surfaces
    assert "API-surface extraction unreliable" not in surfaces and "after skills stabilize" not in surfaces
    row = [line for line in _read(REFERENCES / "exit-codes.md").splitlines() if line.startswith("| 7 ")]
    assert len(row) == 1
    assert ("step 3 §3 (API-surface reads failed for more than 20% of the skills a subagent read, each re-read "
            "once first; the skills themselves may be fine)") in row[0]
    assert "malformed JSON" not in row[0]


def test_an_unreadable_skill_gets_risky_rows_and_one_warning():
    unreadable = _section(_surfaces(), "**A skill still rejected is unreadable.**", "**Mid-run change check.**")
    assert f"carries the verdict `Risky` and the rationale {RATIONALE}" in unreadable
    assert "in every table and in `verdict-rows.json`" in unreadable
    assert RECORD + "'skill_summary_unreadable: <skill>'" in unreadable
    assert "each such skill is recorded once in the run sink" in unreadable
    assert "the requirements stage names the skill as not read" in unreadable
    # A skill also changed mid-run keeps the mid-run rationale; both warnings are recorded.
    assert "takes that check's rationale instead; record both warnings" in unreadable
    midrun = _section(_surfaces(), "**Mid-run change check.**", "The recheck's `new_skills`")
    assert 'the rationale "skill modified mid-run: re-run [VS]"' in midrun


def test_synthesize_recommends_a_re_run_for_each_unreadable_pair():
    risky = _section(_read(REFERENCES / "synthesize.md"), "**Risky integration (from Step 03):**",
                     "**Plausible integration")
    lines = risky.splitlines()
    midrun = next(i for i, line in enumerate(lines) if "If a skill changed mid-run" in line)
    assert lines[midrun + 1] == (
        "- If a skill's API surface could not be read (the rationale \"API surface unreadable\") → "
        "\"`{skill}`'s SKILL.md could not be read into an API summary, even on a second read, so `{lib_a}` "
        "↔ `{lib_b}` was not rated: re-run **[VS]**.\"")


def test_requirements_names_each_unread_skill():
    requirements = _read(REFERENCES / "requirements.md")
    frontmatter = requirements.split("\n---\n", 1)[0]
    assert "`summaries`" in frontmatter and "`unread`" in frontmatter
    assess = _section(requirements, "### 3. Assess Stack Coverage", "### 4.")
    assert "Work from the `summaries` step 3 wrote to `{skillSummariesFile}`" in assess
    assert "A skill its `unread` list names counts toward no verdict." in assess
    display = _section(requirements, "### 4. Display Requirements Results", "### 5.")
    assert ("**Not read:** `{skill}`: its API surface could not be read, so no requirement was checked against "
            "it: re-run **[VS]**.") in display
    assert display.index("**Coverage:") < display.index("**Not read:**")
    write = _section(requirements, "### 5. Append to Report", "### 6.")
    assert "- Include the full requirements coverage table, with its **Not read:** lines" in write


def test_the_envelope_schema_describes_the_warning():
    described = json.loads(_read(SCHEMA))["properties"]["warnings"]["description"]
    assert described.index("zero_coverage") < described.index("skill_summary_unreadable") < \
        described.index("skill_modified_mid_run")


def test_the_count_call_checks_the_staged_pairs():
    rate = _section(_read(REFERENCES / "integrations.md"), "**Count the verdicts deterministically.**", "### 5.")
    assert ('uv run {coverageTallyScript} --kind integrations --cycles "{run_dir}/cycles.json" '
            '--pairs "{run_dir}/integration-pairs.json" --stdin < "{run_dir}/verdict-rows.json"') in rate
    assert ("which names each staged pair that no row names by its two skills; a row that names a pair by a "
            "technology or an alias still counts for it") in rate
    # The section 6 render call stays as it was.
    write = _section(_read(REFERENCES / "integrations.md"), "### 6. Append to Report", "### 7.")
    assert ('uv run {coverageTallyScript} --kind integrations --render --cycles "{run_dir}/cycles.json" '
            '--stdin < "{run_dir}/verdict-rows.json"') in write


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
