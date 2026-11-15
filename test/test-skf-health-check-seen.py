#!/usr/bin/env python3
"""Tests for skf-health-check-seen.py: the shared health check's fingerprints
and seen-issue cache (#1122).

src/shared/health-check.md used to have the model hash both fingerprints
through a sha1sum, shasum or python chain, read $HOME/.skf/health-check-seen.json,
map a bounded `gh issue view` through five branches and two legacy demotions,
and merge its record back by hand. The helper owns all of that now, so these
tests pin its behaviour instead of the prose:

- fingerprint: the golden hashes, and the rules that exit 2. The workflow
  and step file in one form whatever the install (a helper copied under a
  fake _bmad/skf/ tree prints what the src/ one prints), the 15 workflows
  the helper names, the slug of every heading of every step file, and the
  section and defect key it derives from a --stdin heading and name.
- lookup: every branch, the legacy demotions, a cache that is not usable,
  the regression's opening line, --repo, with the gh call replaced in the
  loaded module (no test runs the gh a developer has installed), and end to
  end against a fake gh first on PATH (POSIX only: the fake is a script).
- record: the merge, the never-downgraded resolved record and the
  --regression call that replaces one, a resolved record recorded with the
  helper, a corrupt cache set aside, the lock, the failure paths, the
  Windows rename retry, and eight parallel writers.
- version: each install layout, and no version without blocking.

No test reads or writes the real $HOME/.skf: every call names its cache, or
runs with HOME pointed at a temporary folder.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
HELPER = REPO / "src" / "shared" / "scripts" / "skf-health-check-seen.py"
RUN_LOCK = REPO / "src" / "shared" / "scripts" / "skf-run-lock.py"
QUICK_METADATA = REPO / "src" / "shared" / "scripts" / "skf-render-quick-metadata.py"
SHARED_HEALTH_CHECK = REPO / "src" / "shared" / "health-check.md"
HEALTH_CHECK_REPO = "armelhbobdad/bmad-module-skill-forge"

# The worked example of the fingerprint prose test: two different defects in the only section of one step file.
SAMPLE = {"severity": "gap", "workflow": "skf-test-skill",
          "step_file": "src/skf-test-skill/references/inventory-contract.md",
          "section": "documented-inventory-contract"}
FP_A, FP_B, LEGACY = "fp-a54e7a6", "fp-ed2bb67", "fp-eb2d6f2"
# What --stdin gives for the sample: the step file's only heading, and the names of the two defects.
HEADING = "# Documented Inventory Contract"
NAMES = {FP_A: "const holding function", FP_B: "shared text"}
OTHER_FP = "fp-1234567"
URL = "https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1"
DAY = "2026-11-12"
# JSON nested past the parser's depth: json.loads raises RecursionError, not ValueError.
DEEP = b"[" * 200_000

_MODULE = None


def _mod():
    """Load the helper lazily, so a missing helper fails each test, not collection."""
    global _MODULE
    if _MODULE is None:
        assert HELPER.is_file(), f"missing helper: {HELPER}"
        spec = importlib.util.spec_from_file_location("skf_health_check_seen", HELPER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _MODULE = module
    return _MODULE


def _cli(*args: str, env: dict | None = None, timeout: float = 60, stdin: bytes | None = None,
         helper: Path = HELPER) -> tuple[int, str, str]:
    proc = subprocess.run([sys.executable, str(helper), *args], capture_output=True, env=env, timeout=timeout,
                          input=stdin if stdin is not None else b"")
    return proc.returncode, proc.stdout.decode("utf-8"), proc.stderr.decode("utf-8")


def _fingerprint_args(**over: str) -> list[str]:
    values = {**SAMPLE, "defect_key": "const-holding-function", **over}
    return ["fingerprint", "--severity", values["severity"], "--workflow", values["workflow"],
            "--step-file", values["step_file"], "--section", values["section"], "--defect-key", values["defect_key"]]


def _stdin_args(step_file: str = SAMPLE["step_file"], workflow: str = SAMPLE["workflow"],
                severity: str = SAMPLE["severity"]) -> list[str]:
    return ["fingerprint", "--severity", severity, "--workflow", workflow, "--step-file", step_file, "--stdin"]


def _names(heading: str = HEADING, name: str = NAMES[FP_A], **extra) -> bytes:
    return json.dumps({"section_heading": heading, "defect_name": name, **extra}).encode("utf-8")


def _sample_out(fp: str, key: str) -> dict:
    """What fingerprint prints for the sample with that key."""
    keyed = f"gap|skf-test-skill|{SAMPLE['step_file']}|{SAMPLE['section']}|{key}"
    return {"fp": fp, "legacy_fp": LEGACY, "tuple": keyed, "step_file": SAMPLE["step_file"],
            "section_slug": SAMPLE["section"], "defect_key": key}


def _found(verdict: str, record, matched_on: str | None, opening: str | None = None) -> dict:
    return {"verdict": verdict, "record": record, "matched_on": matched_on, "opening_line": opening}


UNSEEN = _found("unseen", None, None)


def _write_cache(path: Path, data) -> Path:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def _live(action: str = "created", url: str | None = URL) -> dict:
    record = {"action": action, "date": "2026-10-01"}
    if url is not None:
        record["issue_url"] = url
    return record


@pytest.fixture
def no_gh(monkeypatch):
    """gh_issue_state replaced by a recorder that fails the test when called."""
    calls = []

    def fake(issue_url, timeout=None):
        calls.append(issue_url)
        raise AssertionError(f"gh must not run here, got {issue_url!r}")

    monkeypatch.setattr(_mod(), "gh_issue_state", fake)
    return calls


@pytest.fixture
def gh_answer(monkeypatch):
    """gh_issue_state replaced by one that answers with the value set on it, recording each URL."""
    state = {"answer": None, "calls": []}

    def fake(issue_url, timeout=None):
        state["calls"].append(issue_url)
        return state["answer"]

    monkeypatch.setattr(_mod(), "gh_issue_state", fake)
    return state


# --------------------------------------------------------------------------
# fingerprint
# --------------------------------------------------------------------------


class TestFingerprint:
    def test_the_golden_fingerprints(self):
        """The prose test's worked example: the key keeps two defects of one section apart."""
        a = _mod().fingerprint(key="const-holding-function", **SAMPLE)
        b = _mod().fingerprint(key="shared-text", **SAMPLE)
        assert a == _sample_out(FP_A, "const-holding-function")
        assert b == _sample_out(FP_B, "shared-text")

    def test_the_hash_is_sha1_over_the_joined_fields(self):
        """Cross-checked with hashlib on the setup test's key, so the field order and the separator show here."""
        key = "bug|skf-setup|src/skf-setup/references/report.md|emit-headless-json-envelope|result-envelope"
        out = _mod().fingerprint("bug", "skf-setup", "references/report.md", "emit-headless-json-envelope",
                                 "result-envelope")
        assert out["fp"] == "fp-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:7]
        legacy = key.rsplit("|", 1)[0]
        assert out["legacy_fp"] == "fp-" + hashlib.sha1(legacy.encode("utf-8")).hexdigest()[:7]
        assert out["tuple"] == key

    def test_the_cli_prints_the_fingerprints_and_the_fields_they_hash(self):
        code, out, err = _cli(*_fingerprint_args(defect_key="shared-text"))
        assert code == 0, err
        assert json.loads(out) == _sample_out(FP_B, "shared-text")
        assert err == ""

    @pytest.mark.parametrize("over, rule", [
        ({"severity": "nit"}, "--severity"),
        ({"defect_key": "one-two-three-four-five"}, "--defect-key"),
        ({"defect_key": "Shared-Text"}, "--defect-key"),
        ({"section": "Missing Path"}, "--section"),
        ({"section": "missing--path"}, "--section"),
        ({"workflow": "skf|test-skill"}, "--workflow"),
        ({"workflow": ""}, "--workflow"),
        ({"step_file": "references/a.md\nb"}, "--step-file"),
        ({"step_file": "references/a.md|b"}, "--step-file"),
        ({"step_file": ""}, "--step-file"),
        # `$` alone matches before a final newline: each rule is a fullmatch.
        ({"section": "documented-inventory-contract\n"}, "--section"),
        ({"defect_key": "shared-text\n"}, "--defect-key"),
    ])
    def test_a_value_that_breaks_its_rule_exits_2(self, over, rule):
        code, out, err = _cli(*_fingerprint_args(**over))
        assert code == 2
        assert out == ""
        error = json.loads(err)
        assert error["status"] == "error" and rule in error["message"]

    def test_a_four_word_key_is_allowed(self):
        code, out, err = _cli(*_fingerprint_args(defect_key="very-long-helper-name"))
        assert code == 0, err
        assert json.loads(out)["legacy_fp"] == LEGACY


# --------------------------------------------------------------------------
# fingerprint: one form whatever the install, and the heading and name it derives
# --------------------------------------------------------------------------

# The two slugs each of these files gives two headings: a heading of either names one of them, so a defect there may
# share a section fingerprint with one in the other section. Every other step file's slugs name one section each.
KNOWN_DUPLICATE_SLUGS = {
    "skf-create-skill/references/extraction-patterns.md": {"ast-grep-patterns", "confidence", "strategy"},
    "skf-setup/references/tier-rules.md": {"forge-tier"},
}


def _chaining_workflows() -> list[str]:
    """The skf-* folders whose references/health-check.md loads the shared health check."""
    return sorted(path.parent.parent.name for path in SRC.glob("skf-*/references/health-check.md")
                  if "shared/health-check.md" in path.read_text(encoding="utf-8"))


