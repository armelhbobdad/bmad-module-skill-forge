"""Tests for campaign-parse-manifest.py: every campaign target validated at Setup.

Pins the format documented in step-01 section 1: per-line
`name,repo_url,tier,pin[;deps]`, blank/comment skip, all-or-nothing error
reporting with line numbers (never a silent partial target set). Every target
source goes through it (a manifest, a pasted list piped to `-`, a
campaign-brief.yaml with --brief): a repo_url that is no GitHub repository, a
name no sub-skill accepts, a Tier A pin brief-skill cannot take and a
duplicate name are errors, every repo_url comes out in the one shape the pin
stage reads, an empty name is filled from the repository, and dangling
depends_on names and Tier A on Tier B dependencies are reported in the
entries campaign-deps.py reports too. --stack-name gives the capstone a name
create-stack-skill accepts.
"""

from __future__ import annotations

import importlib.util
import io
import json
import pathlib

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "src" / "skf-campaign" / "scripts" / "campaign-parse-manifest.py"
SHARED = REPO_ROOT / "src" / "shared" / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location("campaign_parse_manifest", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()


def _shared(name):
    spec = importlib.util.spec_from_file_location(name[:-3].replace("-", "_"), SHARED / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestParse:
    def test_basic(self):
        r = mod.parse_manifest_text("auth,https://github.com/o/auth,A,v1.2.3\n")
        assert r["errors"] == []
        t = r["targets"][0]
        assert t == {"name": "auth", "repo_url": "https://github.com/o/auth", "tier": "A", "pin": "v1.2.3", "depends_on": []}

    def test_pin_omitted_is_null(self):
        r = mod.parse_manifest_text("data,https://github.com/o/data,B\n")
        assert r["targets"][0]["pin"] is None

    def test_empty_pin_field_is_null(self):
        r = mod.parse_manifest_text("data,https://github.com/o/data,B,\n")
        assert r["targets"][0]["pin"] is None

    def test_depends_on_segment(self):
        r = mod.parse_manifest_text("svc,https://github.com/o/svc,A,;auth,data\n")
        assert r["targets"][0]["depends_on"] == ["auth", "data"]

    def test_blank_and_comment_skipped(self):
        text = "# header\n\nauth,https://github.com/o/auth,A\n\n# trailing\n"
        r = mod.parse_manifest_text(text)
        assert len(r["targets"]) == 1
        assert r["errors"] == []

    def test_bad_tier_errors_with_line(self):
        r = mod.parse_manifest_text("auth,https://github.com/o/auth,C\n")
        assert r["targets"] == []
        assert r["errors"][0]["line"] == 1
        assert "tier" in r["errors"][0]["message"]

    def test_too_few_fields(self):
        r = mod.parse_manifest_text("justname\n")
        assert r["errors"][0]["line"] == 1

    def test_empty_name_taken_from_the_repository(self):
        r = mod.parse_manifest_text(",https://github.com/o/Socket.IO.git,A\n,git@github.com:o/core-lib.git,B\n")
        assert r["errors"] == []
        assert [t["name"] for t in r["targets"]] == ["socket-io", "core-lib"]
        assert r["filled_names"] == [
            {"name": "socket-io", "repo_url": "https://github.com/o/Socket.IO"},
            {"name": "core-lib", "repo_url": "https://github.com/o/core-lib"},
        ]

    @pytest.mark.parametrize(
        "repo_url",
        [
            "https://github.com/o/r",
            "http://www.GitHub.com/o/r.git/",
            "git@github.com:o/r.git",
            "ssh://git@github.com/o/r",
            "o/r",
            "github.com/o/r",
        ],
        ids=["https", "http-www-dotgit", "ssh", "ssh-url", "shorthand", "no-scheme"],
    )
    def test_every_github_shape_comes_out_canonical(self, repo_url):
        r = mod.parse_manifest_text(f"r,{repo_url},A\n")
        assert r["errors"] == []
        assert r["targets"][0]["repo_url"] == "https://github.com/o/r"

    def test_canonical_url_is_the_one_the_pin_stage_reads(self):
        pins = _shared("skf-validate-pins.py")
        for url in ("o/r", "git@github.com:o/r.git"):
            canonical, problem = mod.canonical_repo_url(url)
            assert problem is None
            assert pins._GITHUB_URL_RE.match(canonical).groups() == ("o", "r")

    @pytest.mark.parametrize(
        "repo_url, fragment",
        [
            ("notarepo", "names no repository"),
            ("https://github.com/", "names no repository"),
            ("https://github.com/o/r#readme", "names no repository"),
            ("https://gitlab.com/g/r", "is not on GitHub"),
            ("git@gitlab.com:g/r.git", "is not on GitHub"),
            ("https://github.com/o/r/tree/main", "names a path inside a repository"),
            ("ftp://github.com/o/r", "is no GitHub URL"),
        ],
        ids=["bare-word", "host-only", "fragment", "gitlab", "gitlab-ssh", "tree-ref", "ftp"],
    )
    def test_repo_url_the_pin_stage_cannot_read(self, repo_url, fragment):
        r = mod.parse_manifest_text(f"r,{repo_url},A\n")
        assert r["targets"] == []
        assert fragment in r["errors"][0]["message"]

    def test_tree_url_names_the_repository_to_use(self):
        r = mod.parse_manifest_text(",https://github.com/o/r/tree/main,B\n")
        assert r["filled_names"] == []
        assert "give the repository itself, `https://github.com/o/r`" in r["errors"][0]["message"]

    @pytest.mark.parametrize(
        "name", ["My_Lib", "-lead", "trail-", "two words", "x" * 65],
        ids=["underscore-caps", "leading-hyphen", "trailing-hyphen", "space", "65-chars"],
    )
    def test_name_that_is_no_skill_name(self, name):
        r = mod.parse_manifest_text(f"{name},o/r,A\n")
        assert r["targets"] == []
        assert "is no skill name" in r["errors"][0]["message"]

    def test_name_rules_are_brief_skills(self):
        brief_inputs = _shared("skf-validate-brief-inputs.py")
        # Compare pattern and flags: each module loads the script afresh, so the
        # compiled objects are the same object only while re's cache holds them.
        for ours, theirs in ((mod.KEBAB_RE, brief_inputs.KEBAB_RE), (mod.VERSION_RE, brief_inputs.SEMVER_RE)):
            assert (ours.pattern, ours.flags) == (theirs.pattern, theirs.flags)
        assert mod.is_skill_name("a" * 64) and not mod.is_skill_name("a" * 65)

    def test_filled_name_is_checked_too(self):
        r = mod.parse_manifest_text(f",o/{'r' * 70},A\n")
        assert r["targets"] == []
        assert "is no skill name" in r["errors"][0]["message"]

    @pytest.mark.parametrize("pin", ["main", "v1", "1.10", "release-2024"], ids=["branch", "major", "minor", "named-tag"])
    def test_tier_a_pin_must_be_a_version(self, pin):
        r = mod.parse_manifest_text(f"core,o/core,A,{pin}\n")
        assert r["targets"] == []
        assert f"`core` is Tier A with pin `{pin}`, which is no X.Y.Z version" in r["errors"][0]["message"]

    @pytest.mark.parametrize("pin", ["1.2.3", "v1.2.3", "2.0.0-rc.1"], ids=["plain", "v-prefix", "pre-release"])
    def test_tier_a_version_pin_accepted(self, pin):
        assert mod.parse_manifest_text(f"core,o/core,A,{pin}\n")["targets"][0]["pin"] == pin

    def test_tier_b_pin_is_not_shape_checked(self):
        assert mod.parse_manifest_text("cli,o/cli,B,main\n")["errors"] == []

    def test_duplicate_after_filling_the_name(self):
        r = mod.parse_manifest_text("auth,https://github.com/o/auth,A\n,https://github.com/o/auth,B\n")
        assert r["errors"] == [{"line": 2, "message": "duplicate target name `auth`"}]

    def test_dangling_depends_on_reported(self):
        r = mod.parse_manifest_text("svc,https://github.com/o/svc,A,;auth,ghost\nauth,https://github.com/o/auth,A\n")
        assert r["errors"] == []
        assert r["dangling_depends_on"] == [{"skill": "svc", "depends_on": "ghost"}]

    def test_tier_a_on_tier_b_reported(self):
        text = "lib,https://github.com/o/lib,B\napp,https://github.com/o/app,A,;lib\nplug,https://github.com/o/plug,B,;app\n"
        r = mod.parse_manifest_text(text)
        assert r["tier_inversions"] == [{"skill": "app", "depends_on": "lib"}]

    def test_empty_repo_url(self):
        r = mod.parse_manifest_text("auth,,A\n")
        assert r["errors"]
        assert "repo_url" in r["errors"][0]["message"]

    def test_duplicate_name(self):
        text = "auth,https://github.com/o/auth,A\nauth,https://github.com/o/auth2,B\n"
        r = mod.parse_manifest_text(text)
        assert len(r["targets"]) == 1
        assert any("duplicate" in e["message"] for e in r["errors"])

    def test_partial_collects_good_and_reports_bad(self):
        text = "good,https://github.com/o/good,A\nbad,https://github.com/o/bad,Z\n"
        r = mod.parse_manifest_text(text)
        assert [t["name"] for t in r["targets"]] == ["good"]
        assert r["errors"][0]["line"] == 2


class TestRun:
    def test_clean_exit_0(self, tmp_path, capsys):
        p = tmp_path / "m.txt"
        p.write_text("auth,https://github.com/o/auth,A,v1.0.0\n", encoding="utf-8")
        rc = mod.run(str(p))
        assert rc == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["targets"][0]["name"] == "auth"

    def test_byte_order_mark_is_no_part_of_the_first_name(self, tmp_path, capsys):
        p = tmp_path / "m.txt"
        p.write_bytes(b"\xef\xbb\xbfauth,o/auth,A\n")
        assert mod.run(str(p)) == 0
        assert json.loads(capsys.readouterr().out)["targets"][0]["name"] == "auth"

    def test_stdin_is_read_as_utf8_bytes(self, capsys, monkeypatch):
        # A cp1252 console would decode these bytes differently; the script reads bytes.
        data = "\ufeffcaf\u00e9,o/cafe,A\n".encode("utf-8")
        monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(data), encoding="cp1252"))
        assert mod.run("-") == 1
        message = json.loads(capsys.readouterr().out)["errors"][0]["message"]
        assert message.startswith("`caf\u00e9` is no skill name")

    def test_errors_exit_1(self, tmp_path, capsys):
        p = tmp_path / "m.txt"
        p.write_text("bad,,A\n", encoding="utf-8")
        rc = mod.run(str(p))
        assert rc == 1
        out = json.loads(capsys.readouterr().out.strip())
        assert out["errors"]

    def test_missing_file_exit_2(self, tmp_path, capsys):
        rc = mod.run(str(tmp_path / "nope.txt"))
        assert rc == 2
        err = json.loads(capsys.readouterr().err.strip())
        assert err["code"] == "MANIFEST_NOT_FOUND"


