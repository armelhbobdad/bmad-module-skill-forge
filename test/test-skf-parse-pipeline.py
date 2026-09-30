"""Unit tests for src/skf-forger/scripts/parse-pipeline.py.

Validates the deterministic pipeline parse/expand/anti-pattern logic that
Pipeline Mode (pipeline-mode.md §1-2) delegates to instead of computing
alias expansion and sequence checks in-prompt: the whole invocation (an alias
with its arguments and --pin), bracket keywords in any case, the problems that
make a plan not runnable (a missing alias argument included), a `min:N` only
on AN and TS, and the prose that hands the parser the invocation, branches on
its answer and offers no resume for a parse halt.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import subprocess
import sys

import pytest

SCRIPT = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src"
    / "skf-forger"
    / "scripts"
    / "parse-pipeline.py"
)

spec = importlib.util.spec_from_file_location("parse_pipeline", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_simple_sequence():
    r = mod.parse_pipeline("BS CS TS EX")
    assert r["valid"] is True
    assert r["alias"] is None
    assert r["codes"] == ["BS", "CS", "TS", "EX"]
    assert r["anti_patterns"] == []


def test_arrow_separators_equivalent():
    a = mod.parse_pipeline("AN -> CS -> TS -> EX")
    b = mod.parse_pipeline("AN CS TS EX")
    assert a["codes"] == b["codes"] == ["AN", "CS", "TS", "EX"]


def test_forge_auto_expansion():
    r = mod.parse_pipeline("forge-auto https://github.com/honojs/hono")
    assert r["alias"] == "forge-auto"
    assert r["codes"] == ["AN", "BS", "CS", "TS", "EX"]
    assert r["expanded"] == ["AN[auto]", "BS[auto]", "CS", "TS[min:90]", "EX"]
    # TS[min:90] is the non-default circuit-breaker gate.
    ts = next(p for p in r["plan"] if p["code"] == "TS")
    assert ts["min"] == 90
    # [auto] classifies as a mode flag, not a target.
    an = next(p for p in r["plan"] if p["code"] == "AN")
    assert an["mode"] == "auto" and an["target"] is None
    assert r["valid"] is True
    assert r["anti_patterns"] == []


def test_all_aliases_expand():
    assert mod.parse_pipeline("forge")["codes"] == ["BS", "CS", "TS", "EX"]
    assert mod.parse_pipeline("forge-quick")["codes"] == ["QS", "TS", "EX"]
    assert mod.parse_pipeline("maintain")["codes"] == ["AS", "US", "TS", "EX"]


def test_deprecated_alias_deepwiki():
    r = mod.parse_pipeline("deepwiki")
    assert r["deprecated_alias"] == "deepwiki"
    assert r["alias"] == "forge-auto"
    assert r["codes"] == ["AN", "BS", "CS", "TS", "EX"]
    # Like forge-auto, it needs the repo or doc URL after it.
    assert r["missing_args"] == ["project_path"] and r["valid"] is False


def test_removed_alias_onboard():
    r = mod.parse_pipeline("onboard")
    assert r["removed_alias"] == "onboard"
    assert r["valid"] is False
    assert r["codes"] == []


def test_bracket_target_argument():
    r = mod.parse_pipeline("BS CS[cocoindex] TS EX")
    cs = next(p for p in r["plan"] if p["code"] == "CS")
    assert cs["target"] == "cocoindex"
    assert cs["min"] is None and cs["mode"] is None


def test_min_override_on_circuit_breaker_code():
    r = mod.parse_pipeline("CS TS[min:80] EX")
    ts = next(p for p in r["plan"] if p["code"] == "TS")
    assert ts["min"] == 80


def test_min_ignored_on_non_circuit_breaker_code():
    # EX has no circuit breaker; min:N is ignored (recorded as null).
    r = mod.parse_pipeline("BS CS TS EX[min:80]")
    ex = next(p for p in r["plan"] if p["code"] == "EX")
    assert ex["min"] is None


@pytest.mark.parametrize(
    "raw,code",
    [
        pytest.param("BS CS[min:80] TS EX", "CS", id="cs"),
        pytest.param("AS[min:3] US TS EX", "AS", id="as"),
        pytest.param("VS[min:2] RA", "VS", id="vs"),
    ],
)
def test_min_is_ignored_on_a_circuit_breaker_with_no_number(raw, code):
    """CS, AS and VS have circuit breakers, but nothing reads a min for them:
    only AN (the gate's --min) and TS (--threshold) take one."""
    r = mod.parse_pipeline(raw)
    assert next(p for p in r["plan"] if p["code"] == code)["min"] is None
    warning = next(p for p in r["anti_patterns"] if p["pattern"] == "min-ignored")
    assert warning["codes"] == [code]
    assert r["valid"] is True


def test_only_an_and_ts_take_a_min():
    assert mod.THRESHOLD_CODES == {"AN", "TS"}
    r = mod.parse_pipeline("AN[min:2] CS TS[min:85] EX")
    assert [p["min"] for p in r["plan"]] == [2, None, 85, None]
    assert not [p for p in r["anti_patterns"] if p["pattern"] == "min-ignored"]


def test_anti_pattern_ex_before_ts():
    r = mod.parse_pipeline("BS CS EX TS")
    patterns = {p["pattern"] for p in r["anti_patterns"]}
    assert "ex-before-ts" in patterns
    # anti-patterns are warnings, not invalidating.
    assert r["valid"] is True


def test_anti_pattern_duplicate_codes():
    r = mod.parse_pipeline("BS CS TS TS EX")
    dupe = next(p for p in r["anti_patterns"] if p["pattern"] == "duplicate-codes")
    assert dupe["codes"] == ["TS"]


def test_anti_pattern_cs_without_brief():
    r = mod.parse_pipeline("CS TS EX")
    patterns = {p["pattern"] for p in r["anti_patterns"]}
    assert "cs-without-brief" in patterns


def test_cs_with_an_no_anti_pattern():
    r = mod.parse_pipeline("AN CS TS EX")
    patterns = {p["pattern"] for p in r["anti_patterns"]}
    assert "cs-without-brief" not in patterns


def test_anti_pattern_us_without_audit():
    r = mod.parse_pipeline("US TS EX")
    patterns = {p["pattern"] for p in r["anti_patterns"]}
    assert "us-without-audit" in patterns


def test_unknown_code_invalidates():
    r = mod.parse_pipeline("BS ZZ EX")
    assert "ZZ" in r["unknown_codes"]
    assert r["valid"] is False


def test_empty_input():
    r = mod.parse_pipeline("")
    assert r["codes"] == []
    assert r["valid"] is False


def test_deterministic_identical_output():
    a = json.dumps(mod.parse_pipeline("forge-auto"), sort_keys=True)
    b = json.dumps(mod.parse_pipeline("forge-auto"), sort_keys=True)
    assert a == b


# --- CLI exit codes ---------------------------------------------------------


def _run(*args, stdin=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
    )


def test_cli_ok_exit_zero():
    p = _run("BS CS TS EX")
    assert p.returncode == 0
    assert json.loads(p.stdout)["codes"] == ["BS", "CS", "TS", "EX"]


def test_cli_removed_alias_exit_two():
    p = _run("onboard")
    assert p.returncode == 2
    assert json.loads(p.stdout)["removed_alias"] == "onboard"


def test_cli_unknown_exit_three():
    p = _run("ZZ")
    assert p.returncode == 3


def test_cli_no_input_exit_one():
    p = _run()
    assert p.returncode == 1


def test_cli_stdin():
    p = _run("--stdin", stdin="AN -> CS -> TS -> EX")
    assert p.returncode == 0
    assert json.loads(p.stdout)["codes"] == ["AN", "CS", "TS", "EX"]


# --- The whole invocation: an alias and its arguments ----------------------

HONO = "https://github.com/honojs/hono"
COGNEE_REPO = "https://github.com/topoteretes/cognee"


@pytest.mark.parametrize(
    "raw,alias,args",
    [
        pytest.param(f"forge-auto {HONO}", "forge-auto", {"project_path": HONO}, id="forge-auto-url"),
        pytest.param(f"forge-auto {HONO} --pin 0.2.1", "forge-auto",
                     {"project_path": HONO, "pin": "0.2.1"}, id="forge-auto-url-pin"),
        pytest.param(f"forge {COGNEE_REPO} cocoindex", "forge",
                     {"target_repo": COGNEE_REPO, "skill_name": "cocoindex"}, id="forge-repo-name"),
        pytest.param("forge-quick cognee", "forge-quick", {"target": "cognee"}, id="forge-quick-package"),
        pytest.param("maintain cocoindex", "maintain", {"skill_name": "cocoindex"}, id="maintain-skill"),
    ],
)
def test_documented_alias_invocations_parse(raw, alias, args):
    """The five invocation forms the docs and the menu show (#586)."""
    r = mod.parse_pipeline(raw)
    assert r["valid"] is True, r
    assert r["alias"] == alias
    assert r["codes"] == [p["code"] for p in mod.parse_pipeline(alias)["plan"]]
    assert r["args"] == args
    assert r["unknown_codes"] == r["unexpected_args"] == r["missing_args"] == r["malformed_brackets"] == []
    # The alias's own plan is untouched: forge-auto keeps its TS[min:90] gate.
    assert r["plan"] == mod.parse_pipeline(alias)["plan"]


def test_cli_documented_alias_invocation_exits_zero():
    p = _run(f"forge-auto {HONO} --pin 0.2.1")
    assert p.returncode == 0, p.stdout
    out = json.loads(p.stdout)
    assert out["args"] == {"project_path": HONO, "pin": "0.2.1"}


def test_typo_code_stops_before_any_workflow():
    """`TX` is not dropped from the run: the plan is not runnable (exit 3)."""
    r = mod.parse_pipeline("BS CS TX EX")
    assert r["valid"] is False
    assert r["unknown_codes"] == ["TX"]
    assert _run("BS CS TX EX").returncode == 3


def test_alias_arguments_bind_in_order_and_extras_are_unexpected():
    r = mod.parse_pipeline("forge-quick cognee extra")
    assert r["args"] == {"target": "cognee"}
    assert r["unexpected_args"] == ["extra"]
    assert r["valid"] is False
    assert _run("forge-quick cognee extra").returncode == 3


@pytest.mark.parametrize(
    "raw,missing",
    [
        pytest.param("forge-auto", ["project_path"], id="forge-auto"),
        pytest.param("forge-auto --pin 0.2.1", ["project_path"], id="forge-auto-pin-only"),
        pytest.param("forge", ["target_repo", "skill_name"], id="forge"),
        pytest.param(f"forge {COGNEE_REPO}", ["skill_name"], id="forge-without-name"),
        pytest.param("forge-quick", ["target"], id="forge-quick"),
        pytest.param("maintain", ["skill_name"], id="maintain"),
    ],
)
def test_alias_without_its_argument_is_not_runnable(raw, missing):
    """Each alias's first workflow requires the input, and a pipeline runs it
    headless: the parse reports the gap before any workflow runs (exit 3)."""
    r = mod.parse_pipeline(raw)
    assert r["missing_args"] == missing
    assert r["valid"] is False
    assert r["codes"], "the alias still expands"
    assert _run(raw).returncode == 3


def test_alias_matches_in_any_case():
    r = mod.parse_pipeline("Forge-Quick cognee")
    assert r["alias"] == "forge-quick"
    assert r["args"] == {"target": "cognee"}


def test_deprecated_alias_keeps_its_arguments():
    r = mod.parse_pipeline(f"deepwiki {HONO} --pin 0.2.1")
    assert r["deprecated_alias"] == "deepwiki"
    assert r["alias"] == "forge-auto"
    assert r["args"] == {"project_path": HONO, "pin": "0.2.1"}
    assert r["valid"] is True


def test_removed_alias_with_arguments_still_halts():
    r = mod.parse_pipeline(f"onboard {HONO}")
    assert r["removed_alias"] == "onboard"
    assert r["codes"] == [] and r["valid"] is False
    assert _run(f"onboard {HONO}").returncode == 2


def test_quoted_argument_stays_one_token():
    r = mod.parse_pipeline('forge-auto "/home/me/My Projects/hono"')
    assert r["args"] == {"project_path": "/home/me/My Projects/hono"}
    assert r["valid"] is True


def test_windows_path_keeps_its_backslashes():
    r = mod.parse_pipeline(r"forge-auto C:\Users\me\hono")
    assert r["args"] == {"project_path": r"C:\Users\me\hono"}


def test_url_fragment_is_not_a_comment():
    r = mod.parse_pipeline(f"forge-auto {HONO}#readme")
    assert r["args"] == {"project_path": f"{HONO}#readme"}


def test_every_alias_names_its_inputs():
    assert set(mod.ALIAS_INPUTS) == set(mod.ALIASES)


# --- Pipeline flags -----------------------------------------------------------


def test_pin_in_equals_form_and_on_a_code_sequence():
    assert mod.parse_pipeline(f"forge-auto {HONO} --pin=0.2.1")["args"]["pin"] == "0.2.1"
    r = mod.parse_pipeline("AN[auto] BS[auto] CS TS[min:90] EX --pin 1.4.0")
    assert r["args"] == {"pin": "1.4.0"} and r["valid"] is True


@pytest.mark.parametrize(
    "raw,unexpected",
    [
        pytest.param(f"forge-auto {HONO} --pin", ["--pin"], id="pin-without-value"),
        pytest.param(f"forge-auto {HONO} --pin=", ["--pin="], id="pin-empty"),
        pytest.param(f"forge-auto {HONO} --pin 1 --pin 2", ["--pin 2"], id="pin-twice"),
        pytest.param(f"forge-auto {HONO} --force", ["--force"], id="unknown-flag"),
    ],
)
def test_flag_problems_are_unexpected(raw, unexpected):
    r = mod.parse_pipeline(raw)
    assert r["unexpected_args"] == unexpected
    assert r["valid"] is False


@pytest.mark.parametrize("flag", ["--headless", "-H"])
def test_headless_flag_is_accepted_and_not_returned(flag):
    """Ferris reads --headless/-H at activation; the parser leaves it out."""
    r = mod.parse_pipeline(f"forge-auto {HONO} {flag}")
    assert r["args"] == {"project_path": HONO}
    assert r["valid"] is True


# --- Bracket keywords ---------------------------------------------------------


def test_bracket_keywords_match_in_any_case():
    r = mod.parse_pipeline("ts[MIN:80] EX")
    assert next(p for p in r["plan"] if p["code"] == "TS")["min"] == 80
    assert r["expanded"] == ["TS[min:80]", "EX"]
    r = mod.parse_pipeline("AN[AUTO] BS CS")
    an = next(p for p in r["plan"] if p["code"] == "AN")
    assert an["mode"] == "auto" and an["target"] is None
    assert r["expanded"][0] == "AN[auto]"


@pytest.mark.parametrize("value", ["min:80%", "min=80", "min:", "MIN", "min:-5", "Min:8.5"])
def test_malformed_min_is_reported_not_a_target(value):
    raw = f"BS CS TS[{value}] EX"
    r = mod.parse_pipeline(raw)
    assert r["malformed_brackets"] == [f"TS[{value}]"]
    ts = next(p for p in r["plan"] if p["code"] == "TS")
    assert ts["target"] is None and ts["min"] is None
    assert r["valid"] is False
    assert _run(raw).returncode == 3


def test_target_that_starts_with_min_is_a_target():
    r = mod.parse_pipeline("BS CS[minimatch] TS EX")
    cs = next(p for p in r["plan"] if p["code"] == "CS")
    assert cs["target"] == "minimatch"
    assert r["malformed_brackets"] == [] and r["valid"] is True


def test_min_on_a_code_without_circuit_breaker_warns():
    r = mod.parse_pipeline("BS CS TS EX[min:80]")
    warning = next(p for p in r["anti_patterns"] if p["pattern"] == "min-ignored")
    assert warning["codes"] == ["EX"]
    assert "EX[min:80]" in warning["message"]
    assert r["valid"] is True


def test_cli_stdin_reads_a_heredoc_invocation_as_utf8():
    """Step 1 hands the invocation over a quoted heredoc: a trailing newline,
    an arrow separator and a non-ASCII path must survive."""
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "--stdin"],
        input="forge-auto '/home/me/café hono' --pin 0.2.1\n",
        capture_output=True, text=True, encoding="utf-8",
    )
    assert p.returncode == 0, p.stdout
    out = json.loads(p.stdout)
    assert out["args"] == {"project_path": "/home/me/café hono", "pin": "0.2.1"}
    assert out["raw"] == "forge-auto '/home/me/café hono' --pin 0.2.1"
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "--stdin"],
        input="AN → CS → TS → EX\n", capture_output=True, text=True, encoding="utf-8",
    )
    assert json.loads(p.stdout)["codes"] == ["AN", "CS", "TS", "EX"]