class TestFixedForm:
    @pytest.mark.parametrize("step_file", [
        "inventory-contract.md",
        "references/inventory-contract.md",
        "src/skf-test-skill/references/inventory-contract.md",
        "_bmad/skf/skf-test-skill/references/inventory-contract.md",
        "/home/someone/project/_bmad/skf/skf-test-skill/references/inventory-contract.md",
        "C:\\work\\project\\_bmad\\skf\\skf-test-skill\\references\\inventory-contract.md",
    ])
    def test_every_form_of_the_step_file_gives_one_fingerprint(self, step_file):
        """A checkout, a CLI install and a plugin name the step file differently: one fingerprint for all."""
        for flags, stdin in ((_fingerprint_args(step_file=step_file), None), (_stdin_args(step_file), _names())):
            code, out, err = _cli(*flags, stdin=stdin)
            assert code == 0, err
            assert json.loads(out) == _sample_out(FP_A, "const-holding-function")

    def test_workflows_are_the_folders_that_end_in_the_health_check(self):
        assert sorted(_mod().WORKFLOWS) == _chaining_workflows()
        assert len(_mod().WORKFLOWS) == 15 and "skf-forger" not in _mod().WORKFLOWS

    @pytest.mark.parametrize("workflow", ["create-skill", "skf-forger", "skf-nope", "Test Skill", "SKF-TEST-SKILL"])
    def test_a_workflow_that_is_not_one_of_the_15_exits_2_naming_them(self, workflow):
        code, out, err = _cli(*_fingerprint_args(workflow=workflow))
        assert code == 2 and out == ""
        message = json.loads(err)["message"]
        assert "--workflow" in message
        assert all(name in message for name in _mod().WORKFLOWS)

    @pytest.mark.parametrize("step_file", [
        "nope.md",
        "references/",
        "..",
        "health-check.md",  # the relay: it only loads the shared health check
        "src/skf-test-skill/references/health-check.md",
        "src/skf-create-skill/references/inventory-contract.md",  # the name exists here, the path is another skill's
        "_bmad/skf/skf-forger/references/inventory-contract.md",
        "src/skf-test-skill/SKILL.md",
        # Letter case counts on every OS: a file system that ignores it would otherwise hash another name.
        "Inventory-Contract.md",
        "src/skf-test-skill/references/INVENTORY-CONTRACT.MD",
        "Health-Check.md",
        "HEALTH-CHECK.MD",
    ])
    def test_a_step_file_that_is_not_the_workflows_exits_2(self, step_file):
        for flags, stdin in ((_fingerprint_args(step_file=step_file), None), (_stdin_args(step_file), _names())):
            code, out, err = _cli(*flags, stdin=stdin)
            assert code == 2 and out == ""
            assert "--step-file" in json.loads(err)["message"]

    @pytest.mark.parametrize("step_file", [
        "/home/skf-user/skf-work/_bmad/skf/skf-test-skill/references/inventory-contract.md",
        # Only the folder that holds references/ names the step file's skill: one further up is the user's.
        "/home/u/skf-setup/proj/_bmad/skf/skf-test-skill/references/inventory-contract.md",
        "/home/u/skf-create-skill/src/skf-test-skill/references/inventory-contract.md",
    ])
    def test_a_folder_above_the_skill_does_not_matter(self, step_file):
        code, out, err = _cli(*_stdin_args(step_file), stdin=_names())
        assert code == 0, err
        assert json.loads(out)["fp"] == FP_A

    @pytest.mark.parametrize("relay", ["health-check.md", "Health-Check.md", "HEALTH-CHECK.MD"])
    def test_the_relay_is_refused_in_any_letter_case(self, relay):
        code, _, err = _cli(*_stdin_args(relay), stdin=_names())
        assert code == 2 and "relay" in json.loads(err)["message"]

    def test_a_step_file_borrowed_from_another_workflow_is_that_workflows(self):
        """Update Skill loads Create Skill's extraction-patterns.md: the workflow is the one whose references/ holds
        it, so the finding gets one fingerprint whichever workflow was running."""
        step_file = "_bmad/skf/skf-create-skill/references/extraction-patterns.md"
        names = _names("# Extraction Patterns by Tier", "ast-grep pattern")
        code, out, err = _cli(*_stdin_args(step_file, workflow="skf-update-skill"), stdin=names)
        assert code == 2 and out == ""
        message = json.loads(err)["message"]
        assert ("is in skf-create-skill/references/, so --workflow is skf-create-skill: the workflow whose references/ "
                "folder holds the step file") in message
        assert " or " not in message.split(": ", 1)[1], "one fix, not two"
        code, out, err = _cli(*_stdin_args(step_file, workflow="skf-create-skill"), stdin=names)
        assert code == 0, err
        assert json.loads(out)["step_file"] == "src/skf-create-skill/references/extraction-patterns.md"

    def test_a_copy_under_an_installed_tree_prints_what_the_checkout_prints(self, tmp_path):
        """The helper finds the step files from its own place: a CLI install's _bmad/skf/, never {project-root}."""
        module = tmp_path / "project" / "_bmad" / "skf"
        (module / "shared" / "scripts").mkdir(parents=True)
        copied = module / "shared" / "scripts" / HELPER.name
        copied.write_bytes(HELPER.read_bytes())
        references = module / "skf-test-skill" / "references"
        references.mkdir(parents=True)
        (references / "inventory-contract.md").write_bytes(
            (SRC / "skf-test-skill" / "references" / "inventory-contract.md").read_bytes())
        env = {**os.environ}
        for step_file in ("inventory-contract.md", "_bmad/skf/skf-test-skill/references/inventory-contract.md"):
            installed = _cli(*_stdin_args(step_file), stdin=_names(), helper=copied, env=env)
            checkout = _cli(*_stdin_args(step_file), stdin=_names(), env=env)
            assert installed[0] == checkout[0] == 0, installed[2] + checkout[2]
            assert json.loads(installed[1]) == json.loads(checkout[1]) == _sample_out(FP_A, "const-holding-function")
        # Another step file is not in that tree, though the checkout has it.
        code, _, err = _cli(*_stdin_args("report.md"), stdin=_names(), helper=copied)
        assert code == 2 and "--step-file" in json.loads(err)["message"]

    @pytest.mark.parametrize("fp, name", sorted(NAMES.items()))
    @pytest.mark.parametrize("heading", [HEADING, "Documented Inventory Contract",
                                         "  #   Documented Inventory Contract  ", "# Documented Inventory Contract #"])
    def test_stdin_gives_the_pinned_fingerprints(self, fp, name, heading):
        code, out, err = _cli(*_stdin_args(), stdin=_names(heading, name))
        assert code == 0, err
        assert json.loads(out) == _sample_out(fp, NAMES[fp].replace(" ", "-"))

    def test_the_spec_example_heading_and_name(self, tmp_path):
        """A numbered heading loses its numbering and a script's path, extension and line go."""
        module = tmp_path / "src"
        (module / "shared" / "scripts").mkdir(parents=True)
        copied = module / "shared" / "scripts" / HELPER.name
        copied.write_bytes(HELPER.read_bytes())
        (module / "skf-test-skill" / "references").mkdir(parents=True)
        (module / "skf-test-skill" / "references" / "report.md").write_text(
            "# Report\n\n### 5a. Live-Submit Path: X\n", encoding="utf-8")
        code, out, err = _cli(*_stdin_args("report.md", severity="bug"), helper=copied,
                              stdin=_names("### 5a. Live-Submit Path: X", "scripts/gate_eval.py:42"))
        assert code == 0, err
        payload = json.loads(out)
        assert (payload["section_slug"], payload["defect_key"]) == ("live-submit-path-x", "gate-eval")
        keyed = "bug|skf-test-skill|src/skf-test-skill/references/report.md|live-submit-path-x|gate-eval"
        assert payload["tuple"] == keyed
        assert payload["fp"] == "fp-" + hashlib.sha1(keyed.encode("utf-8")).hexdigest()[:7]

    @pytest.mark.parametrize("heading", ["documented inventory contract", "DOCUMENTED INVENTORY CONTRACT",
                                         "## Documented-Inventory Contract!", "documented-inventory-contract",
                                         "1. Documented Inventory Contract"])
    def test_a_heading_in_another_case_or_punctuation_names_the_same_section(self, heading):
        """Copied in another form, the heading still gives its section's slug, so the step need not fall back on the
        coarser heading that encloses it."""
        code, out, err = _cli(*_stdin_args(), stdin=_names(heading))
        assert code == 0, err
        assert json.loads(out) == _sample_out(FP_A, "const-holding-function")

    @pytest.mark.parametrize("heading", ["# !!", "###", "-- --"])
    def test_a_heading_that_yields_no_slug_exits_2(self, heading):
        code, out, err = _cli(*_stdin_args(), stdin=_names(heading))
        assert code == 2 and out == ""
        assert "yields no slug" in json.loads(err)["message"]

    @pytest.mark.parametrize("heading", ["Documented Inventory", "## Elsewhere",
                                         "Live-Submit Path: Compute Fingerprint and Dedup"])
    def test_a_heading_that_is_not_the_step_files_own_exits_2(self, heading):
        code, out, err = _cli(*_stdin_args(), stdin=_names(heading))
        assert code == 2 and out == ""
        message = json.loads(err)["message"]
        assert "section_heading" in message and SAMPLE["step_file"] in message

    def test_a_heading_line_in_fenced_code_or_frontmatter_is_no_heading(self, tmp_path):
        step = tmp_path / "step.md"
        step.write_text("---\n# front: matter\n---\n# Step 5\n\n```markdown\n# Deferred Work\n```\n\n~~~~\n"
                        "## In tildes\n~~~~\n## Route on the verdict ##\n", encoding="utf-8")
        assert _mod()._stage_headings(step) == ["Step 5", "Route on the verdict"]

    @pytest.mark.parametrize("heading, slug", [
        ("### 5a. Live-Submit Path: Compute Fingerprint and Dedup", "live-submit-path-compute-fingerprint-and-dedup"),
        ("### 5a-ii. If no matching open issue exists", "if-no-matching-open-issue-exists"),
        ("### 4-headless. Unattended routing (no human at the gate)", "unattended-routing-no-human-at-the-gate"),
        ("## 0.5. Enabled gate", "enabled-gate"),
        ("# Step 4: Forge Status Report", "step-4-forge-status-report"),
        ("## Step 2.5 is not numbering", "step-2-5-is-not-numbering"),
        ("## 3.5 GHz is not numbering", "3-5-ghz-is-not-numbering"),
        ("## Closing hashes ##", "closing-hashes"),
        ("# `{emitEnvelopeHelper}` and `--flag`", "emitenvelopehelper-and-flag"),
    ])
    def test_the_slug_rule(self, heading, slug):
        assert _mod().section_slug(heading) == slug

    @pytest.mark.parametrize("name, key", [
        ("floor_check", "floor-check"),
        ("--orphan-action", "orphan-action"),
        ("composeStories", "compose-stories"),
        ("const holding function", "const-holding-function"),
        ("_declared_names", "declared-names"),
        ("cognee.agents.get", "cognee-agents-get"),
        ("a_very_long_helper_name", "very-long-helper-name"),
        ("reader's own code", "readers-own-code"),
        ("readers own code", "readers-own-code"),
        # A script by its file name: the path, the extension and a line suffix go.
        ("gate_eval.py", "gate-eval"),
        ("scripts/gate_eval.py:42", "gate-eval"),
        ("src\\shared\\scripts\\skf-health-check-seen.py:42-50", "skf-health-check-seen"),
        ("validate-inventory.py", "validate-inventory"),
        # A name copied from Markdown or a log: its backticks or quotes, and a `:line:column` suffix, go too.
        ("`gate_eval.py`", "gate-eval"),
        ("'gate_eval.py'", "gate-eval"),
        ('"scripts/gate_eval.py:42"', "gate-eval"),
        ("gate_eval.py:42:7", "gate-eval"),
        ("`scripts/gate_eval.py:42:7`", "gate-eval"),
        ("`floor_check`", "floor-check"),
        ("getHTTPResponse", "get-httpresponse"),
    ])
    def test_a_name_gives_its_defect_key(self, name, key):
        assert _mod().defect_key(name) == key
        code, out, err = _cli(*_stdin_args(), stdin=_names(name=name))
        assert code == 0, err
        assert json.loads(out)["defect_key"] == key

    @pytest.mark.parametrize("name", ["--__", "...", "'", "scripts/", "x/:42"])
    def test_a_name_that_yields_no_word_exits_2(self, name):
        code, out, err = _cli(*_stdin_args(), stdin=_names(name=name))
        assert code == 2 and out == ""
        assert "defect_name" in json.loads(err)["message"]

    @pytest.mark.parametrize("raw", [b"", b"not json", b"[1]", b'{"section": "x", "defect_name": "y"}',
                                     b'{"section_heading": "x", "defect_name": "y", "short_description": "z"}',
                                     b'{"section_heading": 1, "defect_name": "x"}',
                                     b'{"section_heading": " ", "defect_name": "x"}', b"\xff\xfe"],
                             ids=["empty", "junk", "list", "unknown-key", "description", "not-a-string", "blank",
                                  "not-utf8"])
    def test_stdin_that_is_not_the_names_object_exits_2(self, raw):
        code, out, err = _cli(*_stdin_args(), stdin=raw)
        assert code == 2 and out == ""
        assert "--stdin" in json.loads(err)["message"]

    @pytest.mark.parametrize("names, flags", [
        ({"section_heading": HEADING, "defect_name": "x"}, ["--section", SAMPLE["section"]]),
        ({"section_heading": HEADING, "defect_name": "x"}, ["--defect-key", "x"]),
        ({"section_heading": HEADING}, []),
        ({"defect_name": "x"}, []),
        ({}, []),
    ], ids=["section-twice", "key-twice", "no-key", "no-section", "neither"])
    def test_each_pair_takes_exactly_one_form(self, names, flags):
        code, out, err = _cli(*_stdin_args(), *flags, stdin=json.dumps(names).encode("utf-8"))
        assert code == 2 and out == ""
        message = json.loads(err)["message"]
        assert "--section" in message or "--defect-key" in message

    def test_the_heading_and_the_name_go_with_their_flag(self):
        """--stdin may carry one of the pair while the other is a flag."""
        code, out, err = _cli(*_stdin_args(), "--defect-key", "shared-text",
                              stdin=json.dumps({"section_heading": HEADING}).encode("utf-8"))
        assert code == 0, err
        assert json.loads(out) == _sample_out(FP_B, "shared-text")

    def test_without_stdin_both_flags_are_required(self):
        args = _fingerprint_args()
        for drop in ("--section", "--defect-key"):
            i = args.index(drop)
            code, out, err = _cli(*args[:i], *args[i + 2:])
            assert code == 2 and out == ""
            assert drop in json.loads(err)["message"]

    def test_a_non_ascii_heading_is_read_as_utf8(self, tmp_path):
        module = tmp_path / "src"
        (module / "shared" / "scripts").mkdir(parents=True)
        copied = module / "shared" / "scripts" / HELPER.name
        copied.write_bytes(HELPER.read_bytes())
        (module / "skf-setup" / "references").mkdir(parents=True)
        (module / "skf-setup" / "references" / "report.md").write_text("# Café \u2192 Résumé\n", encoding="utf-8")
        env = {**os.environ, "PYTHONIOENCODING": "ascii", "LC_ALL": "C"}
        code, out, err = _cli(*_stdin_args("report.md", workflow="skf-setup"), helper=copied, env=env,
                              stdin=_names("Café \u2192 Résumé"))
        assert code == 0, err
        assert json.loads(out)["section_slug"] == "caf-r-sum"


