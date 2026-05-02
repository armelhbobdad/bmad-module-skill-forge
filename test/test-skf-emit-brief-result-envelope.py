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
        }

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
        }
        mod.validate(env)  # must not raise — user-cancelled→6 is canonical


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
        }
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "validate"],
            input=json.dumps(env), capture_output=True, text=True,
        )
        assert proc.returncode == 1
        assert "canonical mapping" in proc.stderr
