"""Tests for campaign-render-kickoff.py: the whole kickoff, rendered by the script.

Confirms the script fills every placeholder of the kickoff template, the three
that step-05 used to leave to the model included: {{brief_summary}} from the
skill's brief target entry, {{directive_content}} byte for byte from
--directive-file (or "No directive configured"), and {{persistent_facts}} from
--facts-json (or "None"), read from stdin as the customization resolver prints
it, with {project-root} resolved by --project-root, and {{workarounds_list}}
from the pre-apply log (--workarounds-file), each applied workaround formatted
by the script. Also checks that step-05's call fits the script's CLI, passes
no JSON through shell quoting, and routes each exit 2 the script can give.
"""

from __future__ import annotations

import importlib.util
import io
import json
import pathlib
import re
import shlex
import sys

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "src" / "skf-campaign" / "scripts" / "campaign-render-kickoff.py"
TEMPLATE = REPO_ROOT / "src" / "skf-campaign" / "templates" / "kickoff-template.md"
STEP_05 = REPO_ROOT / "src" / "skf-campaign" / "references" / "step-05-skill-loop.md"
GATE_SCRIPT = REPO_ROOT / "src" / "skf-campaign" / "scripts" / "campaign-quality-gate.py"


def _load():
    spec = importlib.util.spec_from_file_location("campaign_render_kickoff", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()

STATE = {
    "campaign": {
        "name": "demo",
        "current_stage": 4,
        "quality_gate": {"hard": "zero-critical-high", "soft_target": 90, "soft_fallback": 80},
    },
    "skills": [
        {"name": "auth", "tier": "A", "pin": "v1.2.3", "commit_sha": "abc123", "status": "active",
         "depends_on": ["core"], "workarounds_applied": ["[doc-rot] fixed import"]},
        {"name": "core", "tier": "A", "pin": None, "commit_sha": None, "status": "completed",
         "depends_on": [], "workarounds_applied": []},
    ],
}
BRIEF = {"targets": [
    {"name": "auth", "repo_url": "https://github.com/o/auth", "tier": "A", "pin": "v1.2.3",
     "depends_on": ["core"], "language": "python", "scope_hint": "src/auth"},
    {"name": "core", "repo_url": "https://github.com/o/core", "tier": "A", "pin": None, "depends_on": []},
]}
TEMPLATE_TEXT = TEMPLATE.read_text(encoding="utf-8")
FORMER_JUDGMENT_SLOTS = ("{{brief_summary}}", "{{persistent_facts}}", "{{directive_content}}")
# A directive with CRLF line endings, text outside ASCII and placeholder-like
# text, none of which the kickoff may change.
DIRECTIVE_BYTES = (
    "## Quality Overrides\r\n\r\nauth: soft_target 95 (café → bar), keep {{pin}} as written\r\n"
).encode("utf-8")
# The same directive saved as cp1252: 0x92 is a curly apostrophe, 0xe9 an e
# with an acute accent, and neither is UTF-8.
LEGACY_DIRECTIVE_BYTES = b"## Quality Overrides\r\n\r\nauth: don\x92t skip the \xe9tape\r\n"


def _section(text: str, heading: str) -> str:
    """The body under a `## ` heading, up to the next one."""
    body = text.split(f"## {heading}\n", 1)[1]
    return body.split("\n## ", 1)[0].strip()


def _stdin(monkeypatch, data: bytes) -> None:
    """Feed data to the script's stdin, as a pipe would."""
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(data), encoding="utf-8"))


def _deny_read_bytes(monkeypatch, name: str) -> None:
    """Make Path.read_bytes raise PermissionError for the file called name."""
    read_bytes = pathlib.Path.read_bytes

    def fake(self):
        if self.name == name:
            raise PermissionError(13, "Permission denied", str(self))
        return read_bytes(self)

    monkeypatch.setattr(pathlib.Path, "read_bytes", fake)


