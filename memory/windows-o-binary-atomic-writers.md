---
created: "2026-05-23 04:59"
session: "d64265c8-b370-4295-81ad-33e6b95dd3d2"
source: claude-mem
source_table: both
source_ids: [11177, 11178, 11180, 11183, 11185, 11187]
---

# Windows O_BINARY requirement for os.open byte-verbatim writers

On `windows-latest` CI every `os.open()`-based atomic writer (`os.open` + `os.write` + `os.fsync` + `os.replace`) silently translated LF to CRLF, because low-level descriptors default to text mode on Windows (unlike `open()`); the post-write byte check then failed with `post-write verification failed: on-disk bytes do not match staged content` (10 tests in `test/test-skf-rebuild-managed-sections.py`, PR #366). Every byte-verbatim writer must OR `getattr(os, "O_BINARY", 0)` into its `os.open` flags (it evaluates to 0 on POSIX). Today all six writers under `src/shared/scripts/` carry it with an inline comment (`skf-atomic-write.py` cmd_write, `skf-rebuild-managed-sections.py`, `skf-merge-ccc-exclusions.py`, `skf-forge-tier-rw.py`, `skf-write-skill-brief.py`, `skf-rewrite-skill-name.py`); the lock-file `os.open` in `skf-atomic-write.py` writes no content and does not need it. A new writer should copy the flags line, and its test should assert `b"\r\n" not in target.read_bytes()` as `test/test-skf-atomic-write.py:40` does — CONTRIBUTING.md says nothing about this, so the Windows CI leg is the only guard.
