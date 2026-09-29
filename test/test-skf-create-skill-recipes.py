#!/usr/bin/env python3
"""Every create-skill ast-grep recipe declares the node kind its pattern matches.

ast-grep's JSON output never reports the kind of the node a rule matched, so
create-skill copies a matched export's `ast_node_type` from the `kind` its
recipe declares (#530, deferred items BH4 and EC11). This test:

  - parses every recipe (a ```yaml block holding a mapping with `id`,
    `language` and `rule`) in src/skf-create-skill/references/**/*.md, and
    the inline `find_code_by_rule` example, and checks that each `rule` names
    the kind its pattern matches (beside `any:` for a recipe with several
    patterns);
  - with the ast-grep version package.json's `test:python` pins on PATH
    (`uv run --with ast-grep-cli==0.45.3`), runs each recipe over small
    fixtures and checks the exact matches. They are the matches each recipe
    found before the kinds were added, except `python-public-functions`,
    which ast-grep rejected without a kind ("Rule must specify a set of AST
    kinds to match"). The recipes the spec defers find nothing on 0.45.3:
    `js-exported-functions`, `react-component-functions` (and its
    component-extraction.md twin `react-component-exports`) and
    `rust-public-functions`. With no ast-grep binary, or another version,
    those runs are skipped.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
REFS = REPO / "src" / "skf-create-skill" / "references"
PATTERNS = REFS / "extraction-patterns.md"


def _pinned_version() -> str:
    """The ast-grep-cli version package.json's test:python installs."""
    scripts = json.loads((REPO / "package.json").read_text(encoding="utf-8"))["scripts"]
    match = re.search(r"--with ast-grep-cli==([\w.]+)", scripts["test:python"])
    assert match, "package.json test:python pins no ast-grep-cli version"
    return match.group(1)


PINNED_VERSION = _pinned_version()

FENCE_RE = re.compile(r"^```yaml\n(.*?)^```", re.M | re.S)
INLINE_RULE_RE = re.compile(r'^\s*yaml="(id: [^"]*)",?$', re.M)

# id -> the kind its pattern matches, verified on ast-grep 0.45.3 except for
# the four recipes that match nothing there (js-exported-functions,
# react-component-functions, react-component-exports, rust-public-functions):
# extraction-patterns.md Known Limitation #11 marks their kinds unverified.
KINDS = {
    "python-public-functions": "function_definition",
    "python-public-classes": "class_definition",
    "js-exported-functions": "export_statement",
    "js-exported-constants": "export_statement",
    "js-exported-arrow-functions": "export_statement",
    "js-exported-classes": "export_statement",
    "rust-public-functions": "function_item",
    "go-exported-functions": "function_declaration",
    "react-props-interfaces": "export_statement",
    "react-component-functions": "export_statement",
    "react-component-exports": "export_statement",
    "react-component-arrow-functions": "export_statement",
    "vue-define-props": "call_expression",
}

# --------------------------------------------------------------------------
# Fixtures: the line numbers below are the ones EXPECTED cites.
# --------------------------------------------------------------------------

FIXTURES = {
    "api.py": """\
import functools


def search(query: str, top_k: int = 10) -> list:
    return []


def _private(x):
    return x


async def fetch(url):
    return url


@functools.cache
def cached(key):
    return key


class Client:
    def update(self, value):
        return value

    async def aclose(self):
        return None


class _Hidden:
    pass


class Derived(Client):
    pass


def no_params():
    pass
""",
    "api.ts": """\
export function plain(a: string) {
  return a;
}

export function typed(a: string): number {
  return 1;
}

export async function asyncFn(a: string) {
  return a;
}

export const LIMIT = 10;

export const handler = (req, res) => {
  return res;
};

export const typedArrow = (req: string): number => 1;

export class Store {
  size = 0;
}

export class Box<T> {
  value?: T;
}

export class Child extends Store {
  extra = 1;
}

export interface ButtonProps {
  label: string;
}

export interface Other {
  x: number;
}

export type Alias = string;

export const Button = (props) => {
  return null;
};

const props = defineProps<ButtonProps>();
""",
    "comp.tsx": """\
export function Card(props: CardProps) {
  return <div>{props.title}</div>;
}

export const Panel = (props) => {
  return <section />;
};

export const helper = (x) => x;

export interface CardProps {
  title: string;
}
""",
    "lib.rs": """\
pub fn add(a: i32, b: i32) -> i32 {
    a + b
}

pub fn reset(x: &mut i32) {
    *x = 0;
}

pub(crate) fn internal() {}

fn private() {}
""",
    "main.go": """\
package main

func Exported(a int) int {
\treturn a
}

func Unit(a int) {
}

func unexported() {}

type T struct{}

func (t T) Method() {}
""",
}

# id -> sorted (file, 1-based line, captured name) the recipe matches
EXPECTED = {
    "python-public-functions": [
        ("api.py", 4, "search"), ("api.py", 12, "fetch"), ("api.py", 17, "cached"),
        ("api.py", 22, "update"), ("api.py", 25, "aclose"), ("api.py", 37, "no_params"),
    ],
    "python-public-classes": [("api.py", 21, "Client"), ("api.py", 33, "Derived")],
    "js-exported-functions": [],
    "js-exported-constants": [
        ("api.ts", 13, "LIMIT"), ("api.ts", 15, "handler"),
        ("api.ts", 19, "typedArrow"), ("api.ts", 43, "Button"),
    ],
    "js-exported-arrow-functions": [("api.ts", 15, "handler"), ("api.ts", 43, "Button")],
    "js-exported-classes": [("api.ts", 21, "Store")],
    "rust-public-functions": [],
    "go-exported-functions": [("main.go", 3, "Exported"), ("main.go", 7, "Unit")],
    "react-props-interfaces": [("api.ts", 33, "ButtonProps")],
    "react-component-functions": [],
    "react-component-exports": [],
    "react-component-arrow-functions": [("api.ts", 43, "Button")],
    "vue-define-props": [("api.ts", 47, "ButtonProps")],
}