class TestRenderKickoff:
    def test_mechanical_fields_filled(self):
        out = mod.render_kickoff(STATE, BRIEF, "auth", TEMPLATE_TEXT)
        assert "demo" in out
        assert "v1.2.3" in out
        assert "abc123" in out
        assert "https://github.com/o/auth" in out
        # The shipped template shows no campaign-wide gate: step-05 resolves each skill's own
        # threshold. A custom template that keeps the slot still gets it filled.
        assert "Soft: 90" not in out
        assert "Hard: zero-critical-high | Soft: 90 (fallback: 80)" in mod.render_kickoff(
            STATE, BRIEF, "auth", "Gate: {{quality_gate_summary}}"
        )
        # dependency status table for core (completed)
        assert "| core | completed |" in out
        # workaround list
        assert "[doc-rot] fixed import" in out

    def test_no_placeholder_left_for_the_model(self):
        out = mod.render_kickoff(
            STATE, BRIEF, "auth", TEMPLATE_TEXT, directive="Skip nothing.", facts=["Cite sources."]
        )
        assert "{{" not in out and "}}" not in out
        assert not hasattr(mod, "JUDGMENT_SLOTS")

    def test_defaults_when_no_directive_and_no_facts(self):
        out = mod.render_kickoff(STATE, BRIEF, "auth", TEMPLATE_TEXT)
        for slot in FORMER_JUDGMENT_SLOTS:
            assert slot not in out
        assert _section(out, "Standing Directive") == "No directive configured"
        assert _section(out, "Campaign Facts") == "None"

    def test_brief_summary_is_the_target_entry(self):
        out = mod.render_kickoff(STATE, BRIEF, "auth", TEMPLATE_TEXT)
        assert _section(out, "Brief Summary") == "\n".join([
            "- `name`: auth",
            "- `repo_url`: https://github.com/o/auth",
            "- `tier`: A",
            "- `pin`: v1.2.3",
            "- `depends_on`: core",
            "- `language`: python",
            "- `scope_hint`: src/auth",
        ])

    def test_brief_summary_empty_values(self):
        out = mod.render_kickoff(STATE, BRIEF, "core", TEMPLATE_TEXT)
        summary = _section(out, "Brief Summary")
        assert "- `pin`: latest" in summary
        assert "- `depends_on`: none" in summary

    def test_brief_summary_without_a_target_entry(self):
        out = mod.render_kickoff(STATE, {"targets": []}, "auth", TEMPLATE_TEXT)
        assert _section(out, "Brief Summary") == "The campaign brief has no target entry for `auth`."

    def test_directive_inserted_byte_for_byte(self):
        directive = DIRECTIVE_BYTES.decode("utf-8")
        out = mod.render_kickoff(STATE, BRIEF, "auth", TEMPLATE_TEXT, directive=directive)
        assert directive in out
        # A value is never searched again: {{pin}} in the directive stays as written.
        assert "keep {{pin}} as written" in out

    def test_facts_are_bullets(self):
        facts = ["All skills cite their source.", "From `ctx.md`:\n\n# Context\n\n- rule one\n"]
        out = mod.render_kickoff(STATE, BRIEF, "auth", TEMPLATE_TEXT, facts=facts)
        assert _section(out, "Campaign Facts") == "\n".join([
            "- All skills cite their source.",
            "- From `ctx.md`:",
            "",
            "  # Context",
            "",
            "  - rule one",
        ])

    def test_empty_facts_list_is_none(self):
        out = mod.render_kickoff(STATE, BRIEF, "auth", TEMPLATE_TEXT, facts=[])
        assert _section(out, "Campaign Facts") == "None"

    def test_blank_facts_are_skipped(self):
        out = mod.render_kickoff(STATE, BRIEF, "auth", TEMPLATE_TEXT, facts=["", "  \n"])
        assert _section(out, "Campaign Facts") == "None"

    def test_null_pin_becomes_latest(self):
        out = mod.render_kickoff(STATE, BRIEF, "core", TEMPLATE_TEXT)
        assert "latest" in out
        assert "{{pin}}" not in out

    def test_null_commit_becomes_unknown(self):
        out = mod.render_kickoff(STATE, BRIEF, "core", TEMPLATE_TEXT)
        assert "unknown" in out
        assert "{{commit_sha}}" not in out

    def test_no_deps_message(self):
        out = mod.render_kickoff(STATE, BRIEF, "core", TEMPLATE_TEXT)
        assert "No dependencies." in out

    def test_explicit_workarounds_override(self):
        out = mod.render_kickoff(STATE, BRIEF, "core", TEMPLATE_TEXT, workarounds=["wa-1", "wa-2"])
        assert "- wa-1" in out and "- wa-2" in out

    def test_preapply_entries_are_formatted_not_printed_as_dicts(self):
        applied = [
            {"fingerprint": "from old import x", "fix": "from new import x", "file": "SKILL.md", "severity": "high"},
            {"fingerprint": "use `a`", "fix": "use b", "file": "references/api.md", "severity": "low"},
            {"fingerprint": "fp", "fix": "fx"},
        ]
        out = mod.render_kickoff(STATE, BRIEF, "core", TEMPLATE_TEXT, workarounds=applied)
        assert _section(out, "Workarounds Applied").splitlines() == [
            "- SKILL.md: `from old import x` replaced with `from new import x` (high severity)",
            "- references/api.md: `` use `a` `` replaced with `use b` (low severity)",
            "- `fp` replaced with `fx`",
        ]
        assert "{'" not in out

    def test_empty_workarounds_none(self):
        out = mod.render_kickoff(STATE, BRIEF, "core", TEMPLATE_TEXT, workarounds=[])
        assert _section(out, "Workarounds Applied") == "None"

    def test_unknown_skill_raises(self):
        with pytest.raises(KeyError):
            mod.render_kickoff(STATE, BRIEF, "ghost", TEMPLATE_TEXT)