# --- The prose hands the parser the whole invocation ---------------------------

REPO = SCRIPT.parents[3]
PIPELINE_MODE = REPO / "src" / "skf-forger" / "references" / "pipeline-mode.md"
FORGER_SKILL = REPO / "src" / "skf-forger" / "SKILL.md"
CONTRACTS = REPO / "src" / "shared" / "references" / "pipeline-contracts.md"


def _read(path):
    return path.read_text(encoding="utf-8")


def _step_1():
    text = _read(PIPELINE_MODE)
    return text[text.index("1. **Parse the invocation**"):text.index("2. **Validate the sequence**")]


def test_step_1_call_runs_as_written():
    m = re.search(r"```bash\n\s*uv run scripts/parse-pipeline\.py (.+?) <<'(\w+)'\n\s*(<[^>\n]+>)\n\s*\2\n",
                  _step_1())
    assert m, "step 1 must hand the invocation to the parser over a quoted heredoc"
    assert m.group(3) == "<the whole invocation>"
    p = subprocess.run(
        [sys.executable, str(SCRIPT), *m.group(1).split()],
        input=f"forge {COGNEE_REPO} cognee\n", capture_output=True, text=True, encoding="utf-8",
    )
    assert p.returncode == 0, p.stdout
    assert json.loads(p.stdout)["args"] == {"target_repo": COGNEE_REPO, "skill_name": "cognee"}