@pytest.mark.parametrize("step_file", sorted(SRC.glob("skf-*/references/*.md")),
                         ids=lambda path: path.relative_to(SRC).as_posix())
def test_every_heading_of_every_step_file_gives_a_slug(step_file):
    """A heading always names its section, and two sections of one file never share a slug but in the files named."""
    headings = _mod()._stage_headings(step_file)
    assert headings, "no heading at all"
    slugs = [_mod().section_slug(heading) for heading in headings]
    assert all(slugs), [heading for heading, slug in zip(headings, slugs) if not slug]
    shared = {slug for slug in slugs if slugs.count(slug) > 1}
    assert shared == KNOWN_DUPLICATE_SLUGS.get(step_file.relative_to(SRC).as_posix(), set())


# --------------------------------------------------------------------------
# lookup: the branches, with the gh call replaced
# --------------------------------------------------------------------------


class TestLookupBranches:
    @pytest.mark.parametrize("content", [None, b"", b"   \n", b"[]", b"{bad", b'"text"',
                                         b"\xff\xfe{}", '{"fp-a54e7a6": {"action": "created\xff"}}'.encode("latin-1"),
                                         pytest.param(DEEP, id="nested-past-the-parsers-depth")])
    def test_no_usable_cache_is_unseen(self, tmp_path, no_gh, content):
        cache = tmp_path / "seen.json"
        if content is not None:
            cache.write_bytes(content)
        assert _mod().lookup(FP_A, LEGACY, cache) == UNSEEN
        assert no_gh == []

    def test_a_folder_in_place_of_the_cache_is_an_empty_cache(self, tmp_path, no_gh):
        cache = tmp_path / "seen.json"
        cache.mkdir()
        assert _mod().lookup(FP_A, LEGACY, cache)["verdict"] == "unseen"

    def test_neither_key_present_is_unseen(self, tmp_path, no_gh):
        cache = _write_cache(tmp_path / "seen.json", {OTHER_FP: _live()})
        assert _mod().lookup(FP_A, LEGACY, cache) == UNSEEN

    def test_a_resolved_record_is_a_regression_without_gh(self, tmp_path, no_gh):
        record = {"action": "resolved", "issue_url": URL, "date": "2026-10-02"}
        cache = _write_cache(tmp_path / "seen.json", {FP_A: record})
        assert _mod().lookup(FP_A, LEGACY, cache) == _found("regression", record, "fp",
                                                             f"Regression of {URL} (resolved 2026-10-02).")

    @pytest.mark.parametrize("action", ["created", "reacted", "commented"])
    @pytest.mark.parametrize("answer, verdict, how", [
        ({"state": "CLOSED", "stateReason": "COMPLETED"}, "regression", "closed as completed"),
        ({"state": "MERGED", "stateReason": ""}, "regression", "merged"),
        ({"state": "MERGED"}, "regression", "merged"),
        ({"state": "OPEN", "stateReason": ""}, "handled", None),
        ({"state": "OPEN", "stateReason": "REOPENED"}, "handled", None),
        ({"state": "CLOSED", "stateReason": "NOT_PLANNED"}, "handled", None),
        ({"state": "CLOSED", "stateReason": "DUPLICATE"}, "handled", None),
        ({"state": "CLOSED", "stateReason": None}, "handled", None),
        (None, "handled", None),  # any failure: no gh, the time limit, a non-zero exit, junk
    ])
    def test_a_live_record_asks_the_issue(self, tmp_path, gh_answer, action, answer, verdict, how):
        record = _live(action)
        cache = _write_cache(tmp_path / "seen.json", {FP_A: record})
        gh_answer["answer"] = answer
        # The record dates the report, not the fix: the line says so.
        opening = how and f"Regression of {URL}, {how} since its report on 2026-10-01."
        assert _mod().lookup(FP_A, LEGACY, cache) == _found(verdict, record, "fp", opening)
        assert gh_answer["calls"] == [URL]

    @pytest.mark.parametrize("url", ["", None])
    @pytest.mark.parametrize("action", ["created", "reacted", "commented"])
    def test_a_live_record_without_a_url_is_handled_without_gh(self, tmp_path, no_gh, action, url):
        record = _live(action, url)
        cache = _write_cache(tmp_path / "seen.json", {FP_A: record})
        assert _mod().lookup(FP_A, LEGACY, cache) == _found("handled", record, "fp")

    @pytest.mark.parametrize("url", ["--web", "http://github.com/o/r/issues/1", "https://github.com/o/r/issues/1 --web",
                                     "  ", 12])
    def test_a_url_gh_may_not_take_counts_as_a_failure(self, tmp_path, no_gh, url):
        """A value starting with `-` would reach gh as a flag."""
        cache = _write_cache(tmp_path / "seen.json", {FP_A: _live("created", url)})
        assert _mod().lookup(FP_A, LEGACY, cache)["verdict"] == "handled"

    @pytest.mark.parametrize("record", [{"issue_url": URL, "date": DAY}, {"action": "queued", "issue_url": URL},
                                        {"action": "Created", "issue_url": URL}, None, "created", ["created"], 7])
    def test_an_odd_record_is_unrecognized(self, tmp_path, no_gh, record):
        cache = _write_cache(tmp_path / "seen.json", {FP_A: record})
        assert _mod().lookup(FP_A, LEGACY, cache) == _found("unrecognized", record, "fp")

    @pytest.mark.parametrize("answer", [{"state": "OPEN"}, None])
    def test_a_legacy_record_that_would_suppress_is_unseen(self, tmp_path, gh_answer, answer):
        record = _live("reacted")
        cache = _write_cache(tmp_path / "seen.json", {LEGACY: record})
        gh_answer["answer"] = answer
        assert _mod().lookup(FP_A, LEGACY, cache) == _found("unseen", record, "legacy_fp")

    def test_a_legacy_record_without_a_url_is_unseen(self, tmp_path, no_gh):
        record = _live("created", "")
        cache = _write_cache(tmp_path / "seen.json", {LEGACY: record})
        assert _mod().lookup(FP_A, LEGACY, cache)["verdict"] == "unseen"

    def test_a_legacy_resolved_record_is_a_possible_regression(self, tmp_path, no_gh):
        record = {"action": "resolved", "issue_url": URL, "date": "2026-10-02"}
        cache = _write_cache(tmp_path / "seen.json", {LEGACY: record})
        assert _mod().lookup(FP_A, LEGACY, cache) == _found(
            "possible-regression", record, "legacy_fp",
            f"Possibly a regression of {URL} (resolved 2026-10-02): that report's fingerprint has no defect key, so "
            "it may be another defect in this section.")

    def test_a_legacy_record_whose_issue_was_completed_is_a_possible_regression(self, tmp_path, gh_answer):
        cache = _write_cache(tmp_path / "seen.json", {LEGACY: _live("commented")})
        gh_answer["answer"] = {"state": "CLOSED", "stateReason": "COMPLETED"}
        found = _mod().lookup(FP_A, LEGACY, cache)
        assert found["verdict"] == "possible-regression"
        assert found["opening_line"] == (f"Possibly a regression of {URL}, closed as completed since its report on "
                                         "2026-10-01: that report's fingerprint has no defect key, so it may be "
                                         "another defect in this section.")

    def test_a_legacy_odd_record_stays_unrecognized(self, tmp_path, no_gh):
        cache = _write_cache(tmp_path / "seen.json", {LEGACY: {"action": "queued"}})
        assert _mod().lookup(FP_A, LEGACY, cache) == _found("unrecognized", {"action": "queued"}, "legacy_fp")

    def test_the_fp_record_wins_over_the_legacy_one(self, tmp_path, gh_answer):
        fp_record = _live("created")
        legacy = {"action": "resolved", "issue_url": "https://github.com/o/r/issues/2", "date": "2026-10-02"}
        cache = _write_cache(tmp_path / "seen.json", {LEGACY: legacy, FP_A: fp_record})
        gh_answer["answer"] = {"state": "OPEN"}
        assert _mod().lookup(FP_A, LEGACY, cache) == _found("handled", fp_record, "fp")
        assert gh_answer["calls"] == [URL]

    def test_an_fp_key_holding_null_is_a_record(self, tmp_path, no_gh):
        """The key is present, so the legacy record is never consulted."""
        cache = _write_cache(tmp_path / "seen.json", {FP_A: None, LEGACY: {"action": "resolved"}})
        assert _mod().lookup(FP_A, LEGACY, cache) == _found("unrecognized", None, "fp")

    @pytest.mark.parametrize("flag, value", [("--fp", "fp-A54E7A6"), ("--fp", "a54e7a6"), ("--legacy-fp", "fp-eb2d6f"),
                                             ("--legacy-fp", "fp-eb2d6f2x"), ("--fp", FP_A + "\n"),
                                             ("--legacy-fp", LEGACY + "\n")])
    def test_a_bad_fingerprint_exits_2(self, tmp_path, flag, value):
        args = {"--fp": FP_A, "--legacy-fp": LEGACY, flag: value}
        code, out, err = _cli("lookup", "--fp", args["--fp"], "--legacy-fp", args["--legacy-fp"],
                              "--cache", str(tmp_path / "seen.json"))
        assert code == 2 and out == ""
        assert flag in json.loads(err)["message"]


