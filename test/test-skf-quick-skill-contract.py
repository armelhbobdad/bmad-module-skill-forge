#!/usr/bin/env python3
"""Quick Skill contract: the skills-module shape (#527), and the batch
override rule and review preview (#609).

quick-extract.md gives the agent two commands for a skills module: a filtered
tree listing (`gh api --jq`) and a loop that prints each skill's SKILL.md
frontmatter. Both run here against fixtures (jq, awk and bash stand in for
what the agent runs; each test is skipped when its tool is missing), so the
prose cannot drift from a command that works. The rule that picks the skills
root from that listing is prose the agent applies, so it is restated here as
code and run over the listing of real repository layouts: each layout states
the skills root the rule gives it, and a library that ships a skill stays a
library. The batch rule, the halt contract entry and the preview are pinned
where each file states them.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

REPO = Path(__file__).resolve().parent.parent
QS = REPO / "src" / "skf-quick-skill"
QUICK_EXTRACT = QS / "references" / "quick-extract.md"
COMPILE = QS / "references" / "compile.md"
TEMPLATE = QS / "assets" / "skill-template.md"
SKILL = QS / "SKILL.md"
BATCH_MODE = QS / "references" / "batch-mode.md"
HALT_CONTRACT = QS / "references" / "halt-contract.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    assert text.count(start) == 1, f"expected exactly one {start!r}"
    head = text.index(start)
    tail = text.find(end, head + len(start))
    assert tail != -1, f"expected {end!r} after {start!r}"
    return text[head:tail]


def _bash_block(text: str, needle: str) -> str:
    """The one ```bash block of `text` that holds `needle`."""
    blocks = [b for b in re.findall(r"^```bash\n(.*?)^```$", text, flags=re.M | re.S) if needle in b]
    assert len(blocks) == 1, f"expected one bash block holding {needle!r}, found {len(blocks)}"
    return blocks[0]


def _single_quoted_after(block: str, word: str) -> str:
    """The single-quoted argument that follows `word` in a shell block."""
    m = re.search(re.escape(word) + r" '([^']*)'", block)
    assert m, f"no {word} '...' in:\n{block}"
    return m.group(1)


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        pytest.skip(f"{name} is not installed")
    return path


# --------------------------------------------------------------------------
# skills-module: the tree listing (quick-extract §1.5)
# --------------------------------------------------------------------------

def _sniff() -> str:
    return _section(_read(QUICK_EXTRACT), "### 1.5. Repo-Shape Sniff", "### 2. ")


def _listing() -> str:
    return _bash_block(_sniff(), "git/trees/")


TREE = {"sha": "0" * 40, "truncated": False, "tree": [
    {"path": ".github", "type": "tree"},
    {"path": ".github/workflows/ci.yaml", "type": "blob"},
    {"path": "README.md", "type": "blob"},
    {"path": "package.json", "type": "blob"},
    {"path": "docs", "type": "tree"},
    {"path": "docs/index.md", "type": "blob"},
    {"path": "docs/SKILL.md.bak", "type": "blob"},
    {"path": "samples/demo/SKILL.md", "type": "blob"},
    {"path": "skills", "type": "tree"},
    {"path": "skills/alpha/SKILL.md", "type": "blob"},
    {"path": "skills/alpha/assets/module.yaml", "type": "blob"},
    {"path": "skills/alpha/references/guide.md", "type": "blob"},
    {"path": "skills/beta/NOTSKILL.md", "type": "blob"},
    {"path": "skills/beta/SKILL.md", "type": "blob"},
    {"path": "skills/module-help.csv", "type": "blob"},
    {"path": "skills/module.yaml", "type": "blob"},
    {"path": "src/index.js", "type": "blob"},
]}


def test_the_listing_reads_the_tree_at_the_resolved_ref():
    listing = _listing()
    assert 'gh api "repos/{owner}/{repo}/git/trees/{source_ref or HEAD}?recursive=1"' in listing
    assert "--jq '" in listing


def test_the_listing_keeps_root_files_and_skill_and_module_files_only():
    listing = _listing()
    jq = _tool("jq")
    result = subprocess.run([jq, "-r", _single_quoted_after(listing, "--jq")],
                            input=json.dumps(TREE), capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "README.md",
        "package.json",
        "samples/demo/SKILL.md",
        "skills/alpha/SKILL.md",
        "skills/alpha/assets/module.yaml",
        "skills/beta/SKILL.md",
        "skills/module-help.csv",
        "skills/module.yaml",
    ]


# --------------------------------------------------------------------------
# skills-module: the rule that picks the skills root (quick-extract §1.5)
# --------------------------------------------------------------------------

# The §1.5 rule as code. It reads only what the listing keeps (root files,
# SKILL.md, module.yaml, module-help.csv) plus the root package.json, which
# the rule fetches when it needs it. The root folder is "".
MANIFESTS = frozenset({"package.json", "pyproject.toml", "setup.py", "setup.cfg", "Cargo.toml", "go.mod",
                       "pom.xml", "build.gradle", "build.gradle.kts", "Gemfile"})


def _folder(path: str) -> str:
    return path.rpartition("/")[0]


def _ancestors(folder: str) -> list[str]:
    """The folders above `folder`, the root excluded."""
    parts = folder.split("/") if folder else []
    return ["/".join(parts[:i]) for i in range(1, len(parts))]


def _skill_dirs(listing: set[str]) -> set[str]:
    return {_folder(p) for p in listing if p.rpartition("/")[2] == "SKILL.md"}


def _is_module_root(folder: str, listing: set[str], skill_dirs: set[str]) -> bool:
    """Directly holds module.yaml or module-help.csv, and sits in no skill folder."""
    prefix = f"{folder}/" if folder else ""
    holds = f"{prefix}module.yaml" in listing or f"{prefix}module-help.csv" in listing
    in_skill = folder in skill_dirs or any(a in skill_dirs for a in _ancestors(folder))
    return holds and not in_skill


def _skill_folders(folder: str, listing: set[str], skill_dirs: set[str]) -> list[str]:
    prefix = f"{folder}/" if folder else ""
    below = [d for d in skill_dirs if d.startswith(prefix) and d != folder]
    if _is_module_root(folder, listing, skill_dirs):
        return sorted(d for d in below if not any(a in skill_dirs for a in _ancestors(d)))
    return sorted(d for d in below if "/" not in d[len(prefix):])


def _ships_no_code(listing: set[str], package_json: dict | None) -> bool:
    root = {p for p in listing if "/" not in p}
    manifests = {p for p in root if p in MANIFESTS or p.endswith(".csproj")}
    if not manifests:
        return True
    if manifests != {"package.json"}:
        return False
    fields = package_json or {}
    if fields.get("main") or any(key in fields for key in ("exports", "bin", "workspaces")):
        return False
    return not root & {"index.js", "index.ts"}


def skills_root(listing: set[str], package_json: dict | None, scope_hint: str | None) -> tuple[str, list[str]] | None:
    """(skills root, its skill folders), or None when the shape stays library."""
    skill_dirs = _skill_dirs(listing)
    if scope_hint is not None:
        found = _skill_folders(scope_hint.strip("/"), listing, skill_dirs)
        return (scope_hint.strip("/"), found) if found else None
    counting = []
    for candidate in ["", *sorted({p.split("/")[0] for p in listing if "/" in p})]:
        found = _skill_folders(candidate, listing, skill_dirs)
        module_root = _is_module_root(candidate, listing, skill_dirs)
        if found and (module_root or _ships_no_code(listing, package_json)):
            counting.append((module_root, len(found), candidate, found))
    if not counting:
        return None
    best = max(counting, key=lambda c: c[:2])
    return best[2], best[3]


def suggested_scope(listing: set[str]) -> str | None:
    """The folder the §4 note names when a run stays a library with no exports."""
    skill_dirs = _skill_dirs(listing)
    folders = {a for p in listing for a in [*_ancestors(_folder(p)), _folder(p)] if a}
    scored = [(_is_module_root(f, listing, skill_dirs), len(_skill_folders(f, listing, skill_dirs)), f)
              for f in sorted(folders)]
    scored = [s for s in scored if s[1]]
    return max(scored, key=lambda s: s[:2])[2] if scored else None


class Layout(NamedTuple):
    paths: tuple[str, ...]
    package_json: dict | None
    root: str | None  # the skills root the rule picks; None: the shape stays library
    skills: tuple[str, ...] = ()
    suggestion: str | None = None  # the folder the §4 note names, for a library
    scope_hint: str | None = None


BUILDER = (  # bmad-code-org/bmad-builder@v2.2.2, the #527 repository
    "README.md", "package.json",
    "samples/bmad-agent-code-coach/SKILL.md", "samples/bmad-agent-creative-muse/SKILL.md",
    "samples/bmad-agent-diagram-reviewer/SKILL.md", "samples/bmad-agent-dream-weaver/SKILL.md",
    "samples/bmad-agent-dream-weaver/assets/module-help.csv", "samples/bmad-agent-dream-weaver/assets/module.yaml",
    "samples/bmad-agent-sentinel/SKILL.md", "samples/bmad-excalidraw/SKILL.md", "samples/sample-module-setup/SKILL.md",
    "samples/sample-module-setup/assets/module-help.csv", "samples/sample-module-setup/assets/module.yaml",
    "skills/bmad-agent-builder/SKILL.md", "skills/bmad-agent-builder/references/build-process.md",
    "skills/bmad-bmb-setup/SKILL.md", "skills/bmad-bmb-setup/assets/module-help.csv",
    "skills/bmad-bmb-setup/assets/module.yaml", "skills/bmad-eval-runner/SKILL.md",
    "skills/bmad-module-builder/SKILL.md", "skills/bmad-module-builder/assets/setup-skill-template/SKILL.md",
    "skills/bmad-module-builder/assets/setup-skill-template/assets/module.yaml",
    "skills/bmad-workflow-builder/SKILL.md", "skills/module-help.csv", "skills/module.yaml",
)
BUILDER_SKILLS = ("skills/bmad-agent-builder", "skills/bmad-bmb-setup", "skills/bmad-eval-runner",
                  "skills/bmad-module-builder", "skills/bmad-workflow-builder")
BMM_612 = (  # bmad-code-org/BMAD-METHOD@v6.12.0: an installer CLI with two modules under src/
    "README.md", "package.json", "src/bmm-skills/agents/bmad-agent-pm/SKILL.md", "src/bmm-skills/module-help.csv",
    "src/bmm-skills/module.yaml", "src/bmm-skills/plan/bmad-prd/SKILL.md", "src/bmm-skills/ship/bmad-build/SKILL.md",
    "src/core-skills/bmad-help/SKILL.md", "src/core-skills/module-help.csv", "src/core-skills/module.yaml",
    "tools/installer/bmad-cli.js", "web-bundles/prd-coach/SKILL.md", "web-bundles/ux-coach/SKILL.md",
)
BMM_612_PACKAGE = {"name": "bmad-method", "main": "tools/installer/bmad-cli.js",
                   "bin": {"bmad-method": "tools/installer/bmad-cli.js"}}
BMM_612_SKILLS = ("src/bmm-skills/agents/bmad-agent-pm", "src/bmm-skills/plan/bmad-prd",
                  "src/bmm-skills/ship/bmad-build")
BMM_HEAD = (  # bmad-code-org/BMAD-METHOD@HEAD: skills/ beside a tooling pyproject.toml
    "README.md", "pyproject.toml", "skills/bmad-agent-pm/SKILL.md", "skills/bmad-architecture/SKILL.md",
    "skills/bmad-prd/SKILL.md", "tools/tests/fixtures/validate-skills/bmad/SKILL.md",
    "web-bundles/prd-coach/SKILL.md",
)

LAYOUTS = {
    "bmad-builder: the module root wins over samples/, which has more skill folders": Layout(
        BUILDER, {"name": "bmad-builder", "main": "", "private": True}, "skills", BUILDER_SKILLS),
    "bmad-builder with scope=skills/, the #527 run": Layout(
        BUILDER, {"name": "bmad-builder", "main": "", "private": True}, "skills", BUILDER_SKILLS,
        scope_hint="skills/"),
    "creative-intelligence-suite: skill folders and a package.json that ships no code": Layout(
        ("README.md", "package.json", "skills/bmad-cis-design-thinking/SKILL.md",
         "skills/bmad-cis-problem-solving/SKILL.md", "skills/bmad-cis-storytelling/SKILL.md", "skills/bmod-cis/SKILL.md"),
        {"name": "bmad-creative-intelligence-suite", "private": True}, "skills",
        ("skills/bmad-cis-design-thinking", "skills/bmad-cis-problem-solving", "skills/bmad-cis-storytelling",
         "skills/bmod-cis")),
    "test-architecture-enterprise: skills at any depth below the module root": Layout(
        ("README.md", "package.json", "src/agents/bmad-tea/SKILL.md", "src/module-help.csv", "src/module.yaml",
         "src/workflows/testarch/bmad-testarch-atdd/SKILL.md", "src/workflows/testarch/bmad-testarch-trace/SKILL.md",
         "test/fixtures/evaluate/stub-agent/skill/SKILL.md"),
        {"name": "bmad-method-test-architecture-enterprise", "main": "", "bin": {"tea-evaluate": "cli/evaluate.js"}},
        "src", ("src/agents/bmad-tea", "src/workflows/testarch/bmad-testarch-atdd",
                "src/workflows/testarch/bmad-testarch-trace")),
    "game-dev-studio: skills at mixed depths below the module root": Layout(
        ("README.md", "package.json", "src/agents/gds-agent-game-dev/SKILL.md", "src/module-help.csv",
         "src/module.yaml", "src/workflows/1-preproduction/research/gds-domain-research/SKILL.md",
         "src/workflows/gds-document-project/SKILL.md", "src/workflows/gds-quick-flow/gds-quick-dev/SKILL.md"),
        {"name": "bmad-game-dev-studio", "main": "", "private": True}, "src",
        ("src/agents/gds-agent-game-dev", "src/workflows/1-preproduction/research/gds-domain-research",
         "src/workflows/gds-document-project", "src/workflows/gds-quick-flow/gds-quick-dev")),
    "skill-forge: a module root beside a package.json with main and bin": Layout(
        ("README.md", "package.json", "src/module-help.csv", "src/module.yaml", "src/skf-create-skill/SKILL.md",
         "src/skf-quick-skill/SKILL.md", "src/shared/scripts/skf-atomic-write.py"),
        {"name": "bmad-module-skill-forge", "main": "tools/cli/skf-cli.js",
         "bin": {"bmad-module-skill-forge": "tools/skf-npx-wrapper.js"}},
        "src", ("src/skf-create-skill", "src/skf-quick-skill")),
    "module files at the repository root": Layout(
        ("README.md", "module-help.csv", "module.yaml", "package.json", "agents/helper/SKILL.md",
         "workflows/plan/make-plan/SKILL.md", "workflows/plan/make-plan/templates/inner/SKILL.md"),
        {"name": "some-module", "main": "index.js"}, "", ("agents/helper", "workflows/plan/make-plan")),
    "anthropics/skills: no manifest, and the folder with the most skill folders wins": Layout(
        (".gitignore", "README.md", "THIRD_PARTY_NOTICES.md", "skills/docx/SKILL.md", "skills/pdf/SKILL.md",
         "skills/skill-creator/SKILL.md", "skills/skill-creator/scripts/init_skill.py", "template/SKILL.md"),
        None, "skills", ("skills/docx", "skills/pdf", "skills/skill-creator")),
    "typescript-wsdl-client: a library with main, exports and bin keeps agent-skill/": Layout(
        ("README.md", "agent-skill/SKILL.md", "package.json", "src/index.ts", "tsconfig.json"),
        {"name": "@techspokes/typescript-wsdl-client", "main": "dist/index.js", "exports": {".": "./dist/index.js"},
         "bin": {"wsdl-tsc": "dist/cli.js"}}, None),
    "better-firebase-functions: a workspaces root keeps skill/": Layout(
        ("README.md", "package.json", "skill/SKILL.md", "turbo.json"),
        {"name": "better-firebase-functions-monorepo", "private": True, "workspaces": ["packages/*"]}, None),
    "viewflow: setup.py beside package.json keeps skill/": Layout(
        ("README.md", "package.json", "setup.py", "skill/SKILL.md"), {"name": "viewflow"}, None),
    "a package.json with no main field, beside the index.js npm then loads": Layout(
        ("README.md", "index.js", "package.json", "skill/SKILL.md"), {"name": "tiny-lib"}, None),
    "BMAD-METHOD v6.12.0: code at the root, so the note names the larger module root": Layout(
        BMM_612, BMM_612_PACKAGE, None, suggestion="src/bmm-skills"),
    "BMAD-METHOD v6.12.0 with scope=src/bmm-skills": Layout(
        BMM_612, BMM_612_PACKAGE, "src/bmm-skills", BMM_612_SKILLS, scope_hint="src/bmm-skills"),
    "BMAD-METHOD v6.12.0 with scope=src/, which holds neither": Layout(
        BMM_612, BMM_612_PACKAGE, None, scope_hint="src/"),
    "BMAD-METHOD HEAD: a pyproject.toml at the root, so the note names skills/": Layout(
        BMM_HEAD, None, None, suggestion="skills"),
    "BMAD-METHOD HEAD with scope=skills/": Layout(
        BMM_HEAD, None, "skills", ("skills/bmad-agent-pm", "skills/bmad-architecture", "skills/bmad-prd"),
        scope_hint="skills/"),
}


def _listed(paths: tuple[str, ...]) -> set[str]:
    """What the §1.5 listing prints for a tree holding `paths`."""
    jq = _tool("jq")
    folders = {a for p in paths for a in [*_ancestors(_folder(p)), _folder(p)] if a}
    tree = [{"path": f, "type": "tree"} for f in sorted(folders)] + [{"path": p, "type": "blob"} for p in paths]
    result = subprocess.run([jq, "-r", _single_quoted_after(_listing(), "--jq")],
                            input=json.dumps({"tree": tree}), capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    return set(result.stdout.splitlines())


@pytest.mark.parametrize("name", list(LAYOUTS))
def test_the_rule_picks_the_skills_root_of_real_layouts(name):
    layout = LAYOUTS[name]
    listing = _listed(layout.paths)
    found = skills_root(listing, layout.package_json, layout.scope_hint)
    if layout.root is None:
        assert found is None
        if layout.scope_hint is None:
            assert suggested_scope(listing) == layout.suggestion
    else:
        assert found == (layout.root, list(layout.skills))


# --------------------------------------------------------------------------
# skills-module: the frontmatter loop (quick-extract §2)
# --------------------------------------------------------------------------

def _loop() -> str:
    return _bash_block(_section(_read(QUICK_EXTRACT), "### 2. Fetch Source Files", "### 3. "), "SKILL.md")


ALPHA = (
    "---\nname: alpha\ndescription: >\n  Builds alpha things.\n  Use when alpha is needed.\n---\n\n"
    "# Alpha\n\n---\n\nname: not-frontmatter\n"
)
ALPHA_FRONTMATTER = "name: alpha\ndescription: >\n  Builds alpha things.\n  Use when alpha is needed.\n"


def _awk(text: bytes) -> bytes:
    program = _single_quoted_after(_loop(), "awk")
    awk = _tool("awk")
    result = subprocess.run([awk, program], input=text, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_the_awk_program_prints_the_frontmatter_and_no_body(newline):
    assert _awk(ALPHA.replace("\n", newline).encode()) == ALPHA_FRONTMATTER.encode()


def test_the_awk_program_prints_nothing_without_frontmatter():
    assert _awk(b"# Beta\n\n---\n\nname: body-text\n") == b""


@pytest.mark.skipif(sys.platform == "win32", reason="the stand-in gh is a POSIX shell script")
def test_the_loop_prints_each_frontmatter_under_its_folder(tmp_path):
    loop = _loop()
    bash = _tool("bash")
    _tool("awk")
    fixtures = tmp_path / "repo"
    (fixtures / "skills" / "alpha").mkdir(parents=True)
    (fixtures / "skills" / "beta").mkdir(parents=True)
    (fixtures / "skills" / "alpha" / "SKILL.md").write_text(ALPHA, encoding="utf-8")
    (fixtures / "skills" / "beta" / "SKILL.md").write_text("# Beta, no frontmatter\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    # Prints the file a contents URL names, after checking the call's shape.
    gh.write_text(
        "#!/bin/sh\n"
        '[ "$1" = api ] && [ "$2" = -H ] && [ "$3" = "Accept: application/vnd.github.raw" ] || exit 9\n'
        'url=$4\n'
        'path=${url#repos/acme/module/contents/}\n'
        'case $url in *"?ref=v1.2.0") ;; *) exit 8 ;; esac\n'
        'cat "$FIXTURES/${path%%\\?*}"\n',
        encoding="utf-8",
    )
    gh.chmod(0o755)
    script = loop.replace("{owner}", "acme").replace("{repo}", "module").replace("{source_ref}", "v1.2.0")
    script = re.sub(r"<each skill folder path[^>]*>", "skills/alpha skills/beta", script)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}", "FIXTURES": str(fixtures)}
    result = subprocess.run([bash, "-c", script], capture_output=True, text=True, env=env, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"=== skills/alpha\n{ALPHA_FRONTMATTER}=== skills/beta\n"


# --------------------------------------------------------------------------
# skills-module: the shape is library-like and reaches the compiled skill
# --------------------------------------------------------------------------


def test_skills_module_is_a_shape_with_no_gate():
    sniff = _sniff()
    shapes = _section(sniff, "**Classify as one of:**", "\n\n**If ")
    # The item runs from its bullet through its indented sub-bullets.
    item = _section(shapes, "- **skills-module**", "\n- **library** (default)")
    for phrase in (
        "Skill folders alone qualify", "proceed with no gate",
        "A module root is a folder that directly holds `module.yaml` or `module-help.csv`: "
        "the listing shows `<folder>/module.yaml` or `<folder>/module-help.csv`",
        "A copy that sits in a skill folder, such as a skill's `assets/module.yaml`, makes no module root.",
        "The skill folders of a module root are all the folders below it that hold a `SKILL.md` "
        "and sit in no other skill folder.",
        "The skill folders of any other folder are its direct subfolders that hold one (`<folder>/<name>/SKILL.md`).",
        "When `scope_hint` is set, it is the only candidate, and it counts whenever it has skill folders.",
        "Otherwise the candidates are the repository root and each top-level folder that has skill folders, "
        "and a candidate counts only when it is a module root or the root ships no code.",
        "or when its only one is a `package.json` that declares no `main` (or an empty one), `exports`, `bin` "
        "or `workspaces` and has no `index.js` or `index.ts` beside it.",
        "So a library with a manifest and one `skill/SKILL.md` stays a library.",
        "When several candidates count, prefer a module root, then the one with the most skill folders.",
    ):
        assert phrase in item, phrase
    # The soft-warn gate names the shapes it stops, so skills-module never reaches it.
    assert "**If an awesome-list, docs-site or examples-only shape is detected**" in sniff
    assert "**If a non-library shape is detected**" not in sniff


def test_a_library_run_with_no_exports_names_the_scope_to_rerun_with():
    inventory = _section(_read(QUICK_EXTRACT), "### 4. Build Extraction Inventory", "### 4.5.")
    rule = _section(inventory, "- If a folder below the repository root has skill folders", "\n")
    assert "re-run with `scope={folder}` to document them as a skills module." in rule
    assert ("Name the module root with the most skill folders or, when the listing shows no module root, "
            "the folder with the most.") in rule


def test_skills_module_exports_are_skill_names_then_menu_codes():
    text = _read(QUICK_EXTRACT)
    fetch = _section(text, "### 2. Fetch Source Files", "### 3. ")
    assert "the `module-help.csv` directly in the skills root (`<skills root>/module-help.csv`)" in fetch
    parse = _section(text, "### 3. Parse Manifest and Scan Exports", "### 4. ")
    branch = parse[parse.index("**Skills module** (`repo_shape: skills-module`)"):]
    assert '`"entries": []`' in branch
    assert branch.index('type: "skill"') < branch.index('type: "menu-code"')
    assert "`brief_description` is the row's `description`, followed by its `display-name`" in branch
    assert "its menu code, display name and `description`, the skill and action it runs" in branch
    assert "(the `_meta` row)" in branch
    inventory = _section(text, "### 4. Build Extraction Inventory", "### 4.5.")
    assert "  repo_shape: " in inventory and "  skills_root: " in inventory
    assert ("**Skills module** (`repo_shape: skills-module`): Unless `{overrides.exports}` is set, "
            "Key Exports lists the skills first, each with its description, then the menu codes, "
            "each with its description, display name and the skill it runs") in _read(COMPILE)
    template = _read(TEMPLATE)
    assert "then each menu code with its description, display name and the skill it runs" in template
    assert "`exports` lists the skill names, then the menu codes" in template


# --------------------------------------------------------------------------
# #609: --description and --exports with --batch halt with exit 2
# --------------------------------------------------------------------------


def test_the_halt_contract_has_the_input_invalid_code():
    text = _read(HALT_CONTRACT)
    codes = _section(text, "## Exit Codes", "## Result Contract")
    [row] = [line for line in codes.splitlines() if line.startswith("| 2 ")]
    for needle in ("input-invalid", "On Activation step 5", "`--description`", "`--exports`", "`--batch`"):
        assert needle in row, needle
    [code_row] = [line for line in text.splitlines() if line.startswith("| `error.code`")]
    assert "`input-invalid`" in code_row
    [phase_row] = [line for line in text.splitlines() if line.startswith("| `phase`")]
    assert "`on-activation`" in phase_row


def test_on_activation_refuses_the_flags_before_the_batch_starts():
    text = _read(SKILL)
    step5 = _section(text, "5. **If `--batch` is set**", "\n\n6. ")
    halt = step5.index("HARD HALT with **exit code 2 (input-invalid)**")
    assert halt < step5.index("load and read `references/batch-mode.md`")
    assert "When `--description` or `--exports` was also passed" in step5
    assert '`phase: "on-activation"`, `error.code: "input-invalid"`' in step5
    assert "no batch summary is written" in step5
    for flag in ("--description", "--exports"):
        [row] = [line for line in text.splitlines() if line.startswith(f"   | `{flag} ")]
        assert "Single-target runs only: On Activation step 5 refuses it with `--batch`." in row


def test_no_file_applies_the_two_flags_to_every_target():
    skill = _read(SKILL)
    batch = _read(BATCH_MODE)
    assert "apply globally to every target" not in skill
    assert "Global overrides apply to every target" not in batch
    [row] = [line for line in skill.splitlines() if line.startswith("   | `--batch <file>`")]
    assert "`--skip-snippet` and `--no-active-pointer` apply to every target in the batch" in row
    assert "`--description` and `--exports` are single-target overrides" in batch
    exit_code = batch[batch.index("## Exit code"):]
    assert "exits with code `2` and writes no batch summary" in exit_code


# --------------------------------------------------------------------------
# #609: the review preview shows one metadata.json line
# --------------------------------------------------------------------------


def test_the_preview_shows_one_metadata_line():
    preview = _section(_read(COMPILE), "### 5. Present Compiled Output for Review", "### 6. ")
    assert "{Display the JSON}" not in preview
    [line] = [line for line in preview.splitlines() if line.startswith("**metadata.json:**")]
    for field in ("version {metadata.version}", "confidence tier {metadata.confidence_tier}",
                  "{metadata.stats.exports_documented} exports documented"):
        assert field in line, field
