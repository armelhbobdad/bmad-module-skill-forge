#!/usr/bin/env python3
"""Tests for skf-skills-module.py: the skills root of a repository listing,
and the exports of a skills module from its staged files (#527, #592).

The rule that picks the skills root was prose quick-extract §1.5 had the
model apply, restated as code in test-skf-quick-skill-contract.py; it now
lives in the helper, and the listings of real repository layouts below
(the ones that test used) state the skills root it gives each, the folder
a library's no-export note names, and that a library which ships one
skill stays a library.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

REPO = Path(__file__).resolve().parent.parent
HELPER = REPO / "src" / "shared" / "scripts" / "skf-skills-module.py"

spec = importlib.util.spec_from_file_location("skf_skills_module", HELPER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class Layout(NamedTuple):
    paths: tuple[str, ...]
    package_json: dict | None
    root: str | None  # the skills root sniff picks; None: the shape stays library
    skills: tuple[str, ...] = ()
    suggestion: str | None = None  # the folder the no-export note names, for a library
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
        {"name": "some-module", "main": "index.js"}, ".", ("agents/helper", "workflows/plan/make-plan")),
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


@pytest.mark.parametrize("name", list(LAYOUTS))
def test_sniff_picks_the_skills_root_of_real_layouts(name):
    layout = LAYOUTS[name]
    out = mod.sniff(list(layout.paths), layout.package_json, layout.scope_hint)
    if layout.root is None:
        assert out["skills_module"] is False
        assert (out["skills_root"], out["skill_folders"]) == (None, [])
        if layout.scope_hint is None:
            assert out["suggested_scope"] == layout.suggestion
    else:
        assert out["skills_module"] is True
        assert (out["skills_root"], out["skill_folders"]) == (layout.root, list(layout.skills))
        assert out["suggested_scope"] is None


def test_the_candidates_say_why_each_counts():
    out = mod.sniff(list(BUILDER), {"name": "bmad-builder", "main": "", "private": True}, None)
    assert out["candidates"] == [
        {"folder": "samples", "module_root": False, "skill_folders": 7, "counts": True},
        {"folder": "skills", "module_root": True, "skill_folders": 5, "counts": True},
    ]
    assert out["module_root"] is True
    bmm = mod.sniff(list(BMM_612), BMM_612_PACKAGE, None)
    assert {c["folder"]: c["counts"] for c in bmm["candidates"]} == {"web-bundles": False}


def test_a_root_package_json_not_read_counts_as_shipping_code():
    paths = ["README.md", "package.json", "skills/a/SKILL.md", "skills/b/SKILL.md"]
    assert mod.sniff(paths, None, None)["skills_module"] is False
    assert any("package.json was not read" in w for w in mod.sniff(paths, None, None)["warnings"])
    assert mod.sniff(paths, {"name": "x", "private": True}, None)["skills_root"] == "skills"


@pytest.mark.parametrize("text", ['{"name": "x", "main": "index.js",', "[]", "\xff\xfe"],
                         ids=["truncated-json", "not-an-object", "not-utf8"])
def test_a_root_package_json_that_cannot_be_read_counts_as_shipping_code(tmp_path, text):
    """A malformed manifest must not read as one that declares no main, exports, bin or workspaces."""
    staged = tmp_path / "package.json"
    staged.write_bytes(text.encode("latin-1"))
    assert mod._package_json(str(staged)) is None
    tree = {"status": "ok", "tree": ["README.md", "package.json", "skills/a/SKILL.md", "skills/b/SKILL.md"],
            "truncated": False}
    (tmp_path / "tree.json").write_text(json.dumps(tree), encoding="utf-8")
    out = _cli("sniff", "--tree-file", str(tmp_path / "tree.json"), "--package-json", str(staged))
    assert out.returncode == 0, out.stderr
    sniffed = json.loads(out.stdout)
    assert sniffed["skills_module"] is False
    assert any("package.json was not read" in w for w in sniffed["warnings"])


def test_the_listing_facts():
    paths = ["README.md", "readme.zh.md", "LICENSE", "package.json", "src/index.ts", "src/templates/a.hbs",
             "bin/cli.js", "docs/assets/logo.png", "skills/a/SKILL.md", "skills/a/scripts/run.py"]
    out = mod.sniff(paths, {"name": "x", "main": "dist/index.js"}, None, truncated=True)
    assert out["root_files"] == ["LICENSE", "README.md", "package.json", "readme.zh.md"]
    assert out["readme"] == "README.md"
    assert out["asset_dirs"] == ["bin", "docs/assets", "skills/a/scripts", "src/templates"]
    assert out["asset_dir_count"] == 4 and out["skill_md_count"] == 1
    assert out["truncated"] is True and any("cut short" in w for w in out["warnings"])
    scoped = mod.sniff(paths, None, "src/")
    assert scoped["asset_dirs"] == ["src/templates"]


@pytest.mark.parametrize("files,readme", [
    (["readme.md", "README.rst"], "readme.md"),
    (["README.rst", "README"], "README"),
    (["Readme.txt"], "Readme.txt"),
    (["READ_THIS.md"], None),
], ids=["lowercase-md", "then-by-name", "mixed-case", "none"])
def test_the_readme_is_the_root_markdown_readme_first(files, readme):
    assert mod.sniff(files + ["x/y.py"], None, None)["readme"] == readme


def test_the_fetch_list_names_each_skill_md_then_the_module_help():
    paths = list(BUILDER)
    out = mod.sniff(paths, {"name": "bmad-builder", "main": ""}, None)
    assert mod.fetch_list(out, paths) == [f"{f}/SKILL.md" for f in BUILDER_SKILLS] + ["skills/module-help.csv"]
    anthropic = list(LAYOUTS["anthropics/skills: no manifest, and the folder with the most skill folders wins"].paths)
    out = mod.sniff(anthropic, None, None)
    assert mod.fetch_list(out, anthropic) == ["skills/docx/SKILL.md", "skills/pdf/SKILL.md",
                                             "skills/skill-creator/SKILL.md"]
    root = list(LAYOUTS["module files at the repository root"].paths)
    out = mod.sniff(root, {"name": "some-module", "main": "index.js"}, None)
    assert mod.fetch_list(out, root)[-1] == "module-help.csv"
    assert mod.fetch_list(mod.sniff(list(BMM_HEAD), None, None), list(BMM_HEAD)) == []


# --------------------------------------------------------------------------
# extract
# --------------------------------------------------------------------------


ALPHA = ("---\nname: alpha\ndescription: >\n  Builds alpha things.\n  Use when alpha's needed.\n---\n\n"
         "# Alpha\n\n---\n\nname: not-frontmatter\n")
CSV = (
    "module,skill,display-name,menu-code,description,action,args,phase,preceded-by,followed-by,required\n"
    "Demo,_meta,,,,,,,,,false\n"
    'Demo,alpha,Build Alpha,BA,"Create, edit, or rebuild an alpha.",build,"{-H: headless}",anytime,,alpha:check,false\n'
    "Demo,beta,Beta Helper,,Helps with beta.,,,anytime,alpha,,false\n"
    "Demo,,Orphan,OR,No skill.,,,,,,false\n"
)


def _stage(root: Path, files: dict[str, str | bytes]) -> None:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body if isinstance(body, bytes) else body.encode("utf-8"))


def test_extract_lists_the_skills_then_the_menu_codes(tmp_path):
    _stage(tmp_path, {"skills/alpha/SKILL.md": ALPHA.replace("\n", "\r\n"),
                      "skills/beta/SKILL.md": "---\nname: beta\ndescription: Helps.\n---\n# Beta\n",
                      "skills/module-help.csv": CSV})
    sniffed = {"skills_root": "skills", "skill_folders": ["skills/alpha", "skills/beta"]}
    out = mod.extract(sniffed, tmp_path, name="demo")
    assert out["exports"] == [
        {"name": "alpha", "type": "skill", "brief_description": "Builds alpha things. Use when alpha's needed.",
         "source_file": "skills/alpha/SKILL.md"},
        {"name": "beta", "type": "skill", "brief_description": "Helps.", "source_file": "skills/beta/SKILL.md"},
        {"name": "BA", "type": "menu-code",
         "brief_description": "Create, edit, or rebuild an alpha. (Build Alpha) runs alpha (build)",
         "source_file": "skills/module-help.csv"},
    ]
    assert [p["skill"] for p in out["usage_patterns"]] == ["alpha", "beta"]
    assert out["usage_patterns"][0] == {"menu_code": "BA", "display_name": "Build Alpha",
                                        "description": "Create, edit, or rebuild an alpha.", "skill": "alpha",
                                        "action": "build", "args": "{-H: headless}", "preceded_by": None,
                                        "followed_by": "alpha:check"}
    assert (out["confidence"], out["skills"], out["menu_codes"]) == ("high", 2, 1)
    assert out["package_name"] == "demo" and out["warnings"] == []


def test_extract_names_a_skill_after_its_folder_when_frontmatter_falls_short(tmp_path):
    _stage(tmp_path, {"skills/beta/SKILL.md": "# Beta, no frontmatter\n"})
    sniffed = {"skills_root": "skills", "skill_folders": ["skills/beta", "skills/gamma"]}
    out = mod.extract(sniffed, tmp_path)
    assert [e["name"] for e in out["exports"]] == ["beta", "gamma"]
    assert out["confidence"] == "medium"
    assert any("skills/gamma/SKILL.md: not staged" in w for w in out["warnings"])
    assert any("skills/beta/SKILL.md: the frontmatter gives no name" in w for w in out["warnings"])


def test_extract_keeps_the_package_fields_of_the_manifest(tmp_path):
    _stage(tmp_path, {"agents/alpha/SKILL.md": ALPHA, "module-help.csv": CSV})
    package = {"language": "javascript", "package_name": "demo-module", "version": "1.2.0",
               "description": "A module.", "dependencies": ["yaml"], "exports": [], "warnings": ["w1"]}
    out = mod.extract({"skills_root": ".", "skill_folders": ["agents/alpha"]}, tmp_path, package, "ignored")
    assert (out["package_name"], out["version"], out["language"]) == ("demo-module", "1.2.0", "javascript")
    assert out["dependencies"] == ["yaml"] and out["warnings"] == ["w1"]
    assert out["exports"][-1]["source_file"] == "module-help.csv"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HELPER), *args], capture_output=True, text=True,
                          encoding="utf-8", check=False, timeout=60)


def test_the_cli_runs_sniff_then_extract_on_staged_files(tmp_path):
    tree = {"status": "ok", "tree": ["README.md", "package.json", "skills/alpha/SKILL.md",
                                     "skills/module-help.csv", "skills/module.yaml"], "truncated": False}
    (tmp_path / "tree.json").write_text(json.dumps(tree), encoding="utf-8")
    src = tmp_path / "src"
    _stage(src, {"package.json": '{"name": "demo", "private": true}', "skills/alpha/SKILL.md": ALPHA,
                 "skills/module-help.csv": CSV})
    sniffed = _cli("sniff", "--tree-file", str(tmp_path / "tree.json"), "--package-json", str(src / "package.json"),
                   "--fetch-list", str(tmp_path / "fetch.txt"))
    assert sniffed.returncode == 0, sniffed.stderr
    (tmp_path / "sniff.json").write_text(sniffed.stdout, encoding="utf-8")
    assert json.loads(sniffed.stdout)["skills_root"] == "skills"
    assert (tmp_path / "fetch.txt").read_text(encoding="utf-8") == "skills/alpha/SKILL.md\nskills/module-help.csv\n"
    out = _cli("extract", "--sniff", str(tmp_path / "sniff.json"), "--source-root", str(src), "--name", "demo")
    assert out.returncode == 0, out.stderr
    assert [e["name"] for e in json.loads(out.stdout)["exports"]] == ["alpha", "BA"]


def test_the_cli_refuses_a_failed_listing_and_a_foreign_sniff_file(tmp_path):
    (tmp_path / "tree.json").write_text('{"status": "unavailable", "message": "gh is not logged in", "tree": []}',
                                        encoding="utf-8")
    out = _cli("sniff", "--tree-file", str(tmp_path / "tree.json"))
    assert out.returncode == 2 and "gh is not logged in" in json.loads(out.stderr)["message"]
    (tmp_path / "other.json").write_text('{"language": "python"}', encoding="utf-8")
    out = _cli("extract", "--sniff", str(tmp_path / "other.json"), "--source-root", str(tmp_path))
    assert out.returncode == 2 and "not skf-skills-module.py sniff output" in json.loads(out.stderr)["message"]