class TestLoadFacts:
    def test_sentences_are_kept(self):
        assert mod.load_facts(["One.", "Two."]) == ["One.", "Two."]

    def test_file_entry_adds_the_file(self, tmp_path):
        ctx = tmp_path / "project-context.md"
        ctx.write_bytes(b"# Context\n\n- rule\n")
        assert mod.load_facts([f"file:{ctx.as_posix()}"]) == [
            f"From `{ctx.as_posix()}`:\n\n# Context\n\n- rule\n"
        ]

    def test_glob_entry_adds_each_match_in_order(self, tmp_path):
        for sub in ("b", "a"):
            (tmp_path / sub).mkdir()
            (tmp_path / sub / "project-context.md").write_bytes(f"{sub} rules\n".encode("utf-8"))
        facts = mod.load_facts([f"file:{tmp_path.as_posix()}/**/project-context.md"])
        assert len(facts) == 2
        assert facts[0].startswith(f"From `{(tmp_path / 'a' / 'project-context.md').as_posix()}`:")
        assert facts[1].endswith("b rules\n")

    def test_glob_matching_no_file_adds_nothing(self, tmp_path):
        assert mod.load_facts([f"file:{tmp_path.as_posix()}/**/project-context.md"]) == []

    def test_path_that_names_no_file_is_refused(self, tmp_path):
        entry = f"file:{(tmp_path / 'team.md').as_posix()}"
        with pytest.raises(FileNotFoundError, match="names no file"):
            mod.load_facts([entry])

    def test_project_root_replaces_the_placeholder_in_a_glob(self, tmp_path):
        (tmp_path / "docs").mkdir()
        ctx = tmp_path / "docs" / "project-context.md"
        ctx.write_bytes(b"rule\n")
        assert mod.load_facts(["file:{project-root}/**/project-context.md"], str(tmp_path)) == [
            f"From `{ctx.as_posix()}`:\n\nrule\n"
        ]

    def test_project_root_replaces_the_placeholder_in_a_path(self, tmp_path):
        style = tmp_path / "style.md"
        style.write_bytes(b"house style\n")
        assert mod.load_facts(["file:{project-root}/style.md"], str(tmp_path)) == [
            f"From `{style.as_posix()}`:\n\nhouse style\n"
        ]

    def test_project_root_with_glob_characters_is_taken_literally(self, tmp_path):
        root = tmp_path / "proj [old]"
        (root / "sub").mkdir(parents=True)
        ctx = root / "sub" / "project-context.md"
        ctx.write_bytes(b"rule\n")
        assert mod.load_facts(["file:{project-root}/**/project-context.md"], str(root)) == [
            f"From `{ctx.as_posix()}`:\n\nrule\n"
        ]

    def test_unresolved_placeholder_is_refused(self):
        with pytest.raises(ValueError, match=r"\{project-root\}.*pass --project-root"):
            mod.load_facts(["file:{project-root}/**/project-context.md"])

    def test_other_placeholder_is_refused_with_a_root(self, tmp_path):
        with pytest.raises(ValueError, match=r"\{skill-root\}"):
            mod.load_facts(["file:{skill-root}/facts.md"], str(tmp_path))


