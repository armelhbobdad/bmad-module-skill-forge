#!/usr/bin/env python3
"""skf-brief-skill's headless inputs, scope defaults, gates and override surface.

#594 (brief part): step 1 §1b sends a headless run to the input gate in
references/headless-args.md before any section reads an argument, so a
preset is merged and the validator has run before a name is checked or the
description is composed from `intent`. Step 3 names one headless boundary
default per scope type and logs it as a `warn:` line, which the result
envelope's `warnings` carries; a specific-modules recommendation the module
count alone made falls back to full-library boundaries, recorded in
scope.rationale, and a reference-app scope with no `include` halts
`input-missing` (a `scope_type=reference-app` argument at the input gate).
The public-api default is the files the recipe runner traces the entry
points' names to, and the component-library default takes the registry and
demo patterns skf-detect-registry.py finds.

#596 (brief part): customize.toml drops `brief_schema_path`, names each
path scalar's real default, uses the DO-NOT-EDIT header form, says when the
prepend steps run and how to drop the bundled persistent fact.

#599 (brief part): the pause step 2 could not time, step 3's menu, the
re-probe cache rule and confirm-brief's repeated menu bullets are gone, and
step 1 ends on one message and one wait.

#600 (brief part): gather-intent.md is carved: the headless input gate and
the ratify branch are files that load only on their route.

No test runs the step prose, so these checks pin it, and they run the
recommender and the validator the prose relies on.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO / "src" / "skf-brief-skill"
REFERENCES = SKILL_DIR / "references"
SKILL_MD = SKILL_DIR / "SKILL.md"
CUSTOMIZE = SKILL_DIR / "customize.toml"
GATHER_INTENT = REFERENCES / "gather-intent.md"
HEADLESS_ARGS = REFERENCES / "headless-args.md"
RATIFY = REFERENCES / "gather-intent-ratify.md"
ANALYZE_TARGET = REFERENCES / "analyze-target.md"
SCOPE_DEFINITION = REFERENCES / "scope-definition.md"
CONFIRM_BRIEF = REFERENCES / "confirm-brief.md"
SCRIPTS = REPO / "src" / "shared" / "scripts"
RECOMMENDER = SCRIPTS / "skf-recommend-scope-type.py"
INPUTS_VALIDATOR = SCRIPTS / "skf-validate-brief-inputs.py"
DETECT_REGISTRY = SCRIPTS / "skf-detect-registry.py"
EXTRACT_PUBLIC_API = SCRIPTS / "skf-extract-public-api.py"
CONTRACT = REFERENCES / "invocation-contract.md"
TEMPLATES = SKILL_DIR / "assets" / "scope-templates.md"
ENVELOPE_SCHEMA = SCRIPTS / "schemas" / "skf-brief-result-envelope.v1.json"

HALT_CALL = "`uv run {emitBriefEnvelopeHelper} emit --target stderr`"
BASH = shutil.which("bash")
# The documented blocks are POSIX shell; on Windows `bash` may be WSL's launcher.
POSIX_BASH = BASH is not None and sys.platform != "win32"
# A fenced bash block, at any indent (a block inside a list item is indented).
BASH_BLOCK_RE = re.compile(r"^(?P<indent>[ \t]*)```bash\n(?P<body>.*?)^(?P=indent)```", re.DOTALL | re.M)
BOUNDARY_WARNING = "warn: headless boundary default <type>: <what was chosen>"
SOURCE_SCOPE_TYPES = ("full-library", "public-api", "component-library", "specific-modules", "reference-app")
# Every file of the skill that a run reads: SKILL.md and the stage and asset files.
SKILL_FILES = sorted(SKILL_DIR.rglob("*.md"))
# The issue's budget is 9,000 cl100k tokens; at 3.5 characters a token, a conservative ratio for this prose,
# 31,500 characters stays under it without a tokenizer in the test run.
GATHER_INTENT_MAX_CHARS = 31_500


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    """The text under the heading line that starts with `heading`, up to the next heading of the same or a
    higher level."""
    match = re.compile(rf"^{re.escape(heading)}[^\n]*\n", re.M).search(text)
    assert match, heading
    level = len(heading) - len(heading.lstrip("#"))
    end = re.compile(rf"^#{{1,{level}}} ", re.M).search(text, match.end())
    return text[match.start():end.start() if end else len(text)]


def _frontmatter(path: Path) -> str:
    text = _read(path)
    assert text.startswith("---\n"), path.name
    return text[4:text.index("\n---\n", 4)]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _blocks(text: str, needle: str) -> list[str]:
    """The ```bash blocks of `text` that hold `needle`, without the indent of their list item."""
    blocks = []
    for match in BASH_BLOCK_RE.finditer(text):
        indent = len(match.group("indent"))
        body = "".join(line[indent:] for line in match.group("body").splitlines(keepends=True))
        if needle in body:
            blocks.append(body)
    return blocks


def _write_tree(root: Path, files: dict[str, str]) -> Path:
    """Write `files` (repo path -> text) under `root` as bytes, so they keep LF line ends on Windows."""
    for rel, content in files.items():
        path = root.joinpath(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))
    return root


def _pinned_ast_grep() -> bool:
    """True when the ast-grep on PATH is the version package.json's test:python pins."""
    scripts = json.loads((REPO / "package.json").read_text(encoding="utf-8"))["scripts"]
    pin = re.search(r"--with ast-grep-cli==([\w.]+)", scripts["test:python"])
    exe = shutil.which("ast-grep")
    if pin is None or exe is None:
        return False
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0 and out.stdout.split()[-1:] == [pin.group(1)]


def _recommend(payload: dict) -> dict:
    proc = subprocess.run([sys.executable, str(RECOMMENDER), "--json", json.dumps(payload)], capture_output=True,
                          text=True, encoding="utf-8", timeout=60, check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# --------------------------------------------------------------------------
# Step 1: the headless gate runs before any section reads an argument (#594)
# --------------------------------------------------------------------------


def test_step_one_routes_every_mode_before_the_interactive_flow():
    text = _read(GATHER_INTENT)
    routes = _section(text, "### 1b. Route by Mode")
    bullets = [line for line in routes.splitlines() if line.startswith("- **")]
    assert [b.split("**")[1] for b in bullets] == ["`{auto_mode}` is true", "`{headless_mode}` is true:",
                                                   "Otherwise"], bullets
    auto = routes[routes.index(bullets[0]):routes.index(bullets[1])]
    assert "`{autoBriefFile}`" in auto and "`{headlessArgsFile}`" in bullets[1] and "§2" in bullets[2]
    front = _frontmatter(GATHER_INTENT)
    assert "headlessArgsFile: 'references/headless-args.md'" in front
    assert "autoBriefFile: 'references/step-auto-brief.md'" in front
    # Past the routing, the file is the interactive flow, so nothing there says "interactive only" or
    # names the headless route.
    interactive = text[text.index("### 2. Welcome and Explain"):]
    for needle in ("headless", "interactive only", "when the flow is interactive"):
        assert needle not in interactive.lower(), needle
    assert "#### Execution rules:" not in interactive


def test_the_input_gate_merges_and_validates_before_it_derives():
    text = _read(HEADLESS_ARGS)
    order = ["### 1. Preset Merge", "### 2. Validate the Arguments", "### 3. Ratify Route (`from_brief`)",
             "### 4. Source Authority", "### 5. Derive the Brief Fields", "### 6. Continue"]
    positions = [text.index(f"\n{heading}\n") for heading in order]
    assert positions == sorted(positions)
    assert "**GATE [default: use args]**" in text[:positions[0]]
    assert re.search(r"^nextStepFile: 'analyze-target\.md'$", _frontmatter(HEADLESS_ARGS), re.M)
    assert re.search(r"^ratifyFile: 'references/gather-intent-ratify\.md'$", _frontmatter(HEADLESS_ARGS), re.M)
    assert "validateBriefInputsProbeOrder:" in _frontmatter(HEADLESS_ARGS)
    # The derive section reads the validated arguments: the description comes from `intent` after the merge.
    derive = _section(text, "### 5. Derive the Brief Fields")
    assert derive.startswith("### 5. Derive the Brief Fields\n\nFrom `normalized`")
    assert "`{descriptionVoiceExamplesPath}`" in derive and "literal `Use when` clause" in derive
    # GitHub owners match case-insensitively while the API keeps the case.
    assert "both lower-cased" in _section(text, "### 4. Source Authority")


def test_every_warning_the_input_gate_logs_reaches_the_envelope():
    for line in _read(HEADLESS_ARGS).splitlines():
        if '"warn: ' in line:
            assert "workflow_warnings[]" in line, line[:100]


def test_the_argument_table_lists_what_the_validator_knows():
    """The validator enforces the table: every argument it knows is a row, and the only extra row is
    `preset`, which the gate merges and drops before validation."""
    validator = _load(INPUTS_VALIDATOR, "skf_validate_brief_inputs")
    table = _section(_read(HEADLESS_ARGS), "## Arguments")
    rows = set(re.findall(r"^\| `([a-z_]+)` \|", table, re.M))
    assert rows == set(validator.KNOWN_FIELDS) | {"preset"}, rows ^ (set(validator.KNOWN_FIELDS) | {"preset"})
    [scope_row] = [line for line in table.splitlines() if line.startswith("| `scope_type` |")]
    assert set(re.findall(r"`([a-z-]+)`", scope_row)) >= validator.VALID_SCOPE_TYPES


def test_the_headless_gate_and_the_ratify_branch_load_only_on_their_route():
    """#600: SKILL.md loads gather-intent.md alone; the carved files load from the one place that routes to
    them, and gather-intent.md stays under the single-file budget."""
    activation = _section(_read(SKILL_MD), "## On Activation")
    assert re.findall(r"`references/[a-z-]+\.md`", activation) == ["`references/invocation-contract.md`",
                                                                    "`references/gather-intent.md`"]
    text = _read(GATHER_INTENT)
    assert len(text) < GATHER_INTENT_MAX_CHARS, len(text)
    uses = {name: [m.start() for m in re.finditer(re.escape(f"`{{{name}}}`"), text)]
            for name in ("headlessArgsFile", "ratifyFile")}
    routes = text.index("### 1b. Route by Mode")
    ratify_branch = text.index("#### 3.1a Branch: Ratify an Existing Brief")
    assert uses["headlessArgsFile"] and all(routes < at < text.index("### 2. ") for at in uses["headlessArgsFile"])
    assert len(uses["ratifyFile"]) == 1 and ratify_branch < uses["ratifyFile"][0] < text.index("#### 3.1b")
    # The source-authority detection is part of the gate now, not a third hop.
    assert not (REFERENCES / "headless-source-authority-detection.md").exists()
    assert "headless-source-authority-detection" not in "".join(_read(path) for path in SKILL_FILES)


# --------------------------------------------------------------------------
# Step 3: one headless boundary default per scope type (#594)
# --------------------------------------------------------------------------


def _boundary_gate() -> str:
    return _section(_read(SCOPE_DEFINITION), "### 3. Define Boundaries Based on Selection")


def test_every_source_scope_type_has_a_headless_boundary_default_or_a_halt():
    gate = _boundary_gate()
    rows = dict(re.findall(r"^\| `([a-z-]+)` \| (.+) \|$", gate, re.M))
    assert tuple(rows) == SOURCE_SCOPE_TYPES, rows
    validator = _load(INPUTS_VALIDATOR, "skf_validate_brief_inputs")
    assert set(rows) | {"docs-only"} == validator.VALID_SCOPE_TYPES
    assert "Halt as below" in rows["reference-app"]
    assert "`include` and `exclude` as given" in gate
    # docs-only takes every collected URL in §2, with the recommender's short-circuit.
    docs_only = _section(_read(SCOPE_DEFINITION), "### 2. Handle Docs-Only Mode (if applicable)")
    [headless] = [line for line in docs_only.splitlines() if line.startswith("**Headless:**")]
    assert "every collected doc URL" in headless and '"docs-only"' in headless


def test_a_boundary_default_is_a_warning_the_envelope_carries():
    gate = _boundary_gate()
    [rule] = [line for line in gate.splitlines() if line.startswith("**GATE [default: the scope type's boundary")]
    assert f"`{BOUNDARY_WARNING}`" in rule and "add that line to `workflow_warnings[]`" in rule
    # SKILL.md's one list of warnings takes every `warn:` line a step logs.
    rules = _section(_read(SKILL_MD), "## Workflow Rules")
    assert "each `warn:` line a step logs" in rules


def test_a_reference_app_scope_without_include_halts_input_missing():
    gate = _boundary_gate()
    [halt] = [line for line in gate.splitlines() if line.startswith("A scope with no default")]
    assert re.search(re.escape(HALT_CALL) + r'.*`halt_reason: "input-missing"`.*then HALT \(exit code 2\)', halt)
    schema = json.loads(_read(ENVELOPE_SCHEMA))
    assert schema["$defs"]["skf-envelope"]["const"]["exit_codes"]["input-missing"] == 2
    assert "`include`" in halt


def test_the_count_heuristic_falls_back_to_full_library_and_says_so():
    rows = dict(re.findall(r"^\| `([a-z-]+)` \| (.+) \|$", _boundary_gate(), re.M))
    modules = rows["specific-modules"]
    for needle in ("`named_module_subset`", "`specific-modules-count`", "switch to `full-library`",
                   "`scope.rationale`", "`chosen` `full-library`", "`accepted_recommendation` false",
                   "from a `scope_type` argument, halt as below"):
        assert needle in modules, needle
    # The heuristic the row names is the one the recommender returns for a module count alone,
    # and a named module takes the other one, whose modules the row includes.
    by_count = _recommend({"signals": {"wants_wiring_pattern": False, "named_module_subset": [],
                                       "wants_narrow_api": False}, "module_count": 6, "mode": "headless"})
    assert (by_count["scope_type"], by_count["matched_heuristic"]) == ("specific-modules", "specific-modules-count")
    by_name = _recommend({"signals": {"wants_wiring_pattern": False, "named_module_subset": ["auth"],
                                      "wants_narrow_api": False}, "module_count": 6, "mode": "headless"})
    assert by_name["matched_heuristic"] == "specific-modules-naming"


def test_scope_type_and_boundaries_are_decided_where_they_are_asked():
    """The old step 3 GATE ran after the sections that used its arguments; each section now carries its own
    headless line, and no menu closes the step."""
    text = _read(SCOPE_DEFINITION)
    for heading, gate in (("### 2c. Offer Scope Templates", "**GATE [default: the recommendation]**"),
                          ("### 3. Define Boundaries Based on Selection",
                           "**GATE [default: the scope type's boundary default]**"),
                          ("### 5. Summarize Scope Decisions", "**GATE [default: C]**")):
        assert gate in _section(text, heading), heading
    scope_type = _section(text, "### 2c. Offer Scope Templates")
    assert '`heuristic` = `"user-supplied-arg"`' in scope_type and '"mode": "headless"' in scope_type
    rules = _section(text, "## Rules")
    assert "- **Headless (`{headless_mode}` is true):** no section prompts." in rules
    assert "### 6. Continue to Brief Confirmation" in text and "MENU OPTIONS" not in text
    assert "advancedElicitationSkill" not in text and "partyModeSkill" not in text


def test_the_scope_signals_are_classified_whichever_way_the_type_is_set():
    """A `scope_type=specific-modules` argument skips the recommender, not the classification: §3 builds the
    boundary from the `named_module_subset` the `intent` and `scope_hint` arguments name."""
    section = _section(_read(SCOPE_DEFINITION), "### 2c. Offer Scope Templates")
    [gate] = [line for line in section.splitlines() if line.startswith("**GATE [default: the recommendation]**")]
    classify = gate.index("classify the `intent` and `scope_hint` arguments")
    argument = gate.index("A `scope_type` argument is the type")
    assert classify < argument < gate.index("Otherwise run the call")
    assert "whichever way the type is set" in gate[classify:argument]
    assert "`named_module_subset`" in gate[classify:argument] and "skip the menu and the call" in gate


def test_an_exclude_without_include_joins_the_default_exclusions():
    [rule] = [line for line in _boundary_gate().splitlines()
              if line.startswith("**GATE [default: the scope type's boundary")]
    assert "the globs of an `exclude` argument, when one was supplied, added to its exclusions" in rule
    assert "naming any `exclude` globs added" in rule
    [row] = [line for line in _section(_read(HEADLESS_ARGS), "## Arguments").splitlines()
             if line.startswith("| `exclude` |")]
    assert "With an `include`, step 3 §3 uses them as given; without one, it adds them to the exclusions" in row


def test_a_module_include_is_the_snapshot_path_of_the_module():
    """A module's `path` in the snapshot is repo-relative and already carries the module root and any
    workspace (`--root`), so the include adds no prefix of its own: `auth/**` would match nothing under a
    src/ layout, and a second workspace prefix would double it."""
    gate = _boundary_gate()
    [module] = [line for line in gate.splitlines() if line.startswith("- **A module include**")]
    for needle in ("`<path>/**`", "`path` in `{run_dir}/snapshot.json`", "`{run_dir}/package-snapshot.json`",
                   "with any workspace prefix already in it", "A `named_module_subset` name maps to the §4.3 module",
                   "`{monorepo_workspace}/**` when step 2 picked a workspace (§3b), else `**`"):
        assert needle in module, needle
    assert "Globs carry the `monorepo_workspace` prefix" not in gate
    workspaces = _load(SCRIPTS / "skf-detect-workspaces.py", "skf_detect_workspaces")
    tree = ["package.json", "packages/sdk/package.json", "packages/sdk/src/auth/a.ts", "packages/sdk/src/http/b.ts"]
    snapshot = workspaces.snapshot(tree, {}, root="packages/sdk")
    assert [c["path"] for c in snapshot["module_candidates"]] == ["packages/sdk/src/auth", "packages/sdk/src/http"]


def test_the_headless_exclusions_are_the_full_library_templates_globs():
    [bullet] = [line for line in _boundary_gate().splitlines() if line.startswith("- **The default exclusions**")]
    globs = re.findall(r"`(\*\*/[^`]+)`", bullet)
    assert len(globs) == 7, globs
    full_library = _section(_read(TEMPLATES), "### Full Library Boundaries")
    for glob in globs:
        assert f"`{glob}`" in full_library, glob


def _public_api_files(result: Path) -> list[str]:
    """Run the documented one-line listing over a runner result and return the lines it prints."""
    [block] = _blocks(_boundary_gate(), "entry_point_diff")
    [line] = block.strip().splitlines()
    argv = shlex.split(line.replace("{run_dir}/public-api.json", result.as_posix()))
    assert argv[:3] == ["uv", "run", "python"]
    proc = subprocess.run([sys.executable, *argv[3:]], capture_output=True, text=True, encoding="utf-8",
                          timeout=60, check=False)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.splitlines()


def test_the_public_api_default_is_the_files_that_define_the_public_names(tmp_path):
    """Step 2's quick mode names the entry file that lists an export as its `source_file`, so a barrel
    gave an include of the barrel alone. The default takes the runner's trace to the defining files."""
    gate = _boundary_gate()
    rows = dict(re.findall(r"^\| `([a-z-]+)` \| (.+) \|$", gate, re.M))
    assert "public API file" in rows["public-api"] and "`source_file`" not in gate
    [bullet] = [line for line in gate.splitlines() if line.startswith("- **The public API files**")]
    assert "§3c's recipe runner" in bullet and '-o "{run_dir}/public-api.json"' in bullet
    assert "the `full-library` default as its globs" in bullet
    assert "`warn: headless boundary default public-api: full-library boundaries ({the reason})`" in gate
    result = tmp_path / "public-api.json"
    result.write_bytes(json.dumps({"entry_point_diff": {"public": [
        {"name": "own", "via": "declaration", "file": "src/index.ts"},
        {"name": "foo", "via": "re-export", "file": "src/lib/foo.ts"},
        {"name": "Bar", "via": "re-export", "file": "src/lib/bar.ts"},
        {"name": "Bar2", "via": "re-export", "file": "src/lib/bar.ts"},
        {"name": "ns", "via": "namespace", "file": None}]}}).encode("utf-8"))
    assert _public_api_files(result) == ["src/index.ts", "src/lib/bar.ts", "src/lib/foo.ts"]


@pytest.mark.skipif(not _pinned_ast_grep(), reason="no ast-grep of the version package.json pins")
def test_the_documented_runner_call_traces_a_barrel_to_its_definitions(tmp_path):
    """The barrel the review verified: `export { foo } from './foo'; export { Bar } from './bar'`. The include
    is the two definition files, plus the barrel only for a name it defines itself."""
    tier_a = _section(_read(SCOPE_DEFINITION), "### 3c. Tier-A Authoring Surface (coarse-glob monorepo subsets)")
    [block] = _blocks(tier_a, "{extractPublicApiHelper}")
    repo = _write_tree(tmp_path / "repo", {
        "package.json": '{"name": "acme", "main": "src/index.ts"}\n',
        "src/index.ts": "export { foo } from './foo';\nexport { Bar } from './bar';\nexport const own = 1;\n",
        "src/foo.ts": "export function foo() {}\n",
        "src/bar.ts": "export class Bar {}\n",
        "src/internal.ts": "export const hidden = 3;\n",
    })
    line = (block.strip().replace("<source folder>", repo.as_posix()).replace("<include glob>", "src/**")
            .replace("<exclude glob>", "**/*.test.*").replace("{language}", "typescript")
            .replace("{run_dir}/tier-a.json", (tmp_path / "public-api.json").as_posix()))
    argv = shlex.split(line)
    assert argv[:3] == ["uv", "run", "{extractPublicApiHelper}"]
    proc = subprocess.run([sys.executable, str(EXTRACT_PUBLIC_API), *argv[3:]], capture_output=True, text=True,
                          encoding="utf-8", timeout=300, check=False, cwd=REPO)
    assert proc.returncode == 0, proc.stderr
    assert _public_api_files(tmp_path / "public-api.json") == ["src/bar.ts", "src/foo.ts", "src/index.ts"]


def _detection_block() -> str:
    [block] = _blocks(_boundary_gate(), "{detectRegistryHelper}")
    return block


def test_component_library_detection_runs_the_registry_helper():
    """The demo patterns and the registry candidate come from skf-detect-registry.py, create-skill's own
    helper, not from a scan by hand: the [C] flow presents them, and a headless run takes them."""
    assert "detectRegistryProbeOrder:" in _frontmatter(SCOPE_DEFINITION)
    block = _detection_block()
    assert block.count('--files-from "{run_dir}/tree.json"') == 3
    assert "registry --files-from \"{run_dir}/tree.json\" --candidates-only" in block
    gate = _boundary_gate()
    bullet = gate[gate.index("- **Component library detection**"):gate.index("A scope with no default")]
    assert "`selected` when `headless_accept` is true" in bullet and "every `patterns[]` glob" in bullet
    assert "warn: component library detection skipped" in gate and "workflow_warnings[]" in gate
    rows = dict(re.findall(r"^\| `([a-z-]+)` \| (.+) \|$", gate, re.M))
    assert "component library detection below" in rows["component-library"]
    templates = _read(TEMPLATES)
    component = templates[templates.index("### Component Library Boundaries"):templates.index("## Scripts & Assets")]
    assert component.count("component library detection found") == 2
    for scan in ("Scan source tree", "Directories: `demo/`", "Files named `registry.ts`"):
        assert scan not in component, scan


@pytest.mark.skipif(not POSIX_BASH, reason="runs the documented block in a POSIX bash")
def test_the_documented_detection_reads_step_twos_github_listing(tmp_path):
    """Step 2 stages a GitHub source's file list as skf-github-probe.py's listing object; the block reads it,
    fetches the registry candidate into the run folder and scores it there."""
    entries = ",\n".join(f'  {{ id: "c{i}", name: "C{i}", category: "forms" }}' for i in range(20))
    registry = _write_tree(tmp_path / "served", {"registry.ts": f"export const registry = [\n{entries}\n];\n"})
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    listing = {"status": "ok", "repo": "o/r", "ref": "main", "count": 4, "truncated": False,
               "tree": ["src/registry/registry.ts", "src/button.tsx", "src/stories/button.stories.tsx",
                        "examples/basic.tsx"]}
    (run_dir / "tree.json").write_bytes((json.dumps(listing) + "\n").encode("utf-8"))
    block = (_detection_block().replace("uv run {detectRegistryHelper}", f'"{sys.executable}" "{DETECT_REGISTRY}"')
             .replace("<source folder>", "{run_dir}/files").replace("{run_dir}", run_dir.as_posix())
             .replace("{owner}/{repo}", "o/r").replace("{analysis_ref}", "main"))
    assert not re.findall(r"\{[A-Za-z_]+\}", block), "every placeholder of the block is filled"
    fake_gh = f'gh() {{ cat "{(registry / "registry.ts").as_posix()}"; }}\n'
    proc = subprocess.run([BASH, "-c", fake_gh + block], capture_output=True, text=True, encoding="utf-8",
                          timeout=60, check=False)
    assert proc.returncode == 0, proc.stderr
    decoder = json.JSONDecoder()
    demo, end = decoder.raw_decode(proc.stdout)
    found, _ = decoder.raw_decode(proc.stdout[end:].lstrip())
    assert {p["pattern"] for p in demo["patterns"]} == {"**/stories/**", "**/examples/**", "**/*.stories.*"}
    assert found["selected"] == "src/registry/registry.ts" and found["headless_accept"] is True
    assert (run_dir / "files" / "src" / "registry" / "registry.ts").is_file()


def test_the_halt_says_how_a_specific_modules_caller_clears_it():
    [halt] = [line for line in _boundary_gate().splitlines() if line.startswith("A scope with no default")]
    assert "or, for `specific-modules`, name the modules in `intent` or `scope_hint`" in halt
    [gates] = [line for line in _read(CONTRACT).splitlines() if line.startswith("| **Gates** |")]
    assert "a `reference-app` scope, or a `specific-modules` `scope_type` argument naming no module, halts" in gates


def test_a_reference_app_argument_without_include_halts_at_the_input_gate():
    """A pure input check: the validator refuses it before step 2 lists or clones the repository, and step 3
    keeps its halt for a reference-app the recommender picked."""
    validator = _load(INPUTS_VALIDATOR, "skf_validate_brief_inputs")
    out = validator.validate({"target_repo": "/x", "skill_name": "foo", "scope_type": "reference-app"})
    assert (out["valid"], out["halt_reason"]) == (False, "input-missing")
    text = _read(HEADLESS_ARGS)
    [row] = [line for line in _section(text, "## Arguments").splitlines() if line.startswith("| `include` |")]
    assert "a `scope_type=reference-app` argument halts here instead (§2)" in row
    [invalid] = [line for line in text.splitlines() if line.startswith("- **`valid: false`**")]
    assert "a `reference-app` `scope_type` without `include`" in invalid
    rows = dict(re.findall(r"^\| `([a-z-]+)` \| (.+) \|$", _boundary_gate(), re.M))
    assert "a type the recommender picked" in rows["reference-app"]
    [codes] = [line for line in _read(CONTRACT).splitlines() if line.startswith("| 2    |")]
    assert "a `scope_type=reference-app` argument with no `include` → `input-missing`" in codes


def test_the_contract_points_at_the_argument_table_instead_of_restating_it():
    [inputs] = [line for line in _read(CONTRACT).splitlines() if line.startswith("| **Inputs** |")]
    assert "the Arguments table of `references/headless-args.md`" in inputs
    assert "`from_brief` [optional:" in inputs and "`[auto]` [optional:" in inputs
    for restated in ("default community", "`include` [optional", "`scope_hint` [optional"):
        assert restated not in inputs, restated


def test_a_halt_that_names_no_halt_reason_emits_nothing():
    """A helper with no installed path HALTs with no halt_reason in every stage file, the headless-only
    input gate and ratify route included: the Halt Contract says it is an install fault and emits nothing."""
    contract = _section(_read(SKILL_MD), "## Halt Contract")
    assert "A HALT that names no `halt_reason`, such as a helper with no installed path" in contract
    assert "emits nothing in any mode" in contract


def test_a_derive_run_carries_the_scope_fields_step_three_set():
    """The headless component-library default sets the registry, demo and variant keys on a derive run, so
    the writer payload must not null them."""
    [carry] = [line for line in _read(REFERENCES / "write-brief.md").splitlines()
               if line.startswith("**Ratify mode (`ratify_mode: true`):**")]
    assert "on a derive run all null" not in carry
    for needle in ("`scope_tier_a_include` from step 3 §3c",
                   "the three component-library keys from step 3's component-library flow or its headless default",
                   "`source_ref` and `scope_amendments` are null"):
        assert needle in carry, needle


# --------------------------------------------------------------------------
# One wait at each stage boundary, no dead branches (#599)
# --------------------------------------------------------------------------


def test_step_two_hands_off_in_the_same_turn():
    handoff = _section(_read(ANALYZE_TARGET), "### 6. Proceed to Scope Definition")
    assert "In the same turn as the §5 summary" in handoff and "{nextStepFile}" in handoff
    for gone in ("Pause briefly", "brief pause", "Menu Handling Logic", "soft auto-proceed"):
        assert gone not in handoff, gone
    # The corrections the pause invited land at step 3's first answer.
    context = _section(_read(SCOPE_DEFINITION), "### 1. Present Scope Context")
    assert "Anything wrong in the analysis?" in context


def test_step_one_ends_on_one_message_and_one_wait():
    text = _read(GATHER_INTENT)
    summary = _section(text, "### 7. Summarize Gathered Intent")
    assert "Ready to analyze" not in summary and "in one message, and wait once" in summary
    description = _section(text, "### 7b. Synthesize Skill Description")
    assert "Wait for" not in description and "Soft sentence-count check" not in description
    menu = _section(text, "### 8. Present MENU OPTIONS")
    [accept] = [line for line in menu.splitlines() if line.startswith("- IF C:")]
    assert "runs past three sentences" in accept


def test_step_three_ends_on_one_message_and_no_menu():
    text = _read(SCOPE_DEFINITION)
    summary = _section(text, "### 5. Summarize Scope Decisions")
    assert "when §5b applies, its question in one message, and wait once" in summary
    assert "Asked in the §5 message." in _section(text, "### 5b. Scripts & Assets Intent (Optional)")
    # The [R] re-probe cache saved one round of five-second HEAD requests.
    assert "byte-identical" not in text and "cache" not in text.lower()


def test_confirm_brief_states_each_menu_rule_once():
    rules = _section(_read(CONFIRM_BRIEF), "#### Execution rules:")
    bullets = [line for line in rules.splitlines() if line.startswith("- ")]
    assert len(bullets) == 1 and bullets[0].startswith("- **GATE [default: C]**"), bullets


# --------------------------------------------------------------------------
# The customization surface (#596)
# --------------------------------------------------------------------------


def _workflow() -> dict:
    return tomllib.loads(_read(CUSTOMIZE))["workflow"]


def test_customize_toml_offers_only_settings_that_take_effect():
    workflow = _workflow()
    assert set(workflow) == {"activation_steps_prepend", "activation_steps_append", "persistent_facts",
                             "description_voice_examples_path", "scope_templates_path", "on_complete"}
    for path in SKILL_FILES + [CUSTOMIZE]:
        text = _read(path)
        assert "brief_schema_path" not in text and "briefSchemaPath" not in text, path.name
    # The brief contract's prose copy is loaded directly, never through an override.
    for path in (CONFIRM_BRIEF, REFERENCES / "write-brief.md"):
        assert "`assets/skill-brief-schema.md`" in _read(path), path.name


def test_every_path_scalar_names_its_real_default_and_reaches_a_stage():
    workflow = _workflow()
    skill = _read(SKILL_MD)
    stages = "".join(_read(path) for path in SKILL_FILES if path != SKILL_MD)
    for key, value in workflow.items():
        if not key.endswith("_path"):
            continue
        assert value and (SKILL_DIR / value).is_file(), (key, value)
        # An override that sets the scalar to "" wins the merge: SKILL.md falls back to the same default.
        [(binding, default)] = re.findall(rf"`\{{([A-Za-z]+)\}}` ← `workflow\.{key}`, else `([^`]+)`", skill)
        assert default == value, (key, default, value)
        assert f"`{{{binding}}}`" in stages, binding
    assert "taking the bundled default when the merged value is empty or absent" in _section(skill, "## On Activation")
    flat = " ".join(line.lstrip("#").strip() for line in _read(CUSTOMIZE).splitlines())
    assert "An empty string means the default named below." in flat


def test_customize_toml_header_and_hook_comments_match_activation():
    text = _read(CUSTOMIZE)
    assert "# Team overrides:     {project-root}/_bmad/custom/skf-brief-skill.toml\n" in text
    assert "# Personal overrides: {project-root}/_bmad/custom/skf-brief-skill.user.toml\n" in text
    assert "(under {project-root})" not in text
    prepend = text[:text.index("activation_steps_prepend = []")].rstrip().rsplit("\n\n", 1)[-1]
    flat = " ".join(line.lstrip("#").strip() for line in prepend.splitlines())
    assert "uv probe" not in flat and "On Activation step 3" in flat
    assert "after config.yaml is loaded" in flat
    # The bundled persistent fact can be dropped, and SKILL.md honours the drop.
    facts = text[:text.index("\npersistent_facts = [")].rstrip().rsplit("\n#\n", 1)[-1]
    assert '"!file:{project-root}/**/project-context.md"' in facts
    assert "an entry prefixed `!` loads nothing and drops each earlier entry it names" in _read(SKILL_MD)


@pytest.mark.parametrize("path", [pytest.param(path, id=path.name) for path in (GATHER_INTENT, HEADLESS_ARGS, RATIFY)])
def test_step_one_files_resolve_each_helper_they_call(path):
    """Moving a section between files moves the probe order its helper call needs."""
    text = _read(path)
    front = _frontmatter(path)
    body = text[text.index("\n---\n", 4):]
    for stem in set(re.findall(r"\{([a-z][A-Za-z]+)Helper\}", body)) - {"emitBriefEnvelope"}:
        assert f"{stem}ProbeOrder:" in front, (path.name, stem)