def _branch(step, label):
    """The text of one step 1 branch bullet, up to the next bullet or paragraph."""
    return re.split(r"\n\s*\n|\n   - ", step.split(label, 1)[1], maxsplit=1)[0]


def test_step_1_branches_before_any_workflow_runs():
    step = _step_1()
    for branch in ("**No JSON object on stdout**", "**Exit 2**", "**Exit 3**", "**`deprecated_alias`**"):
        assert branch in step, branch
    for field in ("`unknown_codes`", "`unexpected_args`", "`missing_args`", "`malformed_brackets`",
                  "`valid`", "`args`"):
        assert field in step, field
    exit_3 = _branch(step, "**Exit 3**")
    assert "`missing_args`" in exit_3 and "{headless_mode}" in exit_3 and "HALT" in exit_3
    # A parser that prints no JSON halts too: there is no hand fallback that
    # would drop an unknown code such as the TX in `BS CS TX EX`.
    assert "HALT" in _branch(step, "**No JSON object on stdout**")
    assert "fall back" not in step and "table by hand" not in step
    assert "`summary.status` `failed`" in step and "`summary.halt_reason`" in step
    assert "already resolved at recognition" not in _read(PIPELINE_MODE)


def test_resume_offer_skips_a_record_with_no_workflow():
    """A headless parse halt writes a failed pipeline result with no workflow
    in it (step 1): On Activation step 4 must make no resume offer for it."""
    m = re.search(r"^4\. \*\*Read the last pipeline result\*\*(.*?)(?=^\d+\. \*\*|^## )",
                  _read(FORGER_SKILL), re.M | re.S)
    assert m, "On Activation step 4 not found"
    assert re.search(r"no workflow[^.]*no offer|no offer[^.]*no workflow", m.group(1)), m.group(1)


