"""Create Skill states each rule once and loads branch-only blocks only on their branch (#1147).

- Five reference files hold the blocks one branch needs: the remote-source block and Deferred CCC Discovery
  (extract §2a), Tessl Review's collect loop (validate §6b) and the three shape overrides (compile §2). Each
  is registered, bound in the frontmatter of the stage that loads it, and loaded only on its branch.
- One home per rule: the emit command in each halting file's Rules, `{detectDocsHelper}` resolved once in
  step 5a, the evidence-report blocks and the Remaining Warnings line in skill-sections.md, signature fidelity
  and the angle-bracket rule in compile-assembly-rules.md, the 80-character query rule in ccc-discover.md, and
  `public: false` in compile §1 (and §7's listing of what it left out).
- Stage frontmatter keeps only the comments that carry a rule its body lacks: no probe boilerplate, no
  `# HARD HALT helper` label and no author note.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
CS = REPO / "src" / "skf-create-skill"
REFS = CS / "references"
ASSETS = CS / "assets"
STAGE_FILES = sorted(p for p in REFS.rglob("*.md") if p.read_text(encoding="utf-8").startswith("---\n"))
CREATE_SKILL_FILES = sorted(CS.rglob("*.md"))

# file name -> (the stage that loads it, its frontmatter key)
BRANCH_FILES = {
    "remote-source-access.md": ("extract.md", "remoteSourceAccessData"),
    "tessl-review-collect.md": ("validate.md", "tesslReviewCollectData"),
    "assembly-component-library.md": ("compile.md", "assemblyComponentLibraryData"),
    "assembly-reference-app.md": ("compile.md", "assemblyReferenceAppData"),
    "assembly-whole-language.md": ("compile.md", "assemblyWholeLanguageData"),
}
# The frontmatter comments a stage keeps, each a rule its body does not state.
KEPT_COMMENTS = {
    ("health-check.md", "# `shared/health-check.md` resolves from the SKF module root, not from this step file."),
    ("compile.md", "# Bind `{extractionPatternsData}` to its first existing path: the Relabel Rule's `kind-at` "
                   "reads the recipes there."),
    ("validate.md", "# Bind `{extractionPatternsData}` to its first existing path: the Relabel Rule's `kind-at` "
                    "reads the recipes there."),
    ("validate.md", "# Advisory: with no path, §2 hashes nothing and records `skill_check_fix_changed: unchecked`."),
    ("validate.md", "# Advisory: with no path, §5 records the scan as skipped and continues."),
    ("fetch-docs.md", "# If neither path exists, §5b skips the registry change with a warning."),
}
EMIT_HALT = ('`uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" '
             '--target stderr < "{run_dir}/halt.json"`')


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _split(path: Path) -> tuple[str, str]:
    """(frontmatter, body) of a stage file."""
    text = _read(path)
    end = text.index("\n---\n", 4)
    return text[4:end + 1], text[end + 5:]


def _section(text: str, start: str, end: str | None) -> str:
    assert text.count(start) == 1, start
    begin = text.index(start)
    return text[begin:text.index(end, begin + len(start))] if end else text[begin:]


def _paragraphs_naming(text: str, token: str) -> list[str]:
    return [p for p in text.split("\n\n") if token in p]


# --------------------------------------------------------------------------
# The branch-only files
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(BRANCH_FILES))
def test_each_branch_file_is_registered_and_bound_by_its_stage(name):
    path = REFS / name
    assert path.is_file(), name
    assert not _read(path).startswith("---\n"), "a loaded block has no frontmatter of its own"
    assert "**HARD HALT**" not in _read(path), "a branch file states no halt of its own"
    stage, key = BRANCH_FILES[name]
    frontmatter, body = _split(REFS / stage)
    assert yaml.safe_load(frontmatter)[key] == f"references/{name}"
    assert f"{{{key}}}" in body
    assert f"'{name}'" in _read(REPO / "test" / "test-installation-components.js"), "listed in the install test"
    # no other stage binds it: it is reached only through this stage's key
    for other in STAGE_FILES:
        if other.name != stage:
            assert f"references/{name}" not in _split(other)[0], (other.name, name)


def test_the_remote_block_loads_only_for_a_remote_source_at_forge_tier():
    _, body = _split(REFS / "extract.md")
    two_a = _section(body, "### 2a. Resolve Source Access", "### 2b.")
    loads = _paragraphs_naming(two_a, "{remoteSourceAccessData}")
    assert len(loads) == 2 and len(_paragraphs_naming(body, "{remoteSourceAccessData}")) == 2
    assert loads[0].startswith("**Remote source at Forge, Forge+ or Deep tier:** load `{remoteSourceAccessData}` "
                               "and follow its **Read the Source Into a Private Tree** section")
    assert loads[1].startswith("**Deferred CCC Discovery:** for a remote source at Forge+ or Deep tier, follow the "
                               "**Deferred CCC Discovery** section of `{remoteSourceAccessData}`")
    # a local source, a Quick-tier remote one and a docs-only brief never read it
    local = next(p for p in two_a.split("\n\n") if p.startswith("**Local source, or a Quick-tier remote source:**"))
    assert "{remoteSourceAccessData}" not in local
    # the discovery still runs after the run is recorded
    assert two_a.index("**Record the run**") < two_a.index("**Deferred CCC Discovery:**")
    remote = _read(REFS / "remote-source-access.md")
    assert re.findall(r"^## (.+)$", remote, re.M) == ["Read the Source Into a Private Tree", "Deferred CCC Discovery"]
    # the deferred discovery builds its query by step 2b's rule, the one home of the 80-character cap
    assert ("3. **Construct semantic query:** build it as `references/sub/ccc-discover.md` §3 says (read that "
            "section when it is not in context).") in remote


def test_the_collect_file_loads_only_after_a_review_was_submitted():
    _, body = _split(REFS / "validate.md")
    six_b = _section(body, "### 6b. Tessl Review (optional)", "### 7.")
    [load] = _paragraphs_naming(body, "{tesslReviewCollectData}")
    assert load in six_b
    assert ("When `{tessl_status}` is `pending` or `reviewed`, or the call printed no JSON, load "
            "`{tesslReviewCollectData}`, follow its **Collect the Review** section and continue to §7. Otherwise "
            "add each entry of `{tessl_warnings}` to the "
            "evidence report's Remaining Warnings and continue to §7: the `## Tessl Review` section holds only its "
            "Result line.") in load
    # the missing-helper branch and an `off` review never load it
    assert six_b.index("If neither path exists, set `{tessl_summary}`") < six_b.index("{tesslReviewCollectData}")
    collect = _read(REFS / "tessl-review-collect.md")
    assert re.findall(r"^## (.+)$", collect, re.M) == ["Collect the Review", "Report the Review"]
    assert "`failed: stopped before skf-tessl-review.py reported a result`" in collect
    # a cached answer (`submit` returned `reviewed`) needs no `collect` call, and its suggestions are still marked
    assert "While `{tessl_status}` is `pending`, collect the review" in collect
    assert "When `{tessl_status}` is `reviewed`, resolve `{tesslReviewRules}`" in collect


def test_compile_loads_at_most_one_override_file():
    _, body = _split(REFS / "compile.md")
    two = _section(body, "### 2. Build SKILL.md Content", "### 2a.")
    shape = next(p for p in two.split("\n\n") if p.startswith("**Shape-specific overrides:**"))
    assert "load at most one override file, the one whose gate matches this brief" in shape
    for gate in ("`{assemblyComponentLibraryData}` when `scope.type` is `component-library` and the inventory holds "
                 "a `component_catalog`",
                 "`{assemblyReferenceAppData}` when `scope.type` is `reference-app`",
                 "`{assemblyWholeLanguageData}` for a whole-language reference, gated on "
                 "`assembly_shape: \"whole-language-reference\"`",
                 "When no gate matches, load none and assemble the standard library-export layout unchanged."):
        assert gate in shape, gate
    # the snippet takes the component-library format only when §2 loaded that file
    three = _section(body, "### 3. Build context-snippet.md Content", "### 4.")
    assert "(when §2 loaded `{assemblyComponentLibraryData}`: that file's)" in three
    rules = _read(ASSETS / "compile-assembly-rules.md")
    for heading in ("Component Library Assembly Overrides", "Reference-App Assembly Overrides",
                    "Whole-Language Reference Assembly Overrides"):
        assert heading not in rules, heading
    whole = _read(REFS / "assembly-whole-language.md")
    assert "**Empty-guide guard (check first):**" in whole
    assert "follows rule 7 (Signature fidelity) of `assets/compile-assembly-rules.md`'s Assembly Rules" in whole


# --------------------------------------------------------------------------
# One home per rule
# --------------------------------------------------------------------------


def test_step_doc_sources_resolves_the_helper_once():
    _, body = _split(REFS / "step-doc-sources.md")
    assert body.count("**Resolve `{detectDocsHelper}`**") == 1
    one = _section(body, "### 1. Check for Upstream Doc Detection Results", "### 2.")
    assert one.index("**Resolve `{detectDocsHelper}`**") < one.index("skip to step 3")
    assert body.count("**HARD HALT** (exit code 3, `helper-missing`") == 1


def test_each_halting_file_states_the_emit_command_once():
    for path in [*STAGE_FILES, REFS / "authoritative-files-protocol.md"]:
        text = _read(path)
        if "**HARD HALT**" not in text or path.name == "batch-mode.md":
            continue
        assert text.count(EMIT_HALT) == 1, path.name
        for line in text.splitlines():
            if "**HARD HALT**" in line:
                assert "emit-halt" not in line, (path.name, line[:80])


def test_validate_fills_the_evidence_report_blocks_by_name():
    text = _read(REFS / "validate.md")
    assert not re.search(r"^## (Validation Results|Remaining Warnings|Tessl Review)$", text, re.M)
    sections = _read(ASSETS / "skill-sections.md")
    assert sections.count("\n## Remaining Warnings\n") == 1
    assert ('## Remaining Warnings\n- {each warning from extraction and validation, the security findings among them, '
            'then each entry of {tessl_warnings}; "none" when there is none}\n') in sections


@pytest.mark.parametrize("token, home", [
    ("Signature conflict for `{export_name}`", ASSETS / "compile-assembly-rules.md"),
    ("keep their angle brackets", ASSETS / "compile-assembly-rules.md"),
    ("80 characters", REFS / "sub" / "ccc-discover.md"),
    ("(`form_validation_rules.md`, not `doc2.md`)", ASSETS / "skill-sections.md"),
])
def test_a_shared_rule_has_one_home(token, home):
    holders = [p.relative_to(CS).as_posix() for p in CREATE_SKILL_FILES if token in _read(p)]
    assert holders == [home.relative_to(CS).as_posix()], holders


def test_public_false_is_stated_once_in_compile():
    assert "public: false" not in _read(ASSETS / "compile-assembly-rules.md")
    _, body = _split(REFS / "compile.md")
    holders = [m.start() for m in re.finditer(r"public: false", body)]
    one = body.index("### 1. Load Data Files")
    one_a = body.index("### 1a.")
    seven = body.index("### 7. Build evidence-report.md Content")
    eight = body.index("### 8.")
    inside = [i for i in holders if one <= i < one_a or seven <= i < eight]
    assert inside == holders and len([i for i in holders if one <= i < one_a]) == 1, holders
    assert ("stays out of SKILL.md, `references/` and the provenance map, and out of every section, snippet line "
            "and count below; when the runner gave no surface the rule could read, nothing is marked and an "
            "inventory warning says why") in body


# --------------------------------------------------------------------------
# Frontmatter comments
# --------------------------------------------------------------------------


def test_stage_frontmatter_keeps_only_the_comments_that_carry_a_rule():
    found = set()
    for path in STAGE_FILES:
        frontmatter, _ = _split(path)
        for line in frontmatter.splitlines():
            if line.startswith("#"):
                found.add((path.name, line))
                assert "first existing path wins" not in line and "dev-checkout fallback" not in line, line
                assert "HARD HALT helper" not in line and "147" not in line, line
    assert found == KEPT_COMMENTS, sorted(found ^ KEPT_COMMENTS)