# --------------------------------------------------------------------------
# lookup: the opening line and --repo
# --------------------------------------------------------------------------

# bmad-module-ultracode-goal's opening_line text, which both health checks share: pinned here as that repository
# pins it.
LOCAL_REGRESSION = "Regression of a previously resolved local finding (resolved 2026-07-19)."
LOCAL_POSSIBLE = "Possibly a regression of a previously resolved local finding in this section (resolved 2026-07-19)."
OWN_URL = f"https://github.com/{HEALTH_CHECK_REPO}/issues/7"
OTHER_URL = "https://github.com/other/repo/issues/3"


class TestOpeningLine:
    @pytest.mark.parametrize("under, url, line", [
        (FP_A, URL, f"Regression of {URL} (resolved 2026-07-19)."),
        (FP_A, "", LOCAL_REGRESSION),
        (LEGACY, URL, f"Possibly a regression of {URL} (resolved 2026-07-19): that report's fingerprint has no "
                      "defect key, so it may be another defect in this section."),
        (LEGACY, "", LOCAL_POSSIBLE),
    ], ids=["fp-url", "fp-local", "legacy-url", "legacy-local"])
    def test_a_resolved_record_gives_one_of_the_four_lines(self, tmp_path, no_gh, under, url, line):
        cache = _write_cache(tmp_path / "seen.json", {under: {"action": "resolved", "issue_url": url,
                                                              "date": "2026-07-19"}})
        found = _mod().lookup(FP_A, LEGACY, cache)
        assert found["verdict"] == ("regression" if under == FP_A else "possible-regression")
        assert found["opening_line"] == line

    @pytest.mark.parametrize("record", [
        {"action": "resolved", "date": "2026-07-19"},
        {"action": "resolved", "issue_url": "http://example.invalid/1", "date": "2026-07-19"},
        {"action": "resolved", "issue_url": "https://x/1\n## Fingerprint", "date": "2026-07-19"},
        {"action": "resolved", "issue_url": 7, "date": "2026-07-19"},
    ], ids=["no-url", "not-https", "whitespace", "not-a-string"])
    def test_a_url_a_body_should_not_carry_reads_as_a_local_finding(self, tmp_path, no_gh, record):
        """The line goes into a public issue body verbatim, so only a plain https:// URL is written into it."""
        cache = _write_cache(tmp_path / "seen.json", {FP_A: record})
        assert _mod().lookup(FP_A, LEGACY, cache)["opening_line"] == LOCAL_REGRESSION

    @pytest.mark.parametrize("day", [None, "", "yesterday", "2026-07-19\n## Severity", 20260719])
    def test_a_date_that_is_not_yyyy_mm_dd_is_unrecorded(self, tmp_path, no_gh, day):
        record = {"action": "resolved", "issue_url": ""}
        if day is not None:
            record["date"] = day
        cache = _write_cache(tmp_path / "seen.json", {FP_A: record})
        assert _mod().lookup(FP_A, LEGACY, cache)["opening_line"] == (
            "Regression of a previously resolved local finding (resolved on an unrecorded date).")

    @pytest.mark.parametrize("data", [{}, {FP_A: _live("created", "")}, {FP_A: {"action": "queued"}},
                                      {LEGACY: _live("created", "")}],
                             ids=["unseen", "handled", "unrecognized", "legacy-unseen"])
    def test_every_other_verdict_has_no_line(self, tmp_path, no_gh, data):
        assert _mod().lookup(FP_A, LEGACY, _write_cache(tmp_path / "seen.json", data))["opening_line"] is None


class TestRepo:
    """The cache serves every project on the machine, and a project may file to another repository."""

    @pytest.mark.parametrize("under", [FP_A, LEGACY])
    @pytest.mark.parametrize("record", [_live("created", OTHER_URL), _live("commented", OTHER_URL),
                                        {"action": "resolved", "issue_url": OTHER_URL, "date": "2026-07-19"}],
                             ids=["created", "commented", "resolved"])
    def test_a_record_of_another_repositorys_issue_counts_as_none(self, tmp_path, no_gh, under, record):
        """Neither suppressed by another tracker's record nor linked to its issue, and gh is never asked about it."""
        cache = _write_cache(tmp_path / "seen.json", {under: record})
        assert _mod().lookup(FP_A, LEGACY, cache, HEALTH_CHECK_REPO) == UNSEEN
        assert no_gh == []

    @pytest.mark.parametrize("repo", [HEALTH_CHECK_REPO, HEALTH_CHECK_REPO.upper()], ids=["same-case", "other-case"])
    @pytest.mark.parametrize("answer, verdict", [({"state": "OPEN"}, "handled"),
                                                 ({"state": "CLOSED", "stateReason": "COMPLETED"}, "regression")])
    def test_a_record_of_the_repositorys_own_issue_decides_as_before(self, tmp_path, gh_answer, repo, answer,
                                                                    verdict):
        cache = _write_cache(tmp_path / "seen.json", {FP_A: _live("created", OWN_URL)})
        gh_answer["answer"] = answer
        assert _mod().lookup(FP_A, LEGACY, cache, repo)["verdict"] == verdict
        assert gh_answer["calls"] == [OWN_URL]

    @pytest.mark.parametrize("record, verdict", [
        (_live("created", ""), "handled"), (_live("reacted", None), "handled"),
        ({"action": "resolved", "issue_url": "", "date": "2026-07-19"}, "regression"),
        ({"action": "queued", "issue_url": ""}, "unrecognized"), ("created", "unrecognized"),
    ], ids=["created-empty-url", "reacted-no-url", "resolved-empty-url", "old-queued", "not-an-object"])
    def test_a_record_that_names_no_repository_decides_as_without_repo(self, tmp_path, no_gh, record, verdict):
        cache = _write_cache(tmp_path / "seen.json", {FP_A: record})
        assert _mod().lookup(FP_A, LEGACY, cache, HEALTH_CHECK_REPO) == _mod().lookup(FP_A, LEGACY, cache)
        assert _mod().lookup(FP_A, LEGACY, cache, HEALTH_CHECK_REPO)["verdict"] == verdict

    def test_without_repo_another_repositorys_record_still_decides(self, tmp_path, gh_answer):
        cache = _write_cache(tmp_path / "seen.json", {FP_A: _live("created", OTHER_URL)})
        gh_answer["answer"] = {"state": "OPEN"}
        assert _mod().lookup(FP_A, LEGACY, cache)["verdict"] == "handled"

    def test_another_repositorys_record_under_fp_leaves_the_legacy_one_to_decide(self, tmp_path, no_gh):
        own = {"action": "resolved", "issue_url": OWN_URL, "date": "2026-07-19"}
        cache = _write_cache(tmp_path / "seen.json", {FP_A: _live("created", OTHER_URL), LEGACY: own})
        found = _mod().lookup(FP_A, LEGACY, cache, HEALTH_CHECK_REPO)
        assert (found["verdict"], found["record"], found["matched_on"]) == ("possible-regression", own, "legacy_fp")

    @pytest.mark.parametrize("repo, url, counts", [
        ("me/repo", "https://github.com/me/repo-two/issues/1", False),
        ("me/repo", "https://github.com/me/repo/pull/4", True),
        ("me/repo", "http://github.com/me/repo/issues/1", False),
        ("me/repo", "https://github.com/me/repo", False),
        ("ghe.example.com/team/repo", "https://ghe.example.com/team/repo/issues/1", True),
        ("ghe.example.com/team/repo", "https://github.com/team/repo/issues/1", False),
    ], ids=["longer-name", "pull-request", "http", "repository-page", "host-form", "host-form-on-github"])
    def test_a_record_counts_only_under_the_repositorys_own_url(self, tmp_path, no_gh, repo, url, counts):
        cache = _write_cache(tmp_path / "seen.json", {FP_A: {"action": "resolved", "issue_url": url,
                                                             "date": "2026-07-19"}})
        assert _mod().lookup(FP_A, LEGACY, cache, repo)["verdict"] == ("regression" if counts else "unseen")

    @pytest.mark.parametrize("repo", ["", "o", "o/r/x/y", "o/r x", "-o/r", "https://github.com/o/r", "o/r\n"])
    def test_a_repo_that_is_not_owner_slash_repo_exits_2(self, tmp_path, repo):
        code, out, err = _cli("lookup", "--fp", FP_A, "--legacy-fp", LEGACY, "--cache", str(tmp_path / "c.json"),
                              f"--repo={repo}")
        assert code == 2 and out == ""
        assert "--repo" in json.loads(err)["message"]

    def test_the_cli_takes_repo(self, tmp_path, fake_gh):
        cache = _write_cache(tmp_path / "seen.json", {FP_A: _live("created", OTHER_URL)})
        code, out, err = _cli("lookup", "--fp", FP_A, "--legacy-fp", LEGACY, "--cache", str(cache),
                              "--repo", HEALTH_CHECK_REPO)
        assert code == 0, err
        assert json.loads(out) == UNSEEN
        assert _logged(fake_gh) == []