class TestReadDirective:
    def test_no_path_is_none(self):
        assert mod.read_directive(None) is None

    def test_missing_file_is_none(self, tmp_path):
        assert mod.read_directive(str(tmp_path / "_campaign-directive.md")) is None

    def test_text_is_exactly_the_file(self, tmp_path):
        p = tmp_path / "_campaign-directive.md"
        p.write_bytes(DIRECTIVE_BYTES)
        assert mod.read_directive(str(p)).encode("utf-8") == DIRECTIVE_BYTES

    def test_bytes_outside_utf8_round_trip(self, tmp_path):
        p = tmp_path / "_campaign-directive.md"
        p.write_bytes(LEGACY_DIRECTIVE_BYTES)
        assert mod.read_directive(str(p)).encode("utf-8", "surrogateescape") == LEGACY_DIRECTIVE_BYTES


class TestRun:
    def _files(self, tmp_path):
        sf = tmp_path / "state.yaml"
        bf = tmp_path / "brief.yaml"
        tf = tmp_path / "kickoff.md"
        sf.write_text(yaml.dump(STATE), encoding="utf-8")
        bf.write_text(yaml.dump(BRIEF), encoding="utf-8")
        tf.write_text(TEMPLATE_TEXT, encoding="utf-8")
        return sf, bf, tf

    def _code(self, capsys) -> str:
        return json.loads(capsys.readouterr().err.strip())["code"]

    def test_success(self, tmp_path, capsys):
        sf, bf, tf = self._files(tmp_path)
        rc = mod.run(str(sf), str(bf), "auth", str(tf), None)
        assert rc == 0
        out = capsys.readouterr().out
        assert "demo" in out and "{{" not in out
        assert _section(out, "Standing Directive") == "No directive configured"
        assert _section(out, "Campaign Facts") == "None"

    def test_directive_file_is_byte_identical_in_the_output(self, tmp_path, capsysbinary):
        sf, bf, tf = self._files(tmp_path)
        directive = tmp_path / "_campaign-directive.md"
        directive.write_bytes(DIRECTIVE_BYTES)
        rc = mod.run(str(sf), str(bf), "auth", str(tf), None, directive_file=str(directive))
        assert rc == 0
        assert DIRECTIVE_BYTES in capsysbinary.readouterr().out

    def test_directive_in_another_encoding_is_byte_identical(self, tmp_path, capsysbinary):
        sf, bf, tf = self._files(tmp_path)
        directive = tmp_path / "_campaign-directive.md"
        directive.write_bytes(LEGACY_DIRECTIVE_BYTES)
        rc = mod.run(str(sf), str(bf), "auth", str(tf), None, directive_file=str(directive))
        assert rc == 0
        assert LEGACY_DIRECTIVE_BYTES in capsysbinary.readouterr().out

    def test_missing_directive_file_falls_back(self, tmp_path, capsys):
        sf, bf, tf = self._files(tmp_path)
        rc = mod.run(str(sf), str(bf), "auth", str(tf), None, directive_file=str(tmp_path / "none.md"))
        assert rc == 0
        assert _section(capsys.readouterr().out, "Standing Directive") == "No directive configured"

    def test_unreadable_directive_exit_2(self, tmp_path, capsys, monkeypatch):
        sf, bf, tf = self._files(tmp_path)
        directive = tmp_path / "_campaign-directive.md"
        directive.write_bytes(DIRECTIVE_BYTES)
        _deny_read_bytes(monkeypatch, directive.name)
        rc = mod.run(str(sf), str(bf), "auth", str(tf), None, directive_file=str(directive))
        assert rc == 2
        assert self._code(capsys) == "DIRECTIVE_UNREADABLE"

    def test_facts_json_renders_sentences_and_files(self, tmp_path, capsys):
        sf, bf, tf = self._files(tmp_path)
        ctx = tmp_path / "project-context.md"
        ctx.write_bytes(b"Keep names stable.\n")
        facts = json.dumps(["Cite the upstream source.", f"file:{ctx.as_posix()}"])
        rc = mod.run(str(sf), str(bf), "auth", str(tf), None, facts_json=facts)
        assert rc == 0
        assert _section(capsys.readouterr().out, "Campaign Facts") == "\n".join([
            "- Cite the upstream source.",
            f"- From `{ctx.as_posix()}`:",
            "",
            "  Keep names stable.",
        ])

    def test_resolver_output_on_stdin(self, tmp_path, capsys, monkeypatch):
        sf, bf, tf = self._files(tmp_path)
        (tmp_path / "docs").mkdir()
        ctx = tmp_path / "docs" / "project-context.md"
        ctx.write_bytes(b"Keep names stable.\n")
        # What `resolve_customization.py --key workflow.persistent_facts` prints.
        resolved = {"workflow.persistent_facts": [
            "Don't vendor upstream code.", "file:{project-root}/**/project-context.md",
        ]}
        _stdin(monkeypatch, json.dumps(resolved, indent=2).encode("utf-8"))
        rc = mod.run(str(sf), str(bf), "auth", str(tf), None, facts_json="-", project_root=str(tmp_path))
        assert rc == 0
        assert _section(capsys.readouterr().out, "Campaign Facts") == "\n".join([
            "- Don't vendor upstream code.",
            f"- From `{ctx.as_posix()}`:",
            "",
            "  Keep names stable.",
        ])

    def test_list_on_stdin_after_a_byte_order_mark(self, tmp_path, capsys, monkeypatch):
        sf, bf, tf = self._files(tmp_path)
        _stdin(monkeypatch, b"\xef\xbb\xbf" + json.dumps(["Cite sources."]).encode("utf-8"))
        rc = mod.run(str(sf), str(bf), "auth", str(tf), None, facts_json="-")
        assert rc == 0
        assert _section(capsys.readouterr().out, "Campaign Facts") == "- Cite sources."

    def test_resolver_output_without_the_key_is_none(self, tmp_path, capsys, monkeypatch):
        sf, bf, tf = self._files(tmp_path)
        _stdin(monkeypatch, b"{}\n")
        rc = mod.run(str(sf), str(bf), "auth", str(tf), None, facts_json="-", project_root=str(tmp_path))
        assert rc == 0
        assert _section(capsys.readouterr().out, "Campaign Facts") == "None"

    def test_empty_stdin_exit_2(self, tmp_path, capsys, monkeypatch):
        # What the pipe carries when the resolver is missing or fails.
        sf, bf, tf = self._files(tmp_path)
        _stdin(monkeypatch, b"")
        rc = mod.run(str(sf), str(bf), "auth", str(tf), None, facts_json="-", project_root=str(tmp_path))
        assert rc == 2
        err = json.loads(capsys.readouterr().err.strip())
        assert err["code"] == "BAD_FACTS" and "empty" in err["error"]

    def test_empty_facts_json_is_none(self, tmp_path, capsys):
        sf, bf, tf = self._files(tmp_path)
        rc = mod.run(str(sf), str(bf), "auth", str(tf), None, facts_json="[]")
        assert rc == 0
        assert _section(capsys.readouterr().out, "Campaign Facts") == "None"

    @pytest.mark.parametrize(
        "facts_json",
        [
            '{"not": "a list"}',
            '{"workflow": {"persistent_facts": []}}',
            "[1, 2]",
            "not json",
            '["file:{project-root}/**/project-context.md"]',
        ],
        ids=["object", "other-resolver-key", "non-string", "invalid-json", "unresolved-placeholder"],
    )
    def test_bad_facts_json_exit_2(self, tmp_path, capsys, facts_json):
        sf, bf, tf = self._files(tmp_path)
        rc = mod.run(str(sf), str(bf), "auth", str(tf), None, facts_json=facts_json)
        assert rc == 2
        assert self._code(capsys) == "BAD_FACTS"

    def test_project_root_that_is_no_directory_exit_2(self, tmp_path, capsys):
        sf, bf, tf = self._files(tmp_path)
        rc = mod.run(str(sf), str(bf), "auth", str(tf), None, facts_json="[]", project_root=str(tmp_path / "gone"))
        assert rc == 2
        assert self._code(capsys) == "BAD_FACTS"

    def test_fact_path_that_names_no_file_exit_2(self, tmp_path, capsys):
        sf, bf, tf = self._files(tmp_path)
        entry = f"file:{(tmp_path / 'docs' / 'team.md').as_posix()}"
        rc = mod.run(str(sf), str(bf), "auth", str(tf), None, facts_json=json.dumps([entry]))
        assert rc == 2
        err = json.loads(capsys.readouterr().err.strip())
        assert err["code"] == "FACTS_FILE_NOT_FOUND"
        assert f"`{entry}` names no file" in err["error"]

    def test_windows_path_turned_into_escapes_exit_2(self, tmp_path, capsys):
        # Single backslashes in JSON: \n and \t become a newline and a tab.
        sf, bf, tf = self._files(tmp_path)
        rc = mod.run(str(sf), str(bf), "auth", str(tf), None, facts_json=r'["file:C:\new\team.md"]')
        assert rc == 2
        assert self._code(capsys) == "FACTS_FILE_NOT_FOUND"

    def test_unreadable_facts_file_exit_2(self, tmp_path, capsys, monkeypatch):
        sf, bf, tf = self._files(tmp_path)
        ctx = tmp_path / "project-context.md"
        ctx.write_bytes(b"rule\n")
        _deny_read_bytes(monkeypatch, ctx.name)
        rc = mod.run(str(sf), str(bf), "auth", str(tf), None, facts_json=json.dumps([f"file:{ctx.as_posix()}"]))
        assert rc == 2
        assert self._code(capsys) == "FACTS_UNREADABLE"

    @pytest.mark.parametrize("label", ["state", "brief", "template"])
    def test_input_that_is_not_utf8_exit_2(self, tmp_path, capsys, label):
        files = dict(zip(("state", "brief", "template"), self._files(tmp_path)))
        files[label].write_bytes(b"\xff\xfe not utf-8")
        rc = mod.run(str(files["state"]), str(files["brief"]), "auth", str(files["template"]), None)
        assert rc == 2
        assert self._code(capsys) == f"{label.upper()}_UNREADABLE"

    def test_missing_state_exit_2(self, tmp_path, capsys):
        sf, bf, tf = self._files(tmp_path)
        rc = mod.run(str(tmp_path / "no.yaml"), str(bf), "auth", str(tf), None)
        assert rc == 2
        assert self._code(capsys) == "STATE_NOT_FOUND"

    def test_missing_brief_exit_2(self, tmp_path, capsys):
        sf, bf, tf = self._files(tmp_path)
        rc = mod.run(str(sf), str(tmp_path / "no.yaml"), "auth", str(tf), None)
        assert rc == 2
        assert self._code(capsys) == "BRIEF_NOT_FOUND"

    def test_non_mapping_brief_exit_2(self, tmp_path, capsys):
        sf, bf, tf = self._files(tmp_path)
        bf.write_text("- a\n- b\n", encoding="utf-8")
        rc = mod.run(str(sf), str(bf), "auth", str(tf), None)
        assert rc == 2
        assert self._code(capsys) == "PARSE_ERROR"

    def test_unknown_skill_exit_2(self, tmp_path, capsys):
        sf, bf, tf = self._files(tmp_path)
        rc = mod.run(str(sf), str(bf), "ghost", str(tf), None)
        assert rc == 2
        assert self._code(capsys) == "SKILL_NOT_FOUND"

    def test_workarounds_file_is_the_preapply_log(self, tmp_path, capsys):
        sf, bf, tf = self._files(tmp_path)
        log = tmp_path / "preapply-log.json"
        log.write_text(json.dumps({"applied": [{"fingerprint": "old()", "fix": "new()", "file": "SKILL.md",
                                                "severity": "medium"}], "skipped_count": 3,
                                   "registry_version": 1}, indent=2) + "\n", encoding="utf-8")
        rc = mod.run(str(sf), str(bf), "auth", str(tf), str(log))
        assert rc == 0
        out = capsys.readouterr().out
        assert "- SKILL.md: `old()` replaced with `new()` (medium severity)" in out

    def test_empty_preapply_log_lists_none(self, tmp_path, capsys):
        sf, bf, tf = self._files(tmp_path)
        log = tmp_path / "preapply-log.json"
        log.write_text('{"applied": [], "skipped_count": 0, "registry_version": 1}', encoding="utf-8")
        assert mod.run(str(sf), str(bf), "auth", str(tf), str(log)) == 0
        assert _section(capsys.readouterr().out, "Workarounds Applied") == "None"

    @pytest.mark.parametrize(
        "content",
        [None, "not json", '["a list"]', '{"skipped_count": 0}', '{"applied": "x"}'],
        ids=["missing", "not-json", "list", "no-applied", "applied-not-a-list"],
    )
    def test_bad_workarounds_file_exit_2(self, tmp_path, capsys, content):
        sf, bf, tf = self._files(tmp_path)
        log = tmp_path / "preapply-log.json"
        if content is not None:
            log.write_text(content, encoding="utf-8")
        rc = mod.run(str(sf), str(bf), "auth", str(tf), str(log))
        assert rc == 2
        assert self._code(capsys) == "BAD_WORKAROUNDS"

    def test_main_takes_every_flag(self, tmp_path, capsysbinary):
        sf, bf, tf = self._files(tmp_path)
        directive = tmp_path / "_campaign-directive.md"
        directive.write_bytes(DIRECTIVE_BYTES)
        (tmp_path / "ctx").mkdir()
        (tmp_path / "ctx" / "project-context.md").write_bytes(b"Ctx rule.\n")
        log = tmp_path / "preapply-log.json"
        log.write_text('{"applied": ["wa-1"]}', encoding="utf-8")
        rc = mod.main([
            "--state-file", str(sf), "--brief-file", str(bf), "--skill", "auth",
            "--template", str(tf), "--workarounds-file", str(log),
            "--facts-json", '["Cite sources.", "file:{project-root}/ctx/project-context.md"]',
            "--project-root", str(tmp_path), "--directive-file", str(directive),
        ])
        assert rc == 0
        out = capsysbinary.readouterr().out
        assert DIRECTIVE_BYTES in out
        assert b"- Cite sources." in out and b"- wa-1" in out and b"  Ctx rule." in out
        # The only {{...}} left is the one the directive itself holds.
        assert out.count(b"{{") == 1 and b"keep {{pin}} as written" in out