def test_legacy_alias_texts_live_in_step_1_not_in_skill_md():
    step = _step_1()
    assert "**onboard has been removed.**" in step
    assert "**`deepwiki` is now `forge-auto`.**" in step
    m = re.search(r"^## Pipeline Mode\s*$(.*?)(?=^## |\Z)", _read(FORGER_SKILL), re.M | re.S)
    assert m, "SKILL.md has no Pipeline Mode section"
    section = m.group(1)
    assert "HALT" not in section and "do NOT expand" not in section
    assert "`deepwiki`" in section and "`onboard`" in section  # still routed here
    # The forge-auto expansion lives in ALIASES; SKILL.md no longer pins a copy.
    assert "TS[min:90]" not in _read(FORGER_SKILL)


def test_first_workflow_takes_args_and_ts_takes_the_threshold():
    text = _read(PIPELINE_MODE)
    resolve = next(line for line in text.splitlines() if "**Resolve inputs**" in line)
    assert "The first workflow takes the parse's `args`" in resolve
    invoke = next(line for line in text.splitlines() if "**Invoke the workflow**" in line)
    assert "`{pipeline_alias}` set to the parse's `alias`" in invoke
    assert "When TS's plan entry has a `min`, invoke TS with `--threshold=<min>`" in invoke


def test_alias_forms_match_the_inputs_the_parser_binds():
    """SKILL.md's Pipelines paragraph and pipeline-contracts.md show each alias
    with as many arguments as ALIAS_INPUTS binds."""
    pipelines = next(p for p in _read(FORGER_SKILL).split("\n\n") if p.startswith("**Pipelines.**"))
    arguments = _read(CONTRACTS).split("## Pipeline Arguments", 1)[1].split("\n## ", 1)[0]
    for alias, inputs in mod.ALIAS_INPUTS.items():
        for text in (pipelines, arguments):
            m = re.search(rf"`{re.escape(alias)}((?: <[^>`]+>)*)`", text)
            assert m, alias
            assert len(re.findall(r"<[^>]+>", m.group(1))) == len(inputs), (alias, m.group(0))
        for name in inputs:
            assert f"`{name}`" in arguments, (alias, name)


@pytest.mark.parametrize(
    "skill,name",
    [
        pytest.param("skf-analyze-source", "project_path", id="an-project-path"),
        pytest.param("skf-brief-skill", "target_repo", id="bs-target-repo"),
        pytest.param("skf-brief-skill", "skill_name", id="bs-skill-name"),
        pytest.param("skf-quick-skill", "target", id="qs-target"),
        pytest.param("skf-audit-skill", "skill_name", id="as-skill-name"),
    ],
)
def test_bound_inputs_are_inputs_the_first_workflow_takes(skill, name):
    """The input sits in the SKILL.md Inputs row, or in the references file an
    input contract lives in (invocation-contract.md, or brief's headless-args.md)."""
    root = REPO / "src" / skill
    skill_md = _read(root / "SKILL.md")
    if re.search(rf"(?:^\| `{name}`|\*\*Inputs\*\* \|[^\n]*\b{name}\b)", skill_md, re.M):
        return
    contracts = [root / "references" / f for f in ("invocation-contract.md", "headless-args.md")]
    assert any(f.exists() and f"`{name}`" in _read(f) for f in contracts), (skill, name)
