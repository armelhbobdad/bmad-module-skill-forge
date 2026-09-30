#!/usr/bin/env python3
"""Tests for skf-emit-brief-result-envelope.py.

The script has two pure functions (assemble, validate) plus two CLI
subcommands. Tests exercise both paths.
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