def _step05_pipeline() -> list[str]:
    """step-05's kickoff call, split at its pipe."""
    calls = [
        line.strip()
        for line in STEP_05.read_text(encoding="utf-8").splitlines()
        if "uv run {kickoffScript}" in line
    ]
    assert len(calls) == 1, calls
    return [part.strip() for part in calls[0].split(" | ")]


def _kickoff_call() -> str:
    calls = [part for part in _step05_pipeline() if part.startswith("uv run {kickoffScript}")]
    assert len(calls) == 1, calls
    return calls[0]


class TestStep05Call:
    """step-05 runs the script with every input it needs, in a form its CLI takes."""

    def test_call_parses(self):
        tokens = []
        for token in shlex.split(_kickoff_call())[3:]:
            token = token.lstrip("[").rstrip("]")
            if token.startswith(("{", "<")):
                token = "value"
            tokens.append(token)
        args = mod.build_parser().parse_args(tokens)
        assert args.skill == "value"
        assert args.facts_json == "-"

    def test_call_passes_every_flag(self):
        called = {t.lstrip("[") for t in shlex.split(_kickoff_call()) if t.lstrip("[").startswith("--")}
        flags = {
            opt
            for action in mod.build_parser()._actions
            for opt in action.option_strings
            if opt.startswith("--") and opt != "--help"
        }
        assert called == flags

    def test_the_resolver_pipes_the_facts(self):
        resolver, kickoff = _step05_pipeline()
        assert resolver == (
            "uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} "
            "--project-root {project-root} --key workflow.persistent_facts"
        )
        assert mod.RESOLVER_KEY == "workflow.persistent_facts"
        tokens = shlex.split(kickoff)
        assert tokens[tokens.index("--facts-json") + 1] == "-"
        assert tokens[tokens.index("--project-root") + 1] == "{project-root}"

    def test_no_fact_is_built_by_hand(self):
        text = STEP_05.read_text(encoding="utf-8")
        assert "`--facts-json -` takes `workflow.persistent_facts` from the resolver unchanged." in text
        for gone in ("one `file:<path>` entry per file", "no fact is typed", "`brief_path` plays no part"):
            assert gone not in text

    def test_no_json_passes_through_shell_quoting(self):
        text = STEP_05.read_text(encoding="utf-8")
        call = _kickoff_call()
        assert "'" not in call
        assert "[--workarounds-file {preapplyLogFile}]" in call
        assert "\\u0027" not in text and "single-quoted JSON" not in text
        assert "--facts-json '" not in text
        assert "replace the pipe with `< {factsFile}`" in text
        assert "leave `--workarounds-file` out of the kickoff call below" in text
        assert (
            "An exit 2 with no JSON on stderr is a usage error from a mangled call, not invalid input: "
            "fix the call and run it again."
        ) in text

    def test_exit_2_routing(self):
        text = STEP_05.read_text(encoding="utf-8")
        assert (
            "on `BAD_WORKAROUNDS` or `BAD_FACTS` this call's input is wrong, so correct it and run the call again"
        ) in text
        assert "on `BRIEF_NOT_FOUND` or `BRIEF_UNREADABLE`, HALT (exit code 8, `missing-brief`)" in text
        assert "Correct a call once only: when the corrected call fails too, HALT (exit code 2, `invalid-input`)." in text

    def test_routed_codes_are_the_scripts(self):
        # step-05 routes the kickoff script's codes and the gate script's resolve codes.
        routed = set(re.findall(r"`([A-Z]+(?:_[A-Z]+)+)`", STEP_05.read_text(encoding="utf-8")))
        assert routed == {"BAD_WORKAROUNDS", "BAD_FACTS", "BRIEF_NOT_FOUND", "BRIEF_UNREADABLE", "TARGET_NOT_FOUND"}
        gate_doc = GATE_SCRIPT.read_text(encoding="utf-8").split('"""', 2)[1]
        for code in routed:
            assert code in mod.__doc__ or code in gate_doc, code

    def test_step_fills_nothing_by_hand(self):
        text = STEP_05.read_text(encoding="utf-8")
        assert "judgment slot" not in text
        for slot in FORMER_JUDGMENT_SLOTS:
            assert slot not in text
