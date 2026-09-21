---
created: "2026-05-23 04:39"
session: "d64265c8-b370-4295-81ad-33e6b95dd3d2"
source: claude-mem
source_table: observations
source_ids: [11146, 11157, 11183, 11184]
---

# Atomic-write idiom copied into six shared scripts

In `src/shared/scripts/` the crash-safe write pattern (stage to a `.skf-tmp` sibling, `os.fsync`, `os.replace`, opened with `os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)`) is copy-pasted, not imported. `skf-atomic-write.py` (`cmd_write`) is the canonical CLI, and `skf-rewrite-skill-name.py` (`atomic_write_text`), `skf-merge-ccc-exclusions.py`, `skf-rebuild-managed-sections.py`, `skf-forge-tier-rw.py` and `skf-write-skill-brief.py` each carry their own `_atomic_write`/`atomic_write` copy (two say "Mirrors skf-atomic-write.py"); only `skf-shard-body.py` delegates to the helper via subprocess. Any change to the idiom must be replicated in every copy: the Windows CRLF bug (missing `O_BINARY`) was fixed in one file and then had to be chased into all the others, each with its own regression test (`test/test-skf-forge-tier-rw.py`, `test/test-skf-merge-ccc-exclusions.py`). `grep -n 'O_BINARY' src/shared/scripts/*.py` is the quick parity check before shipping a write-path change.
