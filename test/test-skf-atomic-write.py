#!/usr/bin/env python3
"""Tests for skf-atomic-write.py.

Highest-value test: the `write` subcommand must persist stdin bytes verbatim,
including line endings. On Windows os.open defaults to text mode and would
inject CRLF (\n -> \r\n) without the O_BINARY flag, corrupting JSON/markdown
artifacts the workflows write through this helper.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-atomic-write.py"
)


def _run_write(target: Path, data: bytes) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "write", "--target", str(target)],
        input=data,
        capture_output=True,
    )


class TestWriteByteIdentity:
    """The write subcommand persists stdin bytes verbatim (no newline mangling)."""

    def test_write_preserves_bytes_verbatim(self):
        data = b"---\nname: x\n---\n\nline1\nline2\n"
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "out.md"
            proc = _run_write(target, data)
            assert proc.returncode == 0, proc.stderr
            assert target.read_bytes() == data
            assert b"\r\n" not in target.read_bytes()

    def test_write_creates_parent_dirs(self):
        data = b"hello\nworld\n"
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "nested" / "deep" / "out.txt"
            proc = _run_write(target, data)
            assert proc.returncode == 0, proc.stderr
            assert target.read_bytes() == data

    def test_write_leaves_no_temp_file(self):
        data = b"content\n"
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "out.txt"
            proc = _run_write(target, data)
            assert proc.returncode == 0, proc.stderr
            assert not target.with_name(target.name + ".skf-tmp").exists()
