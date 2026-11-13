#!/usr/bin/env python3
"""Each workflow's Invocation Contract lists what its activation parses (#594).

A pipeline author reads a workflow's flags and inputs from its Invocation
Contract (the table in SKILL.md, or in references/invocation-contract.md
where a headless contract moved out of SKILL.md). A flag the table lists
that activation never reads does nothing, and a flag activation reads that
the table leaves out is one no caller learns about. So, for the 15
workflows:

- every flag in a flag row (Flags, Inputs, Headless inputs, Headless flag,
  Overrides: the rows tools/covered-surfaces.js reads) is parsed at
  activation: On Activation names the flag or binds its variable, or the
  first stage does (stage 1 and its lettered sub-stages, `0` for campaign),
  which is where an init step binds what the invocation passed;
- every flag On Activation parses is in the contract, apart from the shared
  `--headless` / `-H` pair, which src/shared/references/headless-gate-convention.md
  defines for every workflow, the customization helper's own flags (the
  step names `--facts` when it says what the resolved list holds), and the
  KNOWN_UNLISTED flags below;
- every input an Inputs row names with a `[required]` or `[optional]` marker
  is bound at activation, by its name or its flag.

skf-forger is the agent, not a workflow: it dispatches to these contracts.

Export Skill's `--version` (#1172) is followed from its contract rows to the
step that moves the `active` link, since a contract flag that step 3 never
acts on would make no version active.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
WORKFLOWS = sorted(d.name for d in SRC.iterdir()
                   if d.is_dir() and d.name.startswith("skf-") and d.name != "skf-forger")
CONVENTION = SRC / "shared" / "references" / "headless-gate-convention.md"

# The flags every workflow takes, defined once by the headless gate convention.
SHARED_FLAGS = {"--headless", "-H"}

# Flags activation parses that no contract row lists yet. Listing one in a
# flag row makes it a covered flag (docs/_internal/STABILITY.md), which takes
# an `added` change fragment, so each waits for the pull request that ships
# that fragment; until then this list keeps them visible.
KNOWN_UNLISTED = {
    "skf-campaign": {"--brief", "--manifest"},
    "skf-create-stack-skill": {"--no-headless"},
}

# tools/covered-surfaces.js: a flag that opens a backticked span, or a long
# flag written outside one, in one of these rows.
FLAG_ROW_RE = re.compile(r"^\|\s*\*\*(Flags|Inputs|Headless inputs|Headless flag|Overrides)\*\*\s*\|")
FLAG_IN_BACKTICKS_RE = re.compile(r"`((--[a-z][a-z0-9-]*|-[A-Za-z])(?![\w-])[^`]*)`")
BARE_LONG_FLAG_RE = re.compile(r"(?<![\w`-])(--[a-z][a-z0-9-]*)(?![\w-])")
LONG_FLAG_RE = re.compile(r"(?<![\w-])(--[a-z][a-z0-9-]*)(?![\w-])")
SHORT_FLAG_SPAN_RE = re.compile(r"^(-[A-Za-z])(?![\w-])")
# A backticked span that runs a program: its flags are that program's.
COMMAND_RE = re.compile(
    r"^\s*(?:(?:uv|uvx|python3?|py|node|npx|git|gh|bash|sh|curl|mkdir|rm|printf|mktemp|ccc|qmd)(?=\s|$)"
    r"|\{\w+(?:Helper|Script)\}|<runner>|<helper>|<preflight>)"
)
# A flag handed a {variable}, or an argument the prose says it passes to a helper.
PASSED_FLAG_RE = re.compile(r"(--[a-z][a-z0-9-]*)(?:\s+|=)[\"']?\{")
HELPER_ARG_RE = re.compile(r"passes it to `[^`]+` as `(--[a-z][a-z0-9-]*)`")
# The customization helper's call in its fence: the step's prose names its flags (`--facts`, #1106) when it says
# what the resolved list holds, and they are the helper's, not the workflow's.
RESOLVER_CALL_RE = re.compile(r"^\s*uv run \{resolveCustomizationHelper\}(.*)$", re.MULTILINE)
NAMED_INPUT_RE = re.compile(r"`?\b([a-z][a-z0-9_]*)\b`?(?: \([^)]*\))? \[(?:required|optional|one or more)")
FENCE_RE = re.compile(r"^[ \t]*```.*?^[ \t]*```", re.MULTILINE | re.DOTALL)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _skill_md(workflow: str) -> str:
    return _read(SRC / workflow / "SKILL.md")


def _contract_files(workflow: str) -> list[Path]:
    files = [SRC / workflow / "SKILL.md"]
    lifted = SRC / workflow / "references" / "invocation-contract.md"
    return files + [lifted] if lifted.is_file() else files


def _flag_rows(workflow: str) -> list[str]:
    return [line for path in _contract_files(workflow) for line in _read(path).splitlines()
            if FLAG_ROW_RE.match(line)]


def _row_flags(row: str) -> set[str]:
    flags = {m.group(2) for m in FLAG_IN_BACKTICKS_RE.finditer(row)}
    outside = re.sub(r"`[^`]*`", lambda m: " " * len(m.group(0)), row)
    return flags | {m.group(1) for m in BARE_LONG_FLAG_RE.finditer(outside)}


def _contract_flags(workflow: str) -> set[str]:
    return set().union(*(_row_flags(row) for row in _flag_rows(workflow)))


def _contract_mentions(workflow: str) -> set[str]:
    """Every flag a contract row names, a flag inside a longer span included
    (`campaign resume [--from=<skill>]`)."""
    rows = "\n".join(_flag_rows(workflow))
    return set(LONG_FLAG_RE.findall(rows)) | _contract_flags(workflow)


def _on_activation(workflow: str) -> str:
    return _skill_md(workflow).split("## On Activation", 1)[1].split("\n## ", 1)[0]


def _first_stage_files(workflow: str) -> list[Path]:
    """The files of the first stage and its lettered sub-stages (1, 1a, 1h, ...)."""
    stages = re.search(r"^## Stages\b(.*?)(?=^## )", _skill_md(workflow), re.MULTILINE | re.DOTALL).group(1)
    rows = re.findall(r"^\|\s*(\d+)([a-z]?)\s*\|[^|]*\|\s*(references/[\w./-]+\.md)\s*\|", stages, re.MULTILINE)
    first = rows[0][0]
    return [SRC / workflow / path for number, _, path in rows if number == first]


def _activation_text(workflow: str) -> str:
    return "\n".join([_on_activation(workflow), *(_read(p) for p in _first_stage_files(workflow))])


def _variable(flag: str) -> str:
    return "{" + flag.lstrip("-").replace("-", "_") + "}"


def _parsed_at_activation(workflow: str, flag: str) -> bool:
    text = _activation_text(workflow)
    return bool(re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", text)) or _variable(flag) in text


def _activation_flags(workflow: str) -> set[str]:
    """The flags On Activation parses: every flag it names outside a code
    block, a command span, an argument handed a {variable}, an argument it
    says it passes to a helper, a flag its customization helper call passes,
    and a blockquote, which states how the run calls a helper (setup's halt
    contract and its emitter arguments)."""
    resolver_args = {flag for call in RESOLVER_CALL_RE.findall(_on_activation(workflow))
                     for flag in LONG_FLAG_RE.findall(call)}
    text = FENCE_RE.sub("", _on_activation(workflow))
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))
    helper_args = set(HELPER_ARG_RE.findall(text)) | resolver_args
    found: set[str] = set()

    def span(match: re.Match) -> str:
        body = match.group(1)
        if COMMAND_RE.match(body) or re.search(r"\{\w+(?:Helper|Script)\}", body):
            return " "
        passed = set(PASSED_FLAG_RE.findall(body))
        found.update(flag for flag in LONG_FLAG_RE.findall(body) if flag not in passed)
        short = SHORT_FLAG_SPAN_RE.match(body)
        if short:
            found.add(short.group(1))
        return " "

    rest = re.sub(r"`([^`\n]*)`", span, text)
    found.update(LONG_FLAG_RE.findall(rest))
    return found - helper_args


def test_the_fifteen_workflows_are_checked():
    assert len(WORKFLOWS) == 15, WORKFLOWS


def test_the_convention_defines_the_shared_flags():
    resolving = _read(CONVENTION).split("## Resolving `{headless_mode}`", 1)[1].split("\n## ", 1)[0]
    assert "`--headless` or `-H`" in resolving


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_every_contract_flag_is_parsed_at_activation(workflow):
    missing = sorted(flag for flag in _contract_flags(workflow) if not _parsed_at_activation(workflow, flag))
    assert not missing, (
        f"{workflow}: the Invocation Contract lists {missing}, which neither On Activation nor the first "
        f"stage ({[p.name for p in _first_stage_files(workflow)]}) parses")


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_every_flag_activation_parses_is_in_the_contract(workflow):
    listed = _contract_mentions(workflow) | SHARED_FLAGS | KNOWN_UNLISTED.get(workflow, set())
    unlisted = sorted(_activation_flags(workflow) - listed)
    assert not unlisted, f"{workflow}: On Activation parses {unlisted}, which its Invocation Contract does not list"


@pytest.mark.parametrize("workflow,flag", sorted((w, f) for w, flags in KNOWN_UNLISTED.items() for f in flags))
def test_a_known_unlisted_flag_is_still_parsed_and_still_unlisted(workflow, flag):
    """Once a pull request lists the flag (with its `added` fragment), it leaves KNOWN_UNLISTED."""
    assert flag in _activation_flags(workflow), f"{workflow}: activation no longer parses {flag}"
    assert flag not in _contract_mentions(workflow), f"{workflow}: {flag} is listed now; drop it from KNOWN_UNLISTED"


def _named_inputs(workflow: str) -> set[str]:
    rows = [row for row in _flag_rows(workflow) if row.startswith("| **Inputs** |")]
    return {name for row in rows for name in NAMED_INPUT_RE.findall(row)}


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_every_named_input_is_bound_at_activation(workflow):
    text = _activation_text(workflow)

    def bound(name: str) -> bool:
        flags = {"--" + name.replace("_", "-"), "--" + name.removesuffix("_path").replace("_", "-")}
        return re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text) is not None or any(f in text for f in flags)

    missing = sorted(name for name in _named_inputs(workflow) if not bound(name))
    assert not missing, f"{workflow}: the Inputs row names {missing}, which activation never binds"


def test_the_named_input_scan_reads_the_contracts():
    """The inputs the scan finds, so a reworded row cannot empty the check."""
    found = {w: _named_inputs(w) for w in WORKFLOWS}
    assert {"skill_name", "skill_path", "tier_override", "upstream_drift_choice"} <= found["skf-audit-skill"]
    assert {"skill_name", "mode", "version"} <= found["skf-drop-skill"]
    assert {"old_name", "new_name"} <= found["skf-rename-skill"]
    assert {"architecture_doc_path", "prd_path", "previous_report_path"} <= found["skf-verify-stack"]
    assert sum(len(v) for v in found.values()) >= 20, found


# --------------------------------------------------------------------------
# #1172: Export Skill's `--version`, from the contract to the flip
# --------------------------------------------------------------------------

EXPORT_REFS = SRC / "skf-export-skill" / "references"
ATOMIC_WRITE_PROBE_ORDER = ("atomicWriteProbeOrder:\n"
                            "  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'\n"
                            "  - '{project-root}/src/shared/scripts/skf-atomic-write.py'\n")
FLIP_CALL = ('uv run {atomicWriteHelper} flip-link --link "{skills_output_folder}/{skill-name}/active" '
             '--target "{requested_version}"')
SET_CALL = "python3 {manifestOpsHelper} {skills_output_folder} set {skill-name} {version} [--ides {ides_written}]"
DRY_RUN_ACTIVE = "**[DRY RUN] `active` would point at v{requested_version} for {skill-name}.**"


def _between(text: str, start: str, end: str) -> str:
    assert text.count(start) == 1, f"marker {start!r} must occur once"
    body = text[text.index(start):]
    assert end in body, f"marker {end!r} missing after {start!r}"
    return body[:body.index(end)]


def test_export_version_runs_from_the_contract_to_the_flip():
    """#1172: the contract lists `--version`, step 1 parses it for one skill, §2 resolves it and refuses a
    version it cannot restore, and step 3 §9b points `active` at it before `set` records it."""
    contract = _read(EXPORT_REFS / "invocation-contract.md")
    rows = {row.split("|")[1].strip(): row for row in contract.splitlines() if FLAG_ROW_RE.match(row)}
    assert "`version` [optional, `--version <v>`, one skill only]" in rows["**Inputs**"]
    flag = rows["**Flags**"][rows["**Flags**"].index("`--version <v>`"):]
    for token in ("points `{skills_output_folder}/{skill-name}/active` at it", "archives the version the manifest had active",
                  "the export manifest does not mark deprecated",
                  "refused with `--all` or with several skills, with exit code 3, `resolution-failure`"):
        assert token in flag, token
    load = _read(EXPORT_REFS / "load-skill.md")
    assert ATOMIC_WRITE_PROBE_ORDER in load.split("\n---\n", 1)[0] + "\n"
    parsing = _between(load, "**Flag Parsing:**", "**Context File Resolution:**")
    [bullet] = [line for line in parsing.splitlines() if line.startswith("- `--version` flag:")]
    assert "bind `{requested_version}` ← its value, else null" in bullet
    assert ('With `--all`, or when `len(skill_batch) > 1`, HALT (exit code 3, `halt_reason: '
            '"resolution-failure"`, phase `load-skill §1`)') in parsing
    # The flip helper is found before the skill-selection prompt, as On Activation finds every other helper
    # before any prompt (lane review finding 8).
    early = _between(load, "**Read the export manifest**", "**Skill Path Discovery")
    for token in ("**With `--version`**, resolve `{atomicWriteHelper}` ← the first existing path in "
                  "`{atomicWriteProbeOrder}` now, before the skill-selection prompt below",
                  'HALT (exit code 4, `halt_reason: "context-rebuild-failed"`, phase `load-skill §1`)'):
        assert token in early, token
    assert "{atomicWriteHelper}" not in parsing
    resolve = _between(load, "### 2. Load and Validate Skill Artifacts", "**Validation (the export gate):**")
    [call] = [line for line in resolve.splitlines() if line.startswith("uv run {skillInventoryHelper} resolve ")]
    assert call.endswith('--forge-data-folder "{forge_data_folder}" [--version {requested_version}]')
    requested = _between(resolve, "**`requested`** (a `--version` run):", "\n1. `manifest-and-link`")
    for token in ("`{replaced_version}` ← `symlink_target`, else `active_version`",
                  "`skill_package_exists` is false", '`status` `"deprecated"`',
                  "no `versions` entry of `{requested_version}` has `on_disk` true",
                  "active_version, in place of v{replaced_version}.",
                  'HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `load-skill §2`)',
                  "Versions it can restore: {restorable}", "`on_disk` is true", "else `none`"):
        assert token in requested, token
    assert "archiving" not in requested, "`set` archives the manifest's version, not always `{replaced_version}`"
    update = _read(EXPORT_REFS / "update-context.md")
    manifest = _between(update, "### 9b. Update Export Manifest", "### 9c. ")
    assert FLIP_CALL in manifest and SET_CALL in manifest
    assert manifest.index(FLIP_CALL) < manifest.index(SET_CALL), "the link moves before the manifest records it"
    assert "**With `--version`**" in manifest and "and not in a dry run" in manifest[:manifest.index(FLIP_CALL)]
    assert ('HALT (exit code 4, `halt_reason: "write-failed"`, phase `update-context §9b`) with the helper\'s '
            "error, before any `set`") in manifest
    assert "re-run `[EX] Export Skill {skill-name} --version {requested_version}`" in manifest
    dry_run = manifest[manifest.index("**Dry-run mode:**"):]
    assert "Do NOT update the manifest or move the `active` link." in dry_run and DRY_RUN_ACTIVE in dry_run
    menu = _between(update, "### 8. Present MENU OPTIONS", "**If NOT dry-run:**")
    assert "{With `--version`:} " + DRY_RUN_ACTIVE in menu
    # The exit-code map names each new halt site.
    codes = {line.split("|")[1].strip(): line for line in _read(EXPORT_REFS / "result-envelope.md").splitlines()
             if re.match(r"\| \d ", line)}
    for code, site in (("3", "`--version` comes with `--all` or with several skills"),
                       ("3", "the `--version` version has no package on disk, is not a version folder of the skill (such as "
                             "`active`) or the export manifest marks it deprecated"),
                       ("4", "step 3 §9b (with `--version`, the `active` link cannot be moved"),
                       ("4", "step 1 §1 (with `--version`, `skf-atomic-write.py` is missing)")):
        assert site in codes[code], (code, site)
    # Ferris's menu names the flag on the EX row (test-skf-parse-pipeline.py holds it equal to `SKILLS["EX"]`).
    [ex_row] = [row for row in _read(SRC / "skf-forger" / "SKILL.md").splitlines() if row.startswith("| 12 | EX |")]
    assert "; `--version` makes an earlier version active again | skf-export-skill |" in ex_row
