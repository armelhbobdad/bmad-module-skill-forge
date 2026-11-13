"""Create Skill loads no text a run never acts on (#1148).

- SKILL.md keeps a pointer line where the Invocation Contract table was: the five rows live in
  `references/invocation-contract.md`, which only headless callers read, and SKILL.md stays inside its
  3,000-token budget. Its Overview points at the Gates row instead of re-listing every stop.
- The three stages every run chains through (CCC discovery, temporal and doc enrichment) sit in
  `references/` beside the others: no `references/sub/` folder, no frontmatter value that climbs a folder.
- At each cited site a stage keeps the command, its inputs, the fields the next move reads and the action
  per outcome. The helper internals, the author notes and the gate catalog are gone; the guard phrases below
  are each one of them.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
CS = REPO / "src" / "skf-create-skill"
REFS = CS / "references"
SKILL = CS / "SKILL.md"
CONTRACT = REFS / "invocation-contract.md"
VALIDATOR = REPO / "src" / "shared" / "scripts" / "skf-validate-brief-schema.py"
ENVELOPE_SCHEMA = REPO / "src" / "shared" / "scripts" / "schemas" / "skf-create-skill-result-envelope.v1.json"

POINTER = ("Headless callers and pipelines: the inputs, gates, outputs, exit codes and the "
           "`SKF_CREATE_SKILL_RESULT_JSON` and batch reading rules live in `references/invocation-contract.md`. "
           "Interactive runs do not need it.")
CONTRACT_ROWS = ("Inputs", "Gates", "Outputs", "Headless", "Exit codes")
# SKILL.md's budget is 3,000 tokens; at about four characters a token that is 12,000 characters.
SKILL_MD_MAX_CHARS = 12_000
# The run's main chain, from step 1 to step 4 (step 3d is a branch extract §2c loads in place of §4 to §4c).
RUN_CHAIN = ("load-brief.md", "ccc-discover.md", "extract.md", "fetch-temporal.md", "fetch-docs.md", "enrich.md")

# Each phrase is the narration, author note or restated rule a site lost; none is left in its file.
CUT_TEXT = {
    "references/compile.md": ("147 ≠ 59", "owns all the arithmetic (", "provably sum"),
    "references/validate.md": ("Do not assume availability", "five weighted categories", "two AI judges",
                               "The helper re-bins"),
    "references/generate-artifacts.md": ("bare-rm pattern", "rename-over-symlink", "conceptual interface",
                                         "ccc gitignores its index only"),
    "references/remote-source-access.md": ("Brief-specific `include_patterns`",),
    "references/load-brief.md": ("The helper emits:", "Field reference (for human readers)",
                                 "A failed prerequisite check"),
    "references/report.md": ("stamps the timestamp",),
    "references/batch-mode.md": ("`fail_fast_triggered`",),
    "references/step-auto-shard.md": ("The script counts the body",),
    "references/fetch-temporal.md": ("only BM25", "poisons subsequent cache-hit checks"),
    "references/ccc-discover.md": ("the daemon already has loaded", "the daemon finishes the pass"),
    "references/source-resolution-protocols.md": ("- **Exact match:**", "With package scope"),
    "references/entry-points-by-hand.md": ("Multi-entry packages", "authoritative source for `metadata.json`"),
    "references/fetch-docs.md": ("`xargs -P 4`", "the `xargs` pattern", "in a single message", "Language-Guide carve-out",
                                 "behaves exactly as before"),
    "assets/skill-sections.md": ("does not restate",),
    "assets/compile-assembly-rules.md": ("Authors should not rely", "conciseness scorers", "not re-taught"),
    "references/assembly-whole-language.md": ("tracked separately", "all fail the gate"),
    "references/component-extraction.md": ("needs no special handling", "rather than `[P]` because"),
    "references/authoritative-files-protocol.md": ("Skip this protocol entirely", "Skip it too when"),
}
# The gates a decision row may come from: the sink lists them, so compile §7 names none.
GATE_NAMES = ("tier-override", "tag-choice", "review-gate", "zero-exports", "component-extraction gates",
              "manual-carry-forward", "deferred authoritative files")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin:text.index(end, begin + len(start))]


def _frontmatter(path: Path) -> dict:
    text = _read(path)
    if not text.startswith("---\n"):
        return {}
    return yaml.safe_load(text[4:text.index("\n---\n", 4)]) or {}


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for item in value.values() for s in _strings(item)]
    if isinstance(value, list):
        return [s for item in value for s in _strings(item)]
    return []


def test_skill_md_points_at_the_lifted_contract():
    skill = _read(SKILL)
    assert not [line for line in skill.splitlines() if line.startswith("| **")], "a contract row is left in SKILL.md"
    contract_section = _section(skill, "## Invocation Contract\n", "\n## ")
    assert contract_section.split("\n", 1)[1].strip() == POINTER
    contract = _read(CONTRACT)
    assert contract.startswith("# Invocation Contract\n\nThe inputs, gates, outputs, exit codes and result-reading "
                               "rules of `skf-create-skill`, for headless callers and pipelines. Interactive runs "
                               "do not need this file.\n")
    rows = [line for line in contract.splitlines() if line.startswith("| **")]
    assert [re.match(r"\| \*\*([^*]+)\*\* \|", row).group(1) for row in rows] == list(CONTRACT_ROWS)
    assert len(skill) < SKILL_MD_MAX_CHARS, len(skill)


def test_overview_names_the_gates_row_and_no_step():
    overview = _section(_read(SKILL), "## Overview\n", "\n## ")
    assert "the Gates row of `references/invocation-contract.md` lists every stop" in overview
    assert not re.search(r"\b(step|steps) \d", overview, re.I), overview
    for fact in ("an agentskills.io-compliant SKILL.md with its provenance map, evidence report and `references/`",
                 "The run is mostly autonomous", "(Quick, Forge, Forge+ or Deep)", "A single run is not resumable"):
        assert fact in overview, fact
    assert "Tessl" not in overview and "provenance citation" not in overview


def test_every_stage_sits_in_references():
    assert not (REFS / "sub").exists()
    for path in sorted(CS.rglob("*.md")):
        text = _read(path)
        assert "references/sub" not in text, path.relative_to(REPO)
        for value in _strings(_frontmatter(path)):
            assert not value.startswith(("../", "sub/")), (path.relative_to(REPO), value)
    stages = re.findall(r"^\| \w+ \| [^|]+ \| (references/[\w/.-]+\.md) \| [^|]+ \|$", _read(SKILL), re.M)
    assert len(stages) >= 15
    for rel in stages:
        assert (CS / rel).is_file(), rel
        assert rel.count("/") == 1, rel


def test_the_run_chain_stays_in_references():
    """load-brief, ccc-discover, extract, fetch-temporal, fetch-docs, enrich: each `nextStepFile` a file name."""
    chain = [RUN_CHAIN[0]]
    while len(chain) < len(RUN_CHAIN):
        following = _frontmatter(REFS / chain[-1])["nextStepFile"]
        assert "/" not in following, (chain[-1], following)
        chain.append(following)
    assert tuple(chain) == RUN_CHAIN
    assert all((REFS / name).is_file() for name in chain)


@pytest.mark.parametrize("rel, phrase", [(rel, phrase) for rel, phrases in CUT_TEXT.items() for phrase in phrases])
def test_cut_text_is_gone(rel, phrase):
    assert phrase not in _read(CS / rel), (rel, phrase)


def test_compile_7_renders_the_sink_and_names_no_gate():
    seven = _section(_read(REFS / "compile.md"), "### 7. Build evidence-report.md Content", "### 8.")
    auto = _section(seven, "**Auto-Decisions section (render from the run sink):**", "\n")
    assert "one row per line of the sink, in file order" in auto
    for gate in GATE_NAMES:
        assert gate not in auto, gate


@pytest.mark.parametrize("body, reason", [("name: demo\n", "brief-invalid"), ("name: [unclosed\n", "brief-malformed")])
def test_an_invalid_brief_halts_on_the_fields_the_validator_prints(tmp_path, body, reason):
    """load-brief §3 reads `valid`, `halt_reason` and the first error's `message` from the validator's JSON
    without reprinting it: HARD HALT exit 2 with that reason, the message shown verbatim."""
    brief = tmp_path / "skill-brief.yaml"
    brief.write_bytes(body.encode("utf-8"))
    run = subprocess.run([sys.executable, str(VALIDATOR), str(brief)], capture_output=True, text=True,
                         encoding="utf-8", timeout=60)
    out = json.loads(run.stdout)
    assert out["valid"] is False and out["halt_reason"] == reason and out["errors"][0]["message"]
    exit_codes = json.loads(_read(ENVELOPE_SCHEMA))["$defs"]["skf-envelope"]["const"]["exit_codes"]
    assert exit_codes[reason] == 2
    three = _section(_read(REFS / "load-brief.md"), "### 3. Validate Brief Structure", "### 4.")
    assert ("**If `valid` is false:** **HARD HALT** (exit code 2, `{halt_reason}`, phase `load-brief`), with the "
            "helper's `halt_reason` and the first error's `message` as the halt message, and display that "
            "`message` verbatim") in three
    assert "Run the schema validator:\n\n```bash\nuv run {validateBriefSchemaHelper} \"{brief_path}\"\n```" in three
    assert "```json" not in three


def test_an_old_qmd_skips_a_fresh_embed_and_logs_it():
    """A qmd without `--collection` reads the collection's freshness first and skips the embed when it is fresh."""
    temporal = _section(_read(REFS / "fetch-temporal.md"), "**Scope the embed:**", "\n")
    assert ("If the installed `qmd` CLI does not accept `--collection`, before the block above run `uv run "
            "{forgeTierRwHelper} read --target \"{forgeTierConfig}\" --fresh-within-hours 24 --name "
            "\"{skill-name}-temporal\"`, and when its `fresh` is true skip the embed and log the skip in the "
            "evidence report.") in temporal
    rollback = _section(_read(REFS / "fetch-temporal.md"), "**Rollback rule:**", "\n")
    assert "warn in the evidence report and register nothing below" in rollback
    generate = _read(REFS / "generate-artifacts.md")
    assert ("Scope the embed to this collection: an unscoped `qmd embed` re-embeds every collection. If the installed "
            "qmd CLI lacks `--collection`, before the block above run `uv run {forgeTierRwHelper} read --target "
            "\"{forgeTierConfig}\" --fresh-within-hours 24 --name {name}-extraction`, skip the embed when its "
            "`fresh` is true, and warn in evidence-report.") in generate


def test_the_workspace_clone_is_cleaned_after_a_failed_index():
    clean = _section(_read(REFS / "remote-source-access.md"), "**Leave the workspace clone clean:**", "\n")
    for token in ('run `uv run {cccGitHygieneHelper} workspace --repo "{remote_clone_path}"` from `{project-root}`',
                  "after step 5 or step 6, and also when step 1 or step 2 set `{ccc_discovery: []}`",
                  "a `ccc init` or `ccc index`, a failed one too, may have edited the clone's tracked `.gitignore`",
                  "if neither path exists or the command fails, continue"):
        assert token in clean, token
