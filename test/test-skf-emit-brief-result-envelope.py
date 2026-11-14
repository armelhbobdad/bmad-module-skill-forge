#!/usr/bin/env python3
"""Tests for skf-emit-brief-result-envelope.py.

The script has two pure functions (assemble, validate) plus two CLI
subcommands. Tests exercise both paths.

#1134: the brief stages now call the shared emitter itself, and the alias
stays. A halt is one `emit-halt --halt-reason` command that reads no stdin
and takes the mode and the skill name from the run's halt-state.json (the
name `unknown` from the schema's halt_defaults before then), and a
{field, message} warning is one `field: message` line wherever a payload's
warnings are read.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "shared"
    / "scripts"
    / "skf-emit-brief-result-envelope.py"
)

spec = importlib.util.spec_from_file_location(
    "skf_emit_brief_result_envelope", SCRIPT_PATH
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# assemble() — context → envelope
# --------------------------------------------------------------------------


class TestAssemble:
    def test_success_envelope(self):
        env = mod.assemble({
            "status": "success",
            "brief_path": "/abs/x/skill-brief.yaml",
            "skill_name": "marked",
            "version": "1.2.3",
            "language": "javascript",
            "scope_type": "public-api",
            "halt_reason": None,
        })
        assert env == {
            "status": "success",
            "brief_path": "/abs/x/skill-brief.yaml",
            "skill_name": "marked",
            "version": "1.2.3",
            "language": "javascript",
            "scope_type": "public-api",
            "exit_code": 0,
            "halt_reason": None,
            "mode": None,
        }

    def test_auto_mode_envelope(self):
        env = mod.assemble({
            "status": "success",
            "brief_path": "/abs/x/skill-brief.yaml",
            "skill_name": "marked",
            "version": "1.2.3",
            "language": "javascript",
            "scope_type": "public-api",
            "halt_reason": None,
            "mode": "auto",
        })
        assert env["mode"] == "auto"

    def test_mode_defaults_to_null(self):
        env = mod.assemble({
            "status": "success",
            "skill_name": "foo",
            "halt_reason": None,
        })
        assert env["mode"] is None

    def test_key_order_is_canonical(self):
        env = mod.assemble({
            "status": "error",
            "skill_name": "foo",
            "halt_reason": "input-missing",
        })
        # Insertion order should match KEY_ORDER constant
        assert list(env.keys()) == [
            "status", "brief_path", "skill_name", "version",
            "language", "scope_type", "exit_code", "halt_reason",
            "mode",
        ]

    @pytest.mark.parametrize(
        "halt,expected_exit",
        [
            (None, 0),
            ("input-missing", 2),
            ("input-invalid", 2),
            ("forge-tier-missing", 3),
            ("target-inaccessible", 3),
            ("gh-auth-failed", 3),
            ("write-failed", 4),
            ("overwrite-cancelled", 5),
            ("user-cancelled", 6),
        ],
    )
    def test_halt_reason_to_exit_code_mapping(self, halt, expected_exit):
        ctx = {
            "status": "success" if halt is None else "error",
            "skill_name": "foo",
            "halt_reason": halt,
        }
        env = mod.assemble(ctx)
        assert env["exit_code"] == expected_exit

    def test_brief_path_null_when_omitted(self):
        env = mod.assemble({
            "status": "error",
            "skill_name": "foo",
            "halt_reason": "write-failed",
        })
        assert env["brief_path"] is None
        assert env["version"] is None
        assert env["language"] is None
        assert env["scope_type"] is None


class TestAssembleValidation:
    def test_status_required(self):
        with pytest.raises(SystemExit):
            mod.assemble({"skill_name": "foo", "halt_reason": None})

    def test_status_invalid(self):
        with pytest.raises(SystemExit):
            mod.assemble({"status": "weird", "skill_name": "foo", "halt_reason": None})

    def test_skill_name_required(self):
        with pytest.raises(SystemExit):
            mod.assemble({"status": "success", "halt_reason": None})

    def test_skill_name_must_be_nonempty_string(self):
        with pytest.raises(SystemExit):
            mod.assemble({"status": "success", "skill_name": "", "halt_reason": None})

    def test_halt_reason_invalid(self):
        with pytest.raises(SystemExit):
            mod.assemble({
                "status": "error",
                "skill_name": "foo",
                "halt_reason": "made-up-reason",
            })

    def test_success_requires_null_halt_reason(self):
        with pytest.raises(SystemExit):
            mod.assemble({
                "status": "success",
                "skill_name": "foo",
                "halt_reason": "write-failed",
            })

    def test_error_requires_non_null_halt_reason(self):
        with pytest.raises(SystemExit):
            mod.assemble({
                "status": "error",
                "skill_name": "foo",
                "halt_reason": None,
            })

    def test_scope_type_invalid(self):
        with pytest.raises(SystemExit):
            mod.assemble({
                "status": "success",
                "skill_name": "foo",
                "halt_reason": None,
                "scope_type": "made-up-scope",
            })

    def test_mode_invalid(self):
        with pytest.raises(SystemExit):
            mod.assemble({
                "status": "success",
                "skill_name": "foo",
                "halt_reason": None,
                "mode": "manual",
            })


# --------------------------------------------------------------------------
# validate()
# --------------------------------------------------------------------------


class TestValidate:
    def _good(self) -> dict:
        return {
            "status": "success",
            "brief_path": "/abs/x.yaml",
            "skill_name": "foo",
            "version": "1.0.0",
            "language": "python",
            "scope_type": "full-library",
            "exit_code": 0,
            "halt_reason": None,
            "mode": None,
        }

    def test_canonical_envelope_passes(self):
        mod.validate(self._good())  # no exception = pass

    def test_missing_required_key_fails(self):
        env = self._good()
        del env["skill_name"]
        with pytest.raises(SystemExit):
            mod.validate(env)

    def test_extra_key_fails(self):
        env = self._good()
        env["extra"] = "value"
        with pytest.raises(SystemExit):
            mod.validate(env)

    def test_exit_code_must_match_halt_reason_mapping(self):
        # halt_reason=None → exit_code must be 0
        env = self._good()
        env["exit_code"] = 2  # mismatch
        with pytest.raises(SystemExit):
            mod.validate(env)

    def test_exit_code_3_for_target_inaccessible(self):
        env = {
            "status": "error",
            "brief_path": None,
            "skill_name": "foo",
            "version": None,
            "language": None,
            "scope_type": None,
            "exit_code": 3,
            "halt_reason": "target-inaccessible",
            "mode": None,
        }
        mod.validate(env)

    def test_exit_code_6_for_user_cancelled(self):
        env = {
            "status": "error",
            "brief_path": None,
            "skill_name": "foo",
            "version": None,
            "language": None,
            "scope_type": None,
            "exit_code": 6,
            "halt_reason": "user-cancelled",
            "mode": None,
        }
        mod.validate(env)  # must not raise — user-cancelled→6 is canonical

    def test_mode_auto_validates(self):
        env = self._good()
        env["mode"] = "auto"
        mod.validate(env)

    def test_mode_invalid_fails(self):
        env = self._good()
        env["mode"] = "manual"
        with pytest.raises(SystemExit):
            mod.validate(env)


# --------------------------------------------------------------------------
# CLI: emit
# --------------------------------------------------------------------------


class TestCLIEmit:
    def _run_emit(
        self, ctx: dict, target_flag: list[str] | None = None
    ) -> tuple[int, str, str]:
        cmd = [sys.executable, str(SCRIPT_PATH), "emit"]
        if target_flag:
            cmd.extend(target_flag)
        proc = subprocess.run(
            cmd, input=json.dumps(ctx), capture_output=True, text=True
        )
        return proc.returncode, proc.stdout, proc.stderr

    def test_emit_success_to_stdout_default(self):
        code, out, err = self._run_emit({
            "status": "success",
            "brief_path": "/x.yaml",
            "skill_name": "foo",
            "version": "1.0.0",
            "language": "python",
            "scope_type": "full-library",
            "halt_reason": None,
        })
        assert code == 0
        assert out.startswith("SKF_BRIEF_RESULT_JSON: ")
        assert err == ""
        line = out.strip()[len("SKF_BRIEF_RESULT_JSON: "):]
        env = json.loads(line)
        assert env["status"] == "success"
        assert env["exit_code"] == 0

    def test_emit_error_to_stderr_via_target_flag(self):
        code, out, err = self._run_emit(
            {
                "status": "error",
                "skill_name": "foo",
                "halt_reason": "write-failed",
            },
            target_flag=["--target", "stderr"],
        )
        assert code == 0
        assert out == ""
        assert err.startswith("SKF_BRIEF_RESULT_JSON: ")
        env = json.loads(err.strip()[len("SKF_BRIEF_RESULT_JSON: "):])
        assert env["status"] == "error"
        assert env["halt_reason"] == "write-failed"
        assert env["exit_code"] == 4

    def test_emit_one_line_output(self):
        # The envelope must fit on a single line so pipelines can grep it
        # without managing multi-line JSON.
        code, out, _ = self._run_emit({
            "status": "success",
            "brief_path": "/x.yaml",
            "skill_name": "foo",
            "version": "1.0.0",
            "language": "python",
            "scope_type": "full-library",
            "halt_reason": None,
        })
        assert code == 0
        # Exactly one line (excluding trailing newline)
        assert len(out.rstrip("\n").splitlines()) == 1

    def test_emit_rejects_empty_stdin(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "emit"],
            input="", capture_output=True, text=True,
        )
        assert proc.returncode == 1
        assert "empty stdin" in proc.stderr

    def test_emit_rejects_invalid_json(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "emit"],
            input="not-json", capture_output=True, text=True,
        )
        assert proc.returncode == 1
        assert "invalid JSON" in proc.stderr

    def test_emit_rejects_missing_skill_name(self):
        code, _, err = self._run_emit({"status": "success", "halt_reason": None})
        assert code == 1
        assert "skill_name" in err


# --------------------------------------------------------------------------
# CLI: validate
# --------------------------------------------------------------------------


class TestCLIValidate:
    def test_validate_passes_canonical_envelope(self):
        env = {
            "status": "success",
            "brief_path": "/x.yaml",
            "skill_name": "foo",
            "version": "1.0.0",
            "language": "python",
            "scope_type": "full-library",
            "exit_code": 0,
            "halt_reason": None,
            "mode": None,
        }
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "validate"],
            input=json.dumps(env), capture_output=True, text=True,
        )
        assert proc.returncode == 0
        assert proc.stdout == ""

    def test_validate_rejects_missing_keys(self):
        env = {"status": "success"}
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "validate"],
            input=json.dumps(env), capture_output=True, text=True,
        )
        assert proc.returncode == 1
        assert "missing required" in proc.stderr

    def test_validate_rejects_exit_code_mismatch(self):
        env = {
            "status": "success",
            "brief_path": "/x.yaml",
            "skill_name": "foo",
            "version": "1.0.0",
            "language": "python",
            "scope_type": "full-library",
            "exit_code": 2,  # wrong: should be 0 for halt_reason=null
            "halt_reason": None,
            "mode": None,
        }
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "validate"],
            input=json.dumps(env), capture_output=True, text=True,
        )
        assert proc.returncode == 1
        assert "canonical mapping" in proc.stderr


# --------------------------------------------------------------------------
# warnings (optional v1 property) and the shared emitter behind the alias
# --------------------------------------------------------------------------

SHARED_EMITTER = SCRIPT_PATH.parent / "skf-emit-result-envelope.py"
SCHEMA_PATH = SCRIPT_PATH.parent / "schemas" / "skf-brief-result-envelope.v1.json"
V1_KEYS = ["status", "brief_path", "skill_name", "version", "language", "scope_type",
           "exit_code", "halt_reason", "mode"]


class TestWarnings:
    def _ctx(self, **extra) -> dict:
        return {"status": "success", "skill_name": "foo", "halt_reason": None, **extra}

    def test_warnings_land_after_the_v1_keys(self):
        env = mod.assemble(self._ctx(warnings=["scope_rationale_missing"]))
        assert list(env) == [*V1_KEYS, "warnings"]
        assert env["warnings"] == ["scope_rationale_missing"]
        mod.validate(env)

    def test_no_warnings_key_while_there_are_none(self):
        assert list(mod.assemble(self._ctx(warnings=[]))) == V1_KEYS
        assert list(mod.assemble(self._ctx())) == V1_KEYS

    def test_resolver_reason_becomes_a_warning(self):
        env = mod.assemble(self._ctx(customization_resolver_unavailable="resolver missing"))
        assert env["warnings"] == ["customization_resolver_unavailable: resolver missing"]
        assert "customization_resolver_unavailable" not in env

    def test_a_field_message_warning_is_one_line(self):
        """#1134 (determinism-2): a validator's {field, message} warning no longer costs the run its line."""
        env = mod.assemble(self._ctx(warnings=["plain", {"field": "source_authority", "message": "m"}]))
        assert env["warnings"] == ["plain", "source_authority: m"]
        mod.validate(env)
        proc = subprocess.run([sys.executable, str(SCRIPT_PATH), "emit"], capture_output=True, text=True,
                              encoding="utf-8", input=json.dumps(self._ctx(warnings=[{"field": "f", "message": "m"}])))
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout[len("SKF_BRIEF_RESULT_JSON: "):])["warnings"] == ["f: m"]

    def test_warnings_must_be_strings(self):
        with pytest.raises(SystemExit):
            mod.assemble(self._ctx(warnings=[{"not": "a string"}]))
        env = mod.assemble(self._ctx())
        env["warnings"] = [""]
        with pytest.raises(SystemExit):
            mod.validate(env)

    def test_schema_keeps_warnings_optional(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        assert schema["required"] == V1_KEYS
        assert list(schema["properties"]) == [*V1_KEYS, "warnings"]
        assert schema["properties"]["warnings"]["type"] == "array"
        assert "customization_resolver_unavailable" in schema["properties"]["warnings"]["description"]


class TestAlias:
    def test_the_alias_restates_no_contract(self):
        text = SCRIPT_PATH.read_text(encoding="utf-8")
        for constant in ("HALT_TO_EXIT", "VALID_HALT_REASONS", "KEY_ORDER", "VALID_SCOPE_TYPES"):
            assert constant not in text, constant

    def test_exit_codes_live_in_the_schema(self):
        meta = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["$defs"]["skf-envelope"]["const"]
        assert meta["exit_codes"] == {
            "input-missing": 2, "input-invalid": 2, "forge-tier-missing": 3, "target-inaccessible": 3,
            "gh-auth-failed": 3, "write-failed": 4, "overwrite-cancelled": 5, "user-cancelled": 6,
        }
        assert meta["success_exit_code"] == 0 and meta["halt_status"] == "error"

    @pytest.mark.parametrize("ctx", [
        {"status": "success", "brief_path": "/x.yaml", "skill_name": "foo", "version": "1.0.0",
         "language": "python", "scope_type": "full-library", "halt_reason": None, "mode": "auto",
         "warnings": ["w"]},
        {"status": "error", "skill_name": "foo", "halt_reason": "gh-auth-failed"},
    ])
    def test_alias_and_shared_emitter_print_the_same_line(self, ctx):
        alias = subprocess.run([sys.executable, str(SCRIPT_PATH), "emit"], input=json.dumps(ctx),
                               capture_output=True, text=True, encoding="utf-8")
        shared = subprocess.run([sys.executable, str(SHARED_EMITTER), "emit", "--workflow", "skf-brief-skill"],
                                input=json.dumps(ctx), capture_output=True, text=True, encoding="utf-8")
        assert alias.returncode == shared.returncode == 0, alias.stderr + shared.stderr
        assert alias.stdout == shared.stdout

    def test_alias_validate_matches_the_shared_validate(self):
        env = mod.assemble({"status": "error", "skill_name": "foo", "halt_reason": "write-failed"})
        env["exit_code"] = 3
        shared = subprocess.run([sys.executable, str(SHARED_EMITTER), "validate", "--workflow", "skf-brief"],
                                input=json.dumps(env), capture_output=True, text=True)
        alias = subprocess.run([sys.executable, str(SCRIPT_PATH), "validate"], input=json.dumps(env),
                               capture_output=True, text=True)
        assert alias.returncode == shared.returncode == 1
        assert alias.stderr == shared.stderr and "canonical mapping" in alias.stderr

    # Halt payloads the replaced helper turned into a valid envelope: it read
    # only the keys it knew and always derived exit_code.
    TOLERATED = [
        ({"status": "error", "skill_name": "x", "halt_reason": "write-failed", "reason": "disk full"},
         ["payload_key_ignored: reason"]),
        ({"status": "error", "skill_name": "x", "halt_reason": "write-failed", "reason": "disk full",
          "exit_code": 1},
         ["payload_key_ignored: reason", "exit_code_overridden: 1 (halt_reason write-failed maps to 4)"]),
        ({"status": "success", "skill_name": "x", "halt_reason": None, "exit_code": 3},
         ["exit_code_overridden: 3 (halt_reason null maps to 0)"]),
    ]

    @pytest.mark.parametrize("ctx,notes", TOLERATED)
    def test_alias_emits_what_the_replaced_helper_tolerated(self, ctx, notes):
        proc = subprocess.run([sys.executable, str(SCRIPT_PATH), "emit", "--target", "stderr"],
                              input=json.dumps(ctx), capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0 and proc.stdout == "", proc.stderr
        [line] = proc.stderr.splitlines()
        env = json.loads(line[len("SKF_BRIEF_RESULT_JSON: "):])
        assert env["exit_code"] == (4 if ctx["halt_reason"] else 0)
        assert env["warnings"] == notes
        assert list(env) == [*V1_KEYS, "warnings"]
        mod.validate(env)
        assert mod.assemble(ctx) == env

    def test_a_typed_exit_code_that_matches_the_mapping_is_silent(self):
        env = mod.assemble({"status": "error", "skill_name": "x", "halt_reason": "write-failed", "exit_code": 4})
        assert env["exit_code"] == 4 and "warnings" not in env

    @pytest.mark.parametrize("ctx,_notes", TOLERATED)
    def test_the_shared_emitter_stays_strict(self, ctx, _notes):
        """Only the alias keeps the old tolerance; adopting workflows get a refusal."""
        shared = subprocess.run([sys.executable, str(SHARED_EMITTER), "emit", "--workflow", "skf-brief-skill"],
                                input=json.dumps(ctx), capture_output=True, text=True, encoding="utf-8")
        assert shared.returncode == 1 and shared.stdout == ""

    def test_the_line_is_ascii_as_the_replaced_helper_printed_it(self):
        ctx = {"status": "success", "brief_path": "/p/caf\u00e9/skill-brief.yaml", "skill_name": "caf\u00e9",
               "version": None, "language": None, "scope_type": None, "halt_reason": None,
               "warnings": ["line\u2028break"]}
        proc = subprocess.run([sys.executable, str(SCRIPT_PATH), "emit"], input=json.dumps(ctx),
                              capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, proc.stderr
        expected = {**{k: ctx.get(k) for k in V1_KEYS}, "exit_code": 0, "warnings": ["line\u2028break"]}
        assert proc.stdout == "SKF_BRIEF_RESULT_JSON: " + json.dumps(expected, separators=(",", ":")) + "\n"

    def test_installed_layout_loads_the_sibling_emitter(self, tmp_path):
        import shutil
        scripts = tmp_path / "_bmad" / "skf" / "shared" / "scripts"
        shutil.copytree(SCRIPT_PATH.parent / "schemas", scripts / "schemas")
        for script in (SCRIPT_PATH, SHARED_EMITTER):
            shutil.copy2(script, scripts / script.name)
        proc = subprocess.run([sys.executable, str(scripts / SCRIPT_PATH.name), "emit", "--target", "stderr"],
                              input=json.dumps({"status": "error", "skill_name": "foo",
                                                "halt_reason": "user-cancelled"}),
                              capture_output=True, text=True, cwd=tmp_path)
        assert proc.returncode == 0, proc.stderr
        env = json.loads(proc.stderr.strip()[len("SKF_BRIEF_RESULT_JSON: "):])
        assert env["exit_code"] == 6


# --------------------------------------------------------------------------
# #1134: the halt-reason form of the shared emitter, as the brief stages run it
# --------------------------------------------------------------------------

EXIT_CODES = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["$defs"]["skf-envelope"]["const"]["exit_codes"]


class TestHaltReasonForm:
    """`emit-halt --workflow skf-brief-skill --run-dir D --target stderr --halt-reason R`, the one command each
    brief halt site writes: no stdin read, the run's halt state and sink folded in."""

    def _run_dir(self, tmp_path: Path, state=None, warnings=()) -> Path:
        run_dir = tmp_path / "skf-brief-skill-abc12345"
        run_dir.mkdir()
        if isinstance(state, dict):
            (run_dir / "halt-state.json").write_bytes(json.dumps(state).encode("utf-8"))
        elif isinstance(state, str):  # "a folder": a halt state that cannot be read as a file
            (run_dir / "halt-state.json").mkdir()
        elif state is not None:
            (run_dir / "halt-state.json").write_bytes(state)
        for warning in warnings:
            done = subprocess.run([sys.executable, str(SHARED_EMITTER), "record", "--run-dir", str(run_dir),
                                   "--warning", warning], capture_output=True, text=True, encoding="utf-8")
            assert done.returncode == 0, done.stderr
        return run_dir

    def _halt(self, reason: str, run_dir: Path | None = None, *extra: str) -> subprocess.CompletedProcess:
        args = [sys.executable, str(SHARED_EMITTER), "emit-halt", "--workflow", "skf-brief-skill"]
        if run_dir is not None:
            args += ["--run-dir", str(run_dir)]
        # stdin holds junk: a read of it would fail the call with "invalid JSON on stdin"
        return subprocess.run([*args, "--target", "stderr", "--halt-reason", reason, *extra], input="{not json",
                              capture_output=True, text=True, encoding="utf-8", timeout=30)

    def _line(self, done: subprocess.CompletedProcess) -> dict:
        assert done.returncode == 0, done.stderr
        assert done.stdout == ""
        [line] = done.stderr.splitlines()
        assert line.startswith("SKF_BRIEF_RESULT_JSON: ")
        env = json.loads(line[len("SKF_BRIEF_RESULT_JSON: "):])
        mod.validate(env)
        return env

    def test_a_headless_halt_after_the_name_carries_the_name_and_the_sink(self, tmp_path):
        run_dir = self._run_dir(tmp_path, {"interactive": False, "mode": None, "skill_name": "demo"}, ["w1"])
        env = self._line(self._halt("target-inaccessible", run_dir))
        assert (env["status"], env["skill_name"], env["mode"], env["exit_code"]) == ("error", "demo", None, 3)
        assert env["halt_reason"] == "target-inaccessible" and env["warnings"] == ["w1"]

    def test_an_auto_halt_before_the_name_says_unknown(self, tmp_path):
        env = self._line(self._halt("input-missing", self._run_dir(tmp_path, {"interactive": False, "mode": "auto"})))
        assert (env["skill_name"], env["mode"], env["exit_code"]) == ("unknown", "auto", 2)
        assert "warnings" not in env

    def test_an_interactive_halt_prints_nothing(self, tmp_path):
        done = self._halt("write-failed", self._run_dir(tmp_path, {"interactive": True, "mode": None}, ["w1"]))
        assert (done.returncode, done.stdout, done.stderr) == (0, "", "")

    @pytest.mark.parametrize("extra,mode", [(("--mode", "auto"), "auto"), ((), None)], ids=["auto", "headless"])
    def test_the_write_probe_halt_needs_no_run_folder(self, extra, mode):
        env = self._line(self._halt("write-failed", None, *extra))
        assert (env["skill_name"], env["mode"], env["exit_code"]) == ("unknown", mode, 4)
        assert "warnings" not in env

    def test_the_write_probe_halt_carries_a_resolver_failure_read_on_stdin(self):
        """The write probe halts before the run folder exists, so no sink holds the resolver warning On Activation
        kept: `--customization-resolver-unavailable-from -` reads the reason on stdin, which the halt-reason form
        leaves free, and the line still says the `{project-root}/_bmad/custom/` overrides were not applied."""
        reason = "SKF helper skf-resolve-customization.py not found: it's `$(touch pwned)`"
        done = subprocess.run([sys.executable, str(SHARED_EMITTER), "emit-halt", "--workflow", "skf-brief-skill",
                               "--target", "stderr", "--halt-reason", "write-failed", "--mode", "auto",
                               "--customization-resolver-unavailable-from", "-"], input=reason + "\n",
                              capture_output=True, text=True, encoding="utf-8", timeout=30)
        env = self._line(done)
        assert (env["mode"], env["exit_code"]) == ("auto", 4)
        assert env["warnings"] == [f"customization_resolver_unavailable: {reason}"]

    @pytest.mark.parametrize("extra", [
        (),
        ("--phase", "step 0:write-probe", "--reason", "-"),
        ("--phase", "step 0:write-probe", "--reason", "cannot write: <message>", "--stderr-from", "-"),
    ], ids=["payload-on-stdin", "reason-on-stdin", "stderr-on-stdin"])
    def test_a_resolver_reason_on_stdin_is_refused_where_stdin_holds_something_else(self, extra):
        done = subprocess.run([sys.executable, str(SHARED_EMITTER), "emit-halt", "--workflow", "skf-brief-skill",
                               "--target", "stderr", *extra, "--customization-resolver-unavailable-from", "-"],
                              input='{"halt_reason": "write-failed"}', capture_output=True, text=True,
                              encoding="utf-8", timeout=30)
        assert done.returncode == 1 and "--customization-resolver-unavailable-from -" in done.stderr
        assert "SKF_BRIEF_RESULT_JSON" not in done.stdout + done.stderr

    @pytest.mark.parametrize("state,warning", [
        (b"{not json", "halt_state_unreadable: halt-state.json"),
        (b'["interactive"]', "halt_state_unreadable: halt-state.json"),
        ("{}".encode("utf-16"), "halt_state_unreadable: halt-state.json"),
        ("a folder", "halt_state_unreadable: halt-state.json"),
        ({"interactive": False, "mode": None, "skill_name": ""}, "halt_state_field_invalid: skill_name"),
        ({"interactive": False, "mode": "manual", "skill_name": "demo"}, "halt_state_field_invalid: mode"),
    ], ids=["not-json", "not-an-object", "utf-16", "a-folder", "empty-name", "mode-off-enum"])
    def test_a_bad_halt_state_still_emits_and_says_so(self, tmp_path, state, warning):
        env = self._line(self._halt("write-failed", self._run_dir(tmp_path, state)))
        assert env["warnings"] == [warning] and env["exit_code"] == 4
        assert env["skill_name"] == ("demo" if warning.endswith(": mode") else "unknown")
        assert env["mode"] is None

    def test_a_missing_halt_state_still_emits(self, tmp_path):
        env = self._line(self._halt("gh-auth-failed", self._run_dir(tmp_path, None, ["w1", "w2"])))
        assert (env["skill_name"], env["warnings"], env["exit_code"]) == ("unknown", ["w1", "w2"], 3)

    @pytest.mark.parametrize("reason", sorted(EXIT_CODES))
    def test_every_halt_reason_takes_its_exit_code(self, tmp_path, reason):
        run_dir = self._run_dir(tmp_path, {"interactive": False, "mode": "auto", "skill_name": "demo"})
        env = self._line(self._halt(reason, run_dir))
        assert (env["halt_reason"], env["exit_code"], env["mode"]) == (reason, EXIT_CODES[reason], "auto")

    def test_a_reason_the_schema_does_not_list_is_refused(self, tmp_path):
        done = self._halt("helper-missing", self._run_dir(tmp_path, {"interactive": False, "mode": None}))
        assert done.returncode == 1 and "SKF_BRIEF_RESULT_JSON" not in done.stdout + done.stderr

    def test_a_finished_run_still_needs_its_name(self, tmp_path):
        """halt_defaults apply to a halt alone: a success payload with no skill_name is refused, as before."""
        run_dir = self._run_dir(tmp_path, {"interactive": False, "mode": None, "skill_name": "demo"})
        done = subprocess.run([sys.executable, str(SHARED_EMITTER), "emit", "--workflow", "skf-brief-skill",
                               "--run-dir", str(run_dir)], input=json.dumps({"status": "success", "halt_reason": None}),
                              capture_output=True, text=True, encoding="utf-8", timeout=30)
        assert done.returncode == 1 and "skill_name" in done.stderr