# --------------------------------------------------------------------------
# lookup end to end: the real gh call against a fake gh first on PATH
# --------------------------------------------------------------------------

FAKE_GH = """#!{python}
import json, os, sys, time
with open(os.environ["FAKE_GH_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
mode = os.environ.get("FAKE_GH_MODE", "")
if mode == "hang":
    time.sleep(30)
    sys.exit(0)
if mode == "fail":
    print("GraphQL: Could not resolve to an issue or pull request", file=sys.stderr)
    sys.exit(1)
if mode == "junk":
    print("not json")
    sys.exit(0)
print(mode)
"""


@pytest.fixture
def fake_gh(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("the fake gh is a POSIX script")
    folder = tmp_path / "bin"
    folder.mkdir()
    script = folder / "gh"
    script.write_bytes(FAKE_GH.format(python=sys.executable).encode("utf-8"))
    script.chmod(0o755)
    log = tmp_path / "gh.log"
    monkeypatch.setenv("PATH", f"{folder}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    monkeypatch.setenv("FAKE_GH_MODE", "")
    return log


def _logged(log: Path) -> list:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _must_not_run(argv, timeout):
    """A replacement for skf-source-tree.py's _run that fails the test when anything is started."""
    raise AssertionError(f"nothing may be started here, got {argv!r}")


class TestGhEndToEnd:
    def test_the_call_gh_gets(self, fake_gh, monkeypatch):
        monkeypatch.setenv("FAKE_GH_MODE", json.dumps({"state": "CLOSED", "stateReason": "COMPLETED"}))
        assert _mod().gh_issue_state(URL) == {"state": "CLOSED", "stateReason": "COMPLETED"}
        assert _logged(fake_gh) == [["issue", "view", URL, "--json", "state,stateReason"]]

    @pytest.mark.parametrize("mode", ["fail", "junk", "[]", '{"stateReason": "COMPLETED"}'])
    def test_a_failed_answer_is_none(self, fake_gh, monkeypatch, mode):
        monkeypatch.setenv("FAKE_GH_MODE", mode)
        assert _mod().gh_issue_state(URL) is None

    def test_a_hanging_gh_is_stopped_at_the_limit(self, fake_gh, monkeypatch):
        monkeypatch.setenv("FAKE_GH_MODE", "hang")
        start = time.monotonic()
        assert _mod().gh_issue_state(URL, 1.0) is None
        assert time.monotonic() - start < 20

    def test_the_limit_is_ten_seconds(self):
        assert _mod().GH_TIMEOUT_SEC == 10.0

    def test_lookup_hands_gh_the_ten_second_limit(self, tmp_path, fake_gh, monkeypatch):
        """The limit lookup passes reaches skf-source-tree.py's _run, which stops a hanging gh there.
        The wrapper runs the real _run with a 1-second cap, so the test does not wait the 10."""
        monkeypatch.setenv("FAKE_GH_MODE", "hang")
        tree = _mod()._load(_mod().SOURCE_TREE_HELPER)
        real_run = tree._run
        limits = []

        def capped(argv, timeout):
            limits.append(timeout)
            return real_run(argv, 1.0)

        monkeypatch.setattr(tree, "_run", capped)
        cache = _write_cache(tmp_path / "seen.json", {FP_A: _live("created")})
        start = time.monotonic()
        assert _mod().lookup(FP_A, LEGACY, cache) == _found("handled", _live("created"), "fp")
        assert time.monotonic() - start < 20
        assert limits == [10.0]
        assert len(_logged(fake_gh)) == 1

    def test_no_gh_is_none(self, monkeypatch):
        tree = _mod()._load(_mod().SOURCE_TREE_HELPER)
        monkeypatch.setattr(tree, "_resolve_outside_cwd", lambda _name: None)
        monkeypatch.setattr(tree, "_run", _must_not_run)
        assert _mod().gh_issue_state(URL) is None

    def test_a_gh_planted_in_the_current_folder_is_not_run(self, monkeypatch):
        """shutil.which on Windows searches the current folder ahead of PATH: a gh.CMD that the repository a
        workflow runs in plants there reads as no gh, and nothing is started."""
        tree = _mod()._load(_mod().SOURCE_TREE_HELPER)
        monkeypatch.setattr(tree.shutil, "which", lambda _name, *_a, **_k: os.path.join(os.getcwd(), "gh.CMD"))
        monkeypatch.setattr(tree, "_run", _must_not_run)
        assert _mod().gh_issue_state(URL) is None

    @pytest.mark.parametrize("mode, verdict, how", [
        (json.dumps({"state": "CLOSED", "stateReason": "COMPLETED"}), "regression", "closed as completed"),
        (json.dumps({"state": "MERGED", "stateReason": ""}), "regression", "merged"),
        (json.dumps({"state": "OPEN", "stateReason": ""}), "handled", None),
        (json.dumps({"state": "CLOSED", "stateReason": "NOT_PLANNED"}), "handled", None),
        ("fail", "handled", None),
        ("junk", "handled", None),
    ])
    def test_the_cli_lookup(self, tmp_path, fake_gh, monkeypatch, mode, verdict, how):
        monkeypatch.setenv("FAKE_GH_MODE", mode)
        cache = _write_cache(tmp_path / "seen.json", {FP_A: _live("created")})
        code, out, err = _cli("lookup", "--fp", FP_A, "--legacy-fp", LEGACY, "--cache", str(cache))
        assert code == 0, err
        opening = how and f"Regression of {URL}, {how} since its report on 2026-10-01."
        assert json.loads(out) == _found(verdict, _live("created"), "fp", opening)
        assert len(_logged(fake_gh)) == 1

    def test_the_cli_runs_no_gh_without_a_live_record(self, tmp_path, fake_gh):
        cache = _write_cache(tmp_path / "seen.json", {FP_A: {"action": "resolved"}, FP_B: _live("created", "")})
        for fp, verdict in ((FP_A, "regression"), (FP_B, "handled"), (OTHER_FP, "unseen")):
            code, out, err = _cli("lookup", "--fp", fp, "--legacy-fp", LEGACY, "--cache", str(cache))
            assert code == 0, err
            assert json.loads(out)["verdict"] == verdict
        assert _logged(fake_gh) == []


# --------------------------------------------------------------------------
# record
# --------------------------------------------------------------------------


def _record(cache: Path, *extra: str, fp: str = FP_A, action: str = "created", url: str = URL,
            day: str = DAY) -> tuple[int, str, str]:
    return _cli("record", "--fp", fp, "--action", action, "--issue-url", url, "--date", day, "--cache", str(cache),
                *extra)


class TestRecord:
    def test_a_first_record_creates_the_folder_and_the_file(self, tmp_path):
        cache = tmp_path / "home" / ".skf" / "health-check-seen.json"
        code, out, err = _record(cache)
        assert code == 0, err
        new = {"issue_url": URL, "action": "created", "date": DAY}
        assert json.loads(out) == {"written": True, "fp": FP_A, "record": new, "set_aside": None}
        assert json.loads(cache.read_text(encoding="utf-8")) == {FP_A: new}
        assert sorted(p.name for p in cache.parent.iterdir()) == ["health-check-seen.json"]

    def test_the_merge_sets_one_key_and_keeps_the_rest(self, tmp_path):
        others = {
            LEGACY: {"action": "created", "issue_url": "https://github.com/o/r/issues/9", "date": "2026-01-01"},
            OTHER_FP: {"action": "resolved", "issue_url": "", "date": "2026-02-02", "note": "kept"},
            "not-a-fingerprint": [1, 2, 3],
            FP_A: {"action": "created", "issue_url": "https://github.com/o/r/issues/3", "date": "2026-03-03"},
        }
        cache = _write_cache(tmp_path / "seen.json", others)
        code, out, err = _record(cache, action="reacted")
        assert code == 0, err
        after = json.loads(cache.read_text(encoding="utf-8"))
        assert after[FP_A] == {"issue_url": URL, "action": "reacted", "date": DAY}
        assert {k: v for k, v in after.items() if k != FP_A} == {k: v for k, v in others.items() if k != FP_A}
        assert list(after) == list(others), "the keys keep their order"
        assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"], "no temp, lock or guard file is left"

    def test_record_never_writes_a_legacy_key(self, tmp_path):
        legacy = {"action": "resolved", "issue_url": URL, "date": "2026-01-01"}
        cache = _write_cache(tmp_path / "seen.json", {LEGACY: legacy})
        code, _, err = _record(cache)
        assert code == 0, err
        assert json.loads(cache.read_text(encoding="utf-8"))[LEGACY] == legacy

    @pytest.mark.parametrize("action, extra", [("reacted", ()), ("commented", ()), ("created", ())])
    def test_a_resolved_record_is_never_downgraded(self, tmp_path, action, extra):
        resolved = {"action": "resolved", "issue_url": URL, "date": "2026-10-02"}
        cache = _write_cache(tmp_path / "seen.json", {FP_A: resolved, OTHER_FP: _live()})
        before = cache.read_bytes()
        code, out, err = _record(cache, *extra, action=action, url="https://github.com/o/r/issues/5")
        assert code == 0, err
        assert json.loads(out) == {"written": False, "fp": FP_A, "record": resolved, "set_aside": None}
        assert cache.read_bytes() == before

    def test_the_regression_issue_replaces_a_resolved_record(self, tmp_path):
        resolved = {"action": "resolved", "issue_url": URL, "date": "2026-10-02"}
        cache = _write_cache(tmp_path / "seen.json", {FP_A: resolved, OTHER_FP: _live()})
        new_url = "https://github.com/o/r/issues/5"
        code, out, err = _record(cache, "--regression", url=new_url)
        assert code == 0, err
        new = {"issue_url": new_url, "action": "created", "date": DAY}
        assert json.loads(out) == {"written": True, "fp": FP_A, "record": new, "set_aside": None}
        assert json.loads(cache.read_text(encoding="utf-8")) == {FP_A: new, OTHER_FP: _live()}

    def test_regression_on_a_record_that_is_not_resolved_writes_as_usual(self, tmp_path):
        cache = _write_cache(tmp_path / "seen.json", {FP_A: _live("created")})
        code, out, err = _record(cache, "--regression")
        assert code == 0, err
        assert json.loads(out)["written"] is True

    @pytest.mark.parametrize("content", [b"{bad", b"[]", b'"text"', b"\xff\xfe{}",
                                         pytest.param(DEEP, id="nested-past-the-parsers-depth")])
    def test_a_corrupt_cache_is_set_aside(self, tmp_path, content):
        cache = tmp_path / "seen.json"
        cache.write_bytes(content)
        code, out, err = _record(cache)
        assert code == 0, err
        result = json.loads(out)
        aside = Path(result["set_aside"])
        assert aside.parent == tmp_path and aside.name.startswith("seen.json.corrupt-")
        assert len(aside.name) == len("seen.json.corrupt-20261112T101500Z")
        assert aside.read_bytes() == content
        assert json.loads(cache.read_text(encoding="utf-8")) == {FP_A: {"issue_url": URL, "action": "created",
                                                                       "date": DAY}}
        assert sorted(p.name for p in tmp_path.iterdir()) == sorted(["seen.json", aside.name])

    def test_a_second_set_aside_never_overwrites_the_first(self, tmp_path):
        cache = tmp_path / "seen.json"
        first = _mod()._set_aside(_bytes(cache, b"{one"))
        second = _mod()._set_aside(_bytes(cache, b"{two"))
        assert first != second
        assert first.read_bytes() == b"{one" and second.read_bytes() == b"{two"

    @pytest.mark.parametrize("content", [b"", b"  \n"])
    def test_an_empty_cache_is_not_set_aside(self, tmp_path, content):
        cache = tmp_path / "seen.json"
        cache.write_bytes(content)
        code, out, err = _record(cache)
        assert code == 0, err
        assert json.loads(out)["set_aside"] is None
        assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"]

    def test_a_bom_cache_is_read(self, tmp_path):
        cache = tmp_path / "seen.json"
        cache.write_bytes(b"\xef\xbb\xbf" + json.dumps({OTHER_FP: _live()}).encode("utf-8"))
        code, out, err = _record(cache)
        assert code == 0, err
        assert json.loads(out)["set_aside"] is None
        assert set(json.loads(cache.read_text(encoding="utf-8"))) == {OTHER_FP, FP_A}

    @pytest.mark.parametrize("over, rule", [
        ({"fp": "fp-12345"}, "--fp"),
        ({"fp": FP_A + "\n"}, "--fp"),
        ({"url": "http://github.com/o/r/issues/1"}, "--issue-url"),
        ({"url": "--web"}, "--issue-url"),
        ({"url": "https://github.com/o/r/issues/1 x"}, "--issue-url"),
        ({"day": "2026-02-30"}, "--date"),
        ({"day": "20261112"}, "--date"),
        ({"day": "12/11/2026"}, "--date"),
        ({"day": DAY + "\n"}, "--date"),
        ({"action": "queued"}, "--action"),
        ({"action": "upvoted"}, "--action"),
        ({"action": "created", "url": ""}, "--issue-url"),
        ({"action": "resolved", "url": "http://github.com/o/r/pull/2"}, "--issue-url"),
        ({"action": "resolved", "url": "--web"}, "--issue-url"),
        ({"action": "resolved", "url": " "}, "--issue-url"),
        ({"action": "resolved", "day": "2026-13-01"}, "--date"),
    ])
    def test_a_value_that_breaks_its_rule_exits_2(self, tmp_path, over, rule):
        cache = tmp_path / "seen.json"
        code, out, err = _record(cache, **over)
        assert code == 2 and out == ""
        assert rule in json.loads(err)["message"]
        assert not cache.exists()

    @pytest.mark.parametrize("url", ["", "https://github.com/o/r/pull/2"])
    def test_resolved_takes_an_empty_or_https_url(self, tmp_path, url):
        cache = tmp_path / "seen.json"
        code, out, err = _record(cache, action="resolved", url=url)
        assert code == 0, err
        new = {"issue_url": url, "action": "resolved", "date": DAY}
        assert json.loads(out) == {"written": True, "fp": FP_A, "record": new, "set_aside": None}
        assert json.loads(cache.read_text(encoding="utf-8")) == {FP_A: new}

    @pytest.mark.parametrize("before", [_live("created"), _live("reacted", ""), {"action": "queued"}, "odd",
                                        {"action": "resolved", "issue_url": URL, "date": "2026-10-02"}],
                             ids=["created", "reacted-no-url", "queued", "not-an-object", "resolved"])
    def test_a_resolved_record_replaces_any_record(self, tmp_path, before):
        """The fix, recorded with the helper instead of a hand edit: a resolved record is never a downgrade."""
        cache = _write_cache(tmp_path / "seen.json", {FP_A: before, OTHER_FP: _live()})
        fix = "https://github.com/o/r/pull/9"
        code, out, err = _record(cache, action="resolved", url=fix)
        assert code == 0, err
        new = {"issue_url": fix, "action": "resolved", "date": DAY}
        assert json.loads(out) == {"written": True, "fp": FP_A, "record": new, "set_aside": None}
        assert json.loads(cache.read_text(encoding="utf-8")) == {FP_A: new, OTHER_FP: _live()}

    def test_a_resolved_record_carries_nothing_over(self, tmp_path):
        cache = _write_cache(tmp_path / "seen.json", {FP_A: {**_live("created"), "defect_slug": "old"}})
        code, _, err = _record(cache, action="resolved", url="")
        assert code == 0, err
        assert json.loads(cache.read_text(encoding="utf-8"))[FP_A] == {"issue_url": "", "action": "resolved",
                                                                       "date": DAY}

    @pytest.mark.parametrize("action", ["reacted", "commented"])
    def test_a_reaction_on_the_recurrence_replaces_a_resolved_record(self, tmp_path, action):
        """After a regression verdict, [R] or [C] on an open issue that reports the defect: that issue tracks the
        recurrence now, so later sessions skip the finding instead of asking about the same issue again."""
        resolved = {"action": "resolved", "issue_url": URL, "date": "2026-10-02"}
        cache = _write_cache(tmp_path / "seen.json", {FP_A: resolved, OTHER_FP: _live()})
        open_issue = "https://github.com/o/r/issues/6"
        code, out, err = _record(cache, "--regression", action=action, url=open_issue)
        assert code == 0, err
        new = {"issue_url": open_issue, "action": action, "date": DAY}
        assert json.loads(out) == {"written": True, "fp": FP_A, "record": new, "set_aside": None}
        assert json.loads(cache.read_text(encoding="utf-8")) == {FP_A: new, OTHER_FP: _live()}

    def test_a_cache_that_cannot_be_read_exits_1(self, tmp_path):
        cache = tmp_path / "seen.json"
        cache.mkdir()
        code, out, err = _record(cache)
        assert code == 1 and out == ""
        assert json.loads(err)["status"] == "error"
        assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"], "no lock, guard or temp file is left"

    def test_a_corrupt_cache_that_cannot_be_set_aside_is_kept(self, tmp_path, monkeypatch, capsys):
        """Writing over it would lose the records a user can still repair, so nothing is written."""
        cache = _bytes(tmp_path / "seen.json", b"{bad")
        real_replace = os.replace

        def replace(src, dst):
            if ".corrupt-" in Path(dst).name:
                raise PermissionError(13, "Access is denied", str(dst))
            return real_replace(src, dst)

        monkeypatch.setattr(_mod(), "_IS_WINDOWS", False)
        monkeypatch.setattr(_mod().os, "replace", replace)
        code = _mod().main(["record", "--fp", FP_A, "--action", "created", "--issue-url", URL, "--date", DAY,
                            "--cache", str(cache)])
        captured = capsys.readouterr()
        assert code == 1 and captured.out == ""
        assert "cannot set aside" in json.loads(captured.err)["message"]
        assert cache.read_bytes() == b"{bad"
        assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"], "no .corrupt-*, lock or temp file"

    def test_a_failed_write_leaves_no_lock_and_no_temp_file(self, tmp_path, monkeypatch, capsys):
        cache = _write_cache(tmp_path / "seen.json", {OTHER_FP: _live()})
        before = cache.read_bytes()
        real_replace = os.replace

        def replace(src, dst):
            if Path(dst) == cache:
                raise PermissionError(13, "Access is denied", str(dst))
            return real_replace(src, dst)

        monkeypatch.setattr(_mod(), "_IS_WINDOWS", False)
        monkeypatch.setattr(_mod().os, "replace", replace)
        code = _mod().main(["record", "--fp", FP_A, "--action", "created", "--issue-url", URL, "--date", DAY,
                            "--cache", str(cache)])
        captured = capsys.readouterr()
        assert code == 1 and captured.out == ""
        assert json.loads(captured.err)["message"].startswith(f"cannot write {cache}")
        assert cache.read_bytes() == before
        assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"]

    def test_an_empty_lock_file_is_taken_at_once(self, tmp_path, monkeypatch, capsys):
        """skf-run-lock.py never writes an empty lock and nothing else writes this one, so an empty lock holds
        no call: record passes empty_is_stale=True and replaces it without waiting for it to go stale (here
        with no wait at all)."""
        cache = _write_cache(tmp_path / "seen.json", {OTHER_FP: _live()})
        (tmp_path / "seen.json.lock").write_bytes(b"")
        monkeypatch.setattr(_mod(), "LOCK_WAIT_SEC", 0.0)
        code = _mod().main(["record", "--fp", FP_A, "--action", "created", "--issue-url", URL, "--date", DAY,
                            "--cache", str(cache)])
        captured = capsys.readouterr()
        assert code == 0, captured.err
        assert json.loads(captured.out)["written"] is True
        assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"]

    def test_a_lock_another_run_holds_exits_1(self, tmp_path, monkeypatch, capsys):
        cache = _write_cache(tmp_path / "seen.json", {OTHER_FP: _live()})
        before = cache.read_bytes()
        run_lock = _mod()._load(RUN_LOCK)
        holder = "health-check-seen:record:20261112T101500Z-0badc0de"
        assert run_lock.acquire(tmp_path / "seen.json.lock", holder, 3600)["acquired"] is True
        monkeypatch.setattr(_mod(), "LOCK_WAIT_SEC", 0.3)
        code = _mod().main(["record", "--fp", FP_A, "--action", "created", "--issue-url", URL, "--date", DAY,
                            "--cache", str(cache)])
        captured = capsys.readouterr()
        assert code == 1 and captured.out == ""
        assert holder in json.loads(captured.err)["message"]
        assert cache.read_bytes() == before
        assert run_lock.release(tmp_path / "seen.json.lock", holder)["released"] is True

    def test_a_stale_lock_left_by_a_killed_call_is_replaced(self, tmp_path, monkeypatch, capsys):
        """A record call killed while it held the lock leaves it behind. Once it is older than LOCK_STALE_SEC,
        the next record replaces it at once, with no wait, and leaves no lock; a longer stale window would
        wait, then exit 1."""
        cache = _write_cache(tmp_path / "seen.json", {OTHER_FP: _live()})
        run_lock = _mod()._load(RUN_LOCK)
        killed = "health-check-seen:record:20261112T101500Z-0badc0de"
        killed_at = datetime.now(timezone.utc) - timedelta(seconds=60)
        assert run_lock.acquire(tmp_path / "seen.json.lock", killed, 15, now=killed_at)["acquired"] is True
        monkeypatch.setattr(_mod(), "LOCK_WAIT_SEC", 0.3)
        code = _mod().main(["record", "--fp", FP_A, "--action", "created", "--issue-url", URL, "--date", DAY,
                            "--cache", str(cache)])
        captured = capsys.readouterr()
        assert code == 0, captured.err
        assert json.loads(captured.out)["written"] is True
        assert set(json.loads(cache.read_text(encoding="utf-8"))) == {OTHER_FP, FP_A}
        assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"]

    def test_the_lock_is_the_registry_lock_shape(self):
        """Held for one read-merge-write: stale after 15 seconds, waited on for up to 10."""
        assert (_mod().LOCK_STALE_SEC, _mod().LOCK_WAIT_SEC) == (15.0, 10.0)

    def test_the_default_cache_is_in_home(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
        code, out, err = _cli("record", "--fp", FP_A, "--action", "created", "--issue-url", URL, "--date", DAY,
                              env=env)
        assert code == 0, err
        cache = home / ".skf" / "health-check-seen.json"
        assert json.loads(cache.read_text(encoding="utf-8"))[FP_A]["issue_url"] == URL
        code, out, err = _cli("lookup", "--fp", FP_B, "--legacy-fp", LEGACY, env=env)
        assert code == 0, err
        assert json.loads(out)["verdict"] == "unseen"

    def test_a_record_reads_back_through_lookup(self, tmp_path, no_gh):
        cache = tmp_path / "seen.json"
        _mod().record(FP_A, "created", URL, DAY, False, cache)
        _mod().record(FP_B, "created", "https://github.com/o/r/issues/2", DAY, False, cache)
        _mod().record(FP_A, "resolved", URL, "2026-11-14", False, cache)  # the fix, as CONTRIBUTING.md records it
        found = _mod().lookup(FP_A, LEGACY, cache, HEALTH_CHECK_REPO)
        assert found == _found("regression", {"issue_url": URL, "action": "resolved", "date": "2026-11-14"}, "fp",
                               f"Regression of {URL} (resolved 2026-11-14).")


class TestAtomicWriteWindowsRename:
    """Windows refuses os.replace over the cache while another process has it open (a lookup reading it, a
    scanner); _atomic_write retries a PermissionError there, and only there, before it fails. Ported from
    test-skf-forge-tier-rw.py's class of the same name."""

    @staticmethod
    def _refuse(times: int | None, calls: list, only: Path | None = None):
        """os.replace refused `times` times (None: always), for `only` when it is given."""
        real_replace = os.replace

        def replace(src, dst):
            if only is not None and Path(dst) != only:
                return real_replace(src, dst)  # the lock's own rename
            calls.append(dst)
            if times is None or len(calls) <= times:
                raise PermissionError(13, "Access is denied", str(dst))
            return real_replace(src, dst)

        return replace

    def test_a_rename_refused_for_a_moment_is_retried(self, tmp_path, monkeypatch):
        target = _bytes(tmp_path / "seen.json", b"{}\n")
        calls: list = []
        monkeypatch.setattr(_mod(), "_IS_WINDOWS", True)
        monkeypatch.setattr(_mod().os, "replace", self._refuse(2, calls))
        _mod()._atomic_write(target, '{"new": true}\n')
        assert len(calls) == 3
        assert target.read_bytes() == b'{"new": true}\n'
        assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"]

    def test_a_rename_refused_past_the_wait_fails_and_keeps_the_file(self, tmp_path, monkeypatch):
        target = _bytes(tmp_path / "seen.json", b"{}\n")
        calls: list = []
        monkeypatch.setattr(_mod(), "_IS_WINDOWS", True)
        monkeypatch.setattr(_mod(), "_REPLACE_WAIT_SECONDS", 0.05)
        monkeypatch.setattr(_mod().os, "replace", self._refuse(None, calls))
        started = time.monotonic()
        with pytest.raises(PermissionError):
            _mod()._atomic_write(target, '{"new": true}\n')
        elapsed = time.monotonic() - started
        assert len(calls) > 1 and 0.05 <= elapsed < 2.0
        assert target.read_bytes() == b"{}\n"
        assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"]

    def test_off_windows_a_refused_rename_fails_at_once(self, tmp_path, monkeypatch):
        calls: list = []
        monkeypatch.setattr(_mod(), "_IS_WINDOWS", False)
        monkeypatch.setattr(_mod().os, "replace", self._refuse(None, calls))
        with pytest.raises(PermissionError):
            _mod()._atomic_write(tmp_path / "seen.json", '{"new": true}\n')
        assert len(calls) == 1
        assert list(tmp_path.iterdir()) == []

    def test_only_a_refused_rename_is_retried(self, tmp_path, monkeypatch):
        calls: list = []

        def missing(src, dst):
            calls.append(dst)
            raise FileNotFoundError(2, "No such file or directory", str(src))

        monkeypatch.setattr(_mod(), "_IS_WINDOWS", True)
        monkeypatch.setattr(_mod().os, "replace", missing)
        with pytest.raises(FileNotFoundError):
            _mod()._atomic_write(tmp_path / "seen.json", '{"new": true}\n')
        assert len(calls) == 1

    def test_record_retries_a_refused_rename_on_windows(self, tmp_path, monkeypatch, capsys):
        cache = _write_cache(tmp_path / "seen.json", {OTHER_FP: _live()})
        calls: list = []
        monkeypatch.setattr(_mod(), "_IS_WINDOWS", True)
        monkeypatch.setattr(_mod().os, "replace", self._refuse(2, calls, only=cache))
        code = _mod().main(["record", "--fp", FP_A, "--action", "created", "--issue-url", URL, "--date", DAY,
                            "--cache", str(cache)])
        captured = capsys.readouterr()
        assert code == 0, captured.err
        assert len(calls) == 3
        assert set(json.loads(cache.read_text(encoding="utf-8"))) == {OTHER_FP, FP_A}
        assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"]

    def test_record_refused_past_the_wait_exits_1_and_keeps_the_cache(self, tmp_path, monkeypatch, capsys):
        cache = _write_cache(tmp_path / "seen.json", {OTHER_FP: _live()})
        before = cache.read_bytes()
        calls: list = []
        monkeypatch.setattr(_mod(), "_IS_WINDOWS", True)
        monkeypatch.setattr(_mod(), "_REPLACE_WAIT_SECONDS", 0.05)
        monkeypatch.setattr(_mod().os, "replace", self._refuse(None, calls, only=cache))
        code = _mod().main(["record", "--fp", FP_A, "--action", "created", "--issue-url", URL, "--date", DAY,
                            "--cache", str(cache)])
        captured = capsys.readouterr()
        assert code == 1 and captured.out == "" and len(calls) > 1
        assert json.loads(captured.err)["message"].startswith(f"cannot write {cache}")
        assert cache.read_bytes() == before
        assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"], "no lock, guard or temp file is left"

    def test_the_wait_stays_well_under_the_lock_stale_window(self):
        assert _mod()._REPLACE_WAIT_SECONDS <= _mod().LOCK_STALE_SEC / 2


def _bytes(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


# Runs the helper once a start file exists, so the calls reach the lock together.
RUNNER = (
    "import os, runpy, sys, time\n"
    "go, script = sys.argv[1], sys.argv[2]\n"
    "while not os.path.exists(go):\n"
    "    time.sleep(0.002)\n"
    "sys.argv = sys.argv[2:]\n"
    "runpy.run_path(script, run_name='__main__')\n"
)


def test_parallel_records_lose_none(tmp_path):
    """Without the lock, calls that read the same file overwrite each other's record."""
    cache = _write_cache(tmp_path / "seen.json", {OTHER_FP: _live()})
    go = tmp_path / "go"
    fps = [f"fp-{i:07x}" for i in range(8)]
    procs = [subprocess.Popen([sys.executable, "-c", RUNNER, str(go), str(HELPER), "record", "--fp", fp,
                               "--action", "created", "--issue-url", f"{URL}{i}", "--date", DAY,
                               "--cache", str(cache)],
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for i, fp in enumerate(fps)]
    time.sleep(0.8)
    go.write_bytes(b"")
    for proc in procs:
        out, err = proc.communicate(timeout=120)
        assert proc.returncode == 0, err
        assert json.loads(out)["written"] is True
    data = json.loads(cache.read_text(encoding="utf-8"))
    assert sorted(data) == sorted([OTHER_FP, *fps])
    assert sorted(p.name for p in tmp_path.iterdir()) == ["go", "seen.json"]


# --------------------------------------------------------------------------
# The step's own calls, filled in and run
# --------------------------------------------------------------------------


def _step_calls(subcommand: str) -> list[str]:
    """The fenced `uv run {seenCacheHelper} <subcommand> ...` lines of the shared health check."""
    prefix = f"uv run {{seenCacheHelper}} {subcommand}"
    return [line for line in SHARED_HEALTH_CHECK.read_text(encoding="utf-8").splitlines()
            if line == prefix or line.startswith(prefix + " ")]


def _run_step_call(line: str, values: dict, env: dict, files: dict | None = None) -> dict:
    """Run one of the step's calls with its placeholders filled, through this checkout's helper. A `< file`
    redirect feeds the file `files` holds under that name to the helper's stdin."""
    for placeholder, value in {"{seenCacheHelper}": "HELPER", **values}.items():
        line = line.replace(placeholder, value)
    assert "{" not in line, line
    words = shlex.split(line)
    assert words[:3] == ["uv", "run", "HELPER"], words
    stdin = None
    if "<" in words:
        i = words.index("<")
        assert len(words) == i + 2, words
        stdin = (files or {})[words[i + 1]]
        words = words[:i]
    code, out, err = _cli(*words[3:], env=env, stdin=stdin)
    assert code == 0, err
    return json.loads(out)


# What the step's fingerprint call names its names file with: §5a sub-step 1 writes it there with the Write tool.
NAMES_FILE = {"{localFallbackFolder}": "/q", "{timestamp}": "20261115-101500", "{i}": "1"}


def test_a_worked_example_through_the_steps_command():
    """Two different defects in inventory-contract.md's only section shared one fingerprint before the key; the
    step's call keeps them apart and gives hashlib's 7 hex characters, with the key and without it, from the heading
    and the names written to the names file, whatever form the step file is given in."""
    (line,) = _step_calls("fingerprint")
    joined = "gap|skf-test-skill|src/skf-test-skill/references/inventory-contract.md|documented-inventory-contract"

    def sha7(text: str) -> str:
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:7]

    names_file = "/q/bodies/names-20261115-101500-1.json"
    for step_file in ("inventory-contract.md", "_bmad/skf/skf-test-skill/references/inventory-contract.md"):
        base = {"{severity}": "gap", "{workflow}": "skf-test-skill", "{step_file}": step_file, **NAMES_FILE}
        for fp, name in NAMES.items():
            key = name.replace(" ", "-")
            out = _run_step_call(line, base, dict(os.environ), {names_file: _names(HEADING, name)})
            assert out == _sample_out(fp, key)
            assert (out["fp"], out["legacy_fp"]) == (f"fp-{sha7(f'{joined}|{key}')}", f"fp-{sha7(joined)}")


def test_the_steps_lookup_and_record_calls_share_the_default_cache(tmp_path):
    """The step passes no --cache: its calls meet in $HOME/.skf/health-check-seen.json. A fix recorded there with
    the helper makes the next sighting a regression, whose new issue the step's --regression call records."""
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
    cache = home / ".skf" / "health-check-seen.json"
    ids = {"{fp}": FP_A, "{legacy_fp}": LEGACY, "{today}": DAY, "{healthCheckRepo}": HEALTH_CHECK_REPO}
    # §5a-i's call after [R] or [C], then §5b's after a new issue, each with its --regression form.
    reacted, reacted_regression, created, regression = _step_calls("record")
    assert reacted_regression == f"{reacted} --regression" and regression == f"{created} --regression"

    def mark_resolved():  # CONTRIBUTING.md's call once the defect is fixed
        code, out, err = _cli("record", "--fp", FP_A, "--action", "resolved", "--issue-url", "", "--date", DAY,
                              env=env)
        assert code == 0 and json.loads(out)["written"] is True, err

    first = _run_step_call(created, {**ids, "{new_issue_url}": URL}, env)
    assert first["written"] is True and cache.is_file()
    mark_resolved()
    (lookup_call,) = _step_calls("lookup")
    found = _run_step_call(lookup_call, ids, env)
    assert (found["verdict"], found["opening_line"]) == ("regression", LOCAL_REGRESSION.replace("2026-07-19", DAY))
    # The plain call leaves the fix alone; the regression call records the recurrence's issue.
    new_url = "https://github.com/o/r/issues/77"
    assert _run_step_call(created, {**ids, "{new_issue_url}": new_url}, env)["written"] is False
    assert _run_step_call(regression, {**ids, "{new_issue_url}": new_url}, env)["record"] == {
        "issue_url": new_url, "action": "created", "date": DAY}
    # A record of an issue on another repository than the health check's is no record for the step's lookup.
    assert _run_step_call(lookup_call, ids, env) == UNSEEN
    # The same after [R] or [C] on an open issue that reports the recurrence.
    mark_resolved()
    open_issue = {**ids, "{reacted|commented}": "commented", "{url}": "https://github.com/o/r/issues/78"}
    assert _run_step_call(reacted, open_issue, env)["written"] is False
    assert _run_step_call(reacted_regression, open_issue, env)["record"] == {
        "issue_url": "https://github.com/o/r/issues/78", "action": "commented", "date": DAY}
    out = _run_step_call(reacted, {**ids, "{fp}": FP_B, "{reacted|commented}": "reacted", "{url}": URL}, env)
    assert out["record"]["action"] == "reacted"
    assert set(json.loads(cache.read_text(encoding="utf-8"))) == {FP_A, FP_B}


def test_the_steps_version_call_prints_this_checkouts_version():
    (line,) = _step_calls("version")
    version = json.loads((REPO / "package.json").read_text(encoding="utf-8"))["version"]
    assert _run_step_call(line, {}, dict(os.environ)) == {"version": version, "source": "package.json"}


# --------------------------------------------------------------------------
# version: each layout the helper can sit in
# --------------------------------------------------------------------------


def _install(root: Path, module: str, quick_metadata: bytes | None = None) -> Path:
    """The helper and its version sibling copied to <root>/<module>/shared/scripts/; the copy's path."""
    scripts = root / module / "shared" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / HELPER.name).write_bytes(HELPER.read_bytes())
    if quick_metadata is not False:
        (scripts / QUICK_METADATA.name).write_bytes(quick_metadata or QUICK_METADATA.read_bytes())
    return scripts / HELPER.name


def _version(helper: Path) -> dict:
    code, out, err = _cli("version", helper=helper)
    assert code == 0 and err == "", err
    return json.loads(out)


def _package(folder: Path, name: str = "bmad-module-skill-forge", version: str = "9.8.7") -> None:
    (folder / "package.json").write_text(json.dumps({"name": name, "version": version}), encoding="utf-8")


def _marketplace(folder: Path, name: str = "bmad-module-skill-forge", version="9.8.6") -> None:
    (folder / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (folder / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": name, "plugins": [{"name": "skill-forge", "version": version}]}), encoding="utf-8")


class TestVersion:
    def test_a_cli_install_reads_the_version_file(self, tmp_path):
        helper = _install(tmp_path / "project", "_bmad/skf")
        (tmp_path / "project" / "_bmad" / "skf" / "VERSION").write_text("11.0.0", encoding="utf-8")
        # A project's own package.json, two levels up, is never read.
        _package(tmp_path / "project", name="my-app", version="0.1.0")
        assert _version(helper) == {"version": "11.0.0", "source": "VERSION"}

    def test_a_checkout_or_a_plugin_reads_its_package_json(self, tmp_path):
        helper = _install(tmp_path / "plugin", "src")
        _package(tmp_path / "plugin")
        _marketplace(tmp_path / "plugin")
        assert _version(helper) == {"version": "9.8.7", "source": "package.json"}

    def test_the_version_file_is_read_directly(self, tmp_path):
        """probe_skf_version reads a package.json beside VERSION first: the VERSION rung reads the file itself."""
        helper = _install(tmp_path / "project", "_bmad/skf")
        (tmp_path / "project" / "_bmad" / "skf" / "VERSION").write_text("2.0.0\nnot this line\n", encoding="utf-8")
        _package(tmp_path / "project" / "_bmad" / "skf", version="7.7.7")
        assert _version(helper) == {"version": "2.0.0", "source": "VERSION"}

    def test_the_version_file_comes_first(self, tmp_path):
        helper = _install(tmp_path / "plugin", "src")
        (tmp_path / "plugin" / "src" / "VERSION").write_text("1.2.3\n", encoding="utf-8")
        _package(tmp_path / "plugin")
        assert _version(helper) == {"version": "1.2.3", "source": "VERSION"}

    @pytest.mark.parametrize("package", ["another-name", "broken", "no-version", None])
    def test_the_marketplace_follows_a_package_json_that_gives_none(self, tmp_path, package):
        helper = _install(tmp_path / "plugin", "src")
        if package == "broken":
            (tmp_path / "plugin" / "package.json").write_text("{not json", encoding="utf-8")
        elif package == "no-version":
            (tmp_path / "plugin" / "package.json").write_text('{"name": "bmad-module-skill-forge"}', encoding="utf-8")
        elif package:
            _package(tmp_path / "plugin", name=package)
        _marketplace(tmp_path / "plugin")
        assert _version(helper) == {"version": "9.8.6", "source": ".claude-plugin/marketplace.json"}

    @pytest.mark.parametrize("layout", ["nothing", "unknown-version-file", "empty-version-file", "other-marketplace",
                                        "marketplace-without-version", "broken-marketplace"])
    def test_nothing_found_is_null_and_na(self, tmp_path, layout):
        helper = _install(tmp_path / "plugin", "src")
        if layout == "unknown-version-file":  # probe_skf_version's own sentinel
            (tmp_path / "plugin" / "src" / "VERSION").write_text("unknown\n", encoding="utf-8")
        elif layout == "empty-version-file":
            (tmp_path / "plugin" / "src" / "VERSION").write_text("\n", encoding="utf-8")
        elif layout == "other-marketplace":
            _marketplace(tmp_path / "plugin", name="another-marketplace")
        elif layout == "marketplace-without-version":
            _marketplace(tmp_path / "plugin", version="")
        elif layout == "broken-marketplace":
            (tmp_path / "plugin" / ".claude-plugin").mkdir()
            (tmp_path / "plugin" / ".claude-plugin" / "marketplace.json").write_text("[", encoding="utf-8")
        assert _version(helper) == {"version": None, "source": "N/A"}

    @pytest.mark.parametrize("sibling", [b"raise SystemExit(3)\n", b"def probe_skf_version(\n", b"x = 1\n", None],
                             ids=["exits", "syntax-error", "no-probe", "missing"])
    def test_a_broken_sibling_gives_no_version_and_never_blocks(self, tmp_path, sibling):
        helper = _install(tmp_path / "project", "_bmad/skf", quick_metadata=sibling if sibling else False)
        (tmp_path / "project" / "_bmad" / "skf" / "VERSION").write_text("11.0.0", encoding="utf-8")
        assert _version(helper) == {"version": None, "source": "N/A"}

    def test_a_probe_that_raises_gives_no_version(self, tmp_path):
        helper = _install(tmp_path / "plugin", "src",
                          quick_metadata=b"def probe_skf_version(root):\n    raise RuntimeError(root)\n")
        _package(tmp_path / "plugin")
        _marketplace(tmp_path / "plugin")
        assert _version(helper) == {"version": None, "source": "N/A"}

    def test_this_checkout(self):
        version = json.loads((REPO / "package.json").read_text(encoding="utf-8"))["version"]
        assert _mod().skf_version() == {"version": version, "source": "package.json"}


# --------------------------------------------------------------------------
# The helper's shape
# --------------------------------------------------------------------------


def test_the_helper_is_a_stdlib_script_with_a_parser():
    text = HELPER.read_text(encoding="utf-8")
    assert text.startswith("# /// script\n# requires-python = \">=3.11\"\n# dependencies = []\n# ///\n")
    parser = _mod()._build_parser()
    for argv in (_fingerprint_args(), _stdin_args(), ["lookup", "--fp", FP_A, "--legacy-fp", LEGACY],
                 ["lookup", "--fp", FP_A, "--legacy-fp", LEGACY, "--repo", HEALTH_CHECK_REPO],
                 ["record", "--fp", FP_A, "--action", "created", "--issue-url", URL, "--date", DAY, "--regression"],
                 ["record", "--fp", FP_A, "--action", "resolved", "--issue-url", "", "--date", DAY], ["version"]):
        parser.parse_args(argv)


def test_the_helper_finds_files_from_its_own_place_never_the_project():
    """{project-root} is the user's project: the module is the folder two levels above the helper."""
    text = HELPER.read_text(encoding="utf-8")
    assert "MODULE_ROOT = HERE.parent.parent" in text
    assert "project-root" not in text.split('"""', 2)[2]
    assert "getcwd" not in text and "Path.cwd" not in text


def test_fingerprint_and_record_run_no_gh(tmp_path, no_gh):
    _mod().fingerprint(key="shared-text", **SAMPLE)
    _mod().record(FP_A, "created", URL, DAY, False, tmp_path / "seen.json")
    assert no_gh == []