class TestBrief:
    def _brief(self, tmp_path, data):
        p = tmp_path / "campaign-brief.yaml"
        p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        return p

    def test_targets_take_defaults_and_keep_hints(self):
        r = mod.parse_brief({"targets": [
            {"name": "core", "repo_url": "https://github.com/o/core", "language_hint": "python"},
            {"repo_url": "o/web-sdk", "tier": "B", "pin": "2.1.0", "depends_on": ["core"]},
        ]})
        assert r["errors"] == []
        assert r["targets"] == [
            {"name": "core", "repo_url": "https://github.com/o/core", "tier": "A", "pin": None,
             "depends_on": [], "language_hint": "python"},
            {"name": "web-sdk", "repo_url": "https://github.com/o/web-sdk", "tier": "B", "pin": "2.1.0",
             "depends_on": ["core"]},
        ]
        assert r["filled_names"] == [{"name": "web-sdk", "repo_url": "https://github.com/o/web-sdk"}]

    def test_brief_fields_returned(self):
        r = mod.parse_brief({"campaign_name": "acme", "quality_gate": {"soft_target": 95},
                             "architecture_doc_path": "", "targets": []})
        assert r["brief"] == {"campaign_name": "acme", "quality_gate": {"soft_target": 95}, "architecture_doc_path": ""}

    @pytest.mark.parametrize(
        "target, fragment",
        [
            ({"name": "n", "repo_url": "o/n", "pin": 1.1}, "`pin` must be a string or null"),
            ({"name": "n", "repo_url": "o/n", "tier": "C"}, "invalid tier `C`"),
            ({"name": "n"}, "empty `repo_url`"),
            ({"name": "n", "repo_url": "o/n", "depends_on": "core"}, "`depends_on` must be a list"),
            ("just-a-string", "must be a mapping"),
            ({"name": "My_Lib", "repo_url": "o/n"}, "`My_Lib` is no skill name"),
            ({"name": "n", "repo_url": "o/n", "pin": "canary"}, "is Tier A with pin `canary`"),
            ({"name": "n", "repo_url": "https://gitlab.com/g/n"}, "is not on GitHub"),
        ],
        ids=["numeric-pin", "bad-tier", "no-repo", "deps-not-list", "not-a-mapping", "not-kebab",
             "branch-pin", "gitlab"],
    )
    def test_bad_target(self, target, fragment):
        r = mod.parse_brief({"targets": [target]})
        assert r["targets"] == []
        assert r["errors"][0]["target"] == 1
        assert fragment in r["errors"][0]["message"]

    def test_duplicate_names(self):
        r = mod.parse_brief({"targets": [{"name": "a", "repo_url": "o/a"}, {"name": "a", "repo_url": "o/a2"}]})
        assert r["errors"] == [{"target": 2, "message": "duplicate target name `a`"}]

    def test_quality_gate_must_hold_numbers(self):
        r = mod.parse_brief({"targets": [], "quality_gate": {"soft_target": "ninety"}})
        assert r["errors"] == [{"field": "quality_gate.soft_target",
                                "message": "`quality_gate.soft_target` must be a number, got 'ninety'"}]

    def test_cli_brief_exit_codes(self, tmp_path, capsys):
        good = self._brief(tmp_path, {"targets": [{"name": "a", "repo_url": "o/a"}]})
        assert mod.main(["--brief", str(good)]) == 0
        assert json.loads(capsys.readouterr().out)["targets"][0]["name"] == "a"

        bad = self._brief(tmp_path, {"targets": [{"name": "a"}]})
        assert mod.main(["--brief", str(bad)]) == 1
        capsys.readouterr()

        assert mod.main(["--brief", str(tmp_path / "none.yaml")]) == 2
        assert json.loads(capsys.readouterr().err)["code"] == "BRIEF_NOT_FOUND"

        listy = tmp_path / "list.yaml"
        listy.write_bytes(b"- a\n- b\n")
        assert mod.main(["--brief", str(listy)]) == 2
        assert json.loads(capsys.readouterr().err)["code"] == "BRIEF_PARSE_ERROR"

    def test_cli_needs_exactly_one_source(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            mod.main([])
        assert exc.value.code == 2
        with pytest.raises(SystemExit) as exc:
            mod.main(["m.txt", "--brief", "b.yaml"])
        assert exc.value.code == 2
        with pytest.raises(SystemExit) as exc:
            mod.main(["--brief", "b.yaml", "--stack-name", "s.yaml"])
        assert exc.value.code == 2


# --------------------------------------------------------------------------
# One dependency rule for Setup and Strategy
# --------------------------------------------------------------------------


def test_dependency_problems_name_skill_and_dependency():
    problems = mod.dependency_problems([
        {"name": "lib", "tier": "B", "depends_on": []},
        {"name": "app", "tier": "A", "depends_on": ["lib", "ghost"]},
        {"name": "plug", "tier": "B", "depends_on": ["app"]},
    ])
    assert problems == {
        "dangling_depends_on": [{"skill": "app", "depends_on": "ghost"}],
        "tier_inversions": [{"skill": "app", "depends_on": "lib"}],
    }


# --------------------------------------------------------------------------
# --stack-name: the capstone's stack_name, a name create-stack-skill accepts
# --------------------------------------------------------------------------


class TestStackName:
    @pytest.mark.parametrize(
        "campaign_name, expected",
        [
            ("Acme (web)", "acme-web"),
            ("Caf\u00e9 Launch", "caf-launch"),
            ("platform-stack", "platform-stack"),
            ("!!!", None),
            ("", None),
            (None, None),
        ],
        ids=["edge-punctuation", "non-ascii", "keeps-stack-suffix", "nothing-left", "empty", "missing"],
    )
    def test_names(self, campaign_name, expected):
        assert mod.stack_name(campaign_name) == expected

    def test_long_name_leaves_room_for_the_suffix(self):
        name = mod.stack_name("Platform " + "x" * 80)
        assert len(name) == mod.MAX_NAME - len("-stack")
        assert mod.is_skill_name(name + "-stack")

    def test_cut_never_ends_on_a_hyphen(self):
        name = mod.stack_name("a" * 57 + " b")
        assert name == "a" * 57

    def test_cli_reads_the_campaign_name_from_state(self, tmp_path, capsys):
        state = tmp_path / "_campaign-state.yaml"
        state.write_text(yaml.safe_dump({"campaign": {"name": "Acme Web"}, "skills": []}), encoding="utf-8")
        assert mod.main(["--stack-name", str(state)]) == 0
        assert json.loads(capsys.readouterr().out) == {"stack_name": "acme-web"}

    def test_cli_missing_state(self, tmp_path, capsys):
        assert mod.main(["--stack-name", str(tmp_path / "none.yaml")]) == 2
        assert json.loads(capsys.readouterr().err)["code"] == "STATE_NOT_FOUND"