def _recipes() -> list[tuple[str, str, dict]]:
    """(file relative to REFS, fenced text, parsed recipe) for every recipe."""
    found = []
    for md in sorted(REFS.rglob("*.md")):
        for block in FENCE_RE.findall(md.read_text(encoding="utf-8")):
            # A recipe starts with `id:` after any comment lines; other yaml
            # blocks in the step files are templates, not always valid YAML.
            body = [ln for ln in block.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
            if not body or not body[0].startswith("id:"):
                continue
            doc = yaml.safe_load(block)
            assert isinstance(doc, dict) and {"id", "language", "rule"} <= set(doc), block
            found.append((md.relative_to(REFS).as_posix(), block, doc))
    return found


RECIPES = _recipes()


def _recipe_id(item: tuple[str, str, dict]) -> str:
    return f"{item[0]}:{item[2]['id']}"


def test_every_recipe_is_known() -> None:
    ids = [doc["id"] for _, _, doc in RECIPES]
    assert len(ids) == 14  # 12 in extraction-patterns.md, 2 in component-extraction.md
    assert set(ids) == set(KINDS), f"a recipe without a verified kind: {sorted(set(ids) ^ set(KINDS))}"


@pytest.mark.parametrize("item", RECIPES, ids=_recipe_id)
def test_recipe_rule_names_its_kind(item: tuple[str, str, dict]) -> None:
    _, _, doc = item
    rule = doc["rule"]
    assert rule.get("kind") == KINDS[doc["id"]]
    assert "pattern" in rule or "any" in rule


def test_inline_find_code_by_rule_example_matches_the_python_recipe() -> None:
    (inline,) = INLINE_RULE_RE.findall(PATTERNS.read_text(encoding="utf-8"))
    doc = yaml.safe_load(inline.replace("\\n", "\n"))
    assert doc["rule"]["kind"] == "function_definition"
    (python,) = [d for f, _, d in RECIPES if d["id"] == "python-public-functions"]
    assert doc["rule"] == python["rule"]
    assert doc["constraints"] == python["constraints"]


def test_cli_template_prints_the_recipe_kind() -> None:
    text = PATTERNS.read_text(encoding="utf-8")
    assert "KIND = '{node_kind}'" in text
    assert "print(f'[AST:{f}:L{ln}] kind={KIND} {sig}')" in text


# --------------------------------------------------------------------------
# Real ast-grep runs
# --------------------------------------------------------------------------


def _ast_grep() -> str | None:
    exe = shutil.which("ast-grep")
    if exe is None:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True,
                             timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return exe if out.returncode == 0 and out.stdout.split()[-1:] == [PINNED_VERSION] else None


AST_GREP = _ast_grep()


@pytest.fixture(scope="module")
def fixture_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("recipes")
    for name, text in FIXTURES.items():
        (root / name).write_text(text, encoding="utf-8")
    return root


def _matches(exe: str, block: str, root: Path, rule_dir: Path) -> list[tuple[str, int, str]]:
    rule = rule_dir / "recipe.yml"
    rule.write_text(block, encoding="utf-8")
    result = subprocess.run(
        [exe, "scan", "-r", str(rule), "--json=stream", "."],
        capture_output=True, text=True, encoding="utf-8", check=False, cwd=root,
    )
    assert result.returncode == 0, result.stderr
    found = []
    for line in result.stdout.splitlines():
        match = json.loads(line)
        single = match.get("metaVariables", {}).get("single", {})
        name = (single.get("NAME") or single.get("TYPE") or {}).get("text")
        found.append((Path(match["file"]).name, match["range"]["start"]["line"] + 1, name))
    return sorted(found)


@pytest.mark.skipif(AST_GREP is None, reason=f"no ast-grep {PINNED_VERSION} binary on PATH")
@pytest.mark.parametrize("item", RECIPES, ids=_recipe_id)
def test_recipe_matches_on_fixtures(item: tuple[str, str, dict], fixture_dir: Path, tmp_path: Path) -> None:
    _, block, doc = item
    assert _matches(AST_GREP, block, fixture_dir, tmp_path) == EXPECTED[doc["id"]]


@pytest.mark.skipif(AST_GREP is None, reason=f"no ast-grep {PINNED_VERSION} binary on PATH")
@pytest.mark.parametrize("item", RECIPES, ids=_recipe_id)
def test_another_kind_loses_the_matches(item: tuple[str, str, dict], fixture_dir: Path, tmp_path: Path) -> None:
    """The declared kind is the matched node's: a neighbouring kind (the
    declaration inside an export, the call's statement) matches nothing."""
    _, block, doc = item
    if not EXPECTED[doc["id"]]:
        pytest.skip("the recipe finds nothing on 0.45.3 (deferred)")
    other = {
        "function_definition": "decorated_definition",
        "class_definition": "decorated_definition",
        "export_statement": "lexical_declaration",
        "function_declaration": "method_declaration",
        "call_expression": "expression_statement",
    }[KINDS[doc["id"]]]
    wrong = block.replace(f"kind: {KINDS[doc['id']]}", f"kind: {other}", 1)
    assert wrong != block
    assert _matches(AST_GREP, wrong, fixture_dir, tmp_path) == []
