---
created: "2026-10-01 11:18"
session: "1eac7d31-a255-4a86-b7ad-388ffb7624ab"
---

# Windows os.replace PermissionError over an open file

On windows-latest, `os.replace(tmp, target)` fails with `PermissionError` (`[WinError 5] Access is denied`) whenever another process has the target open, such as a parallel writer's unlocked `Path.exists()` or `os.stat` check, an unlocked reader or a virus scanner. It surfaced as Windows-only flakes in `test/test-skf-gap-ledger.py::TestOverlappingAppends::test_parallel_appends_keep_every_record_they_report` (fixed in `gap-ledger.py` `save_ledger`, 0d4bc772) and `test/test-skf-forge-tier-rw.py::test_concurrent_registers_lose_no_entry`, which exited 2 with `atomic write failed for ...forge-tier.yaml: [WinError 5] Access is denied` (issue #715, PR #717, 11c1d5df). The fix retries only `PermissionError`, only when `os.name == "nt"`, for up to `_REPLACE_WAIT_SECONDS = 5.0`, polling every 0.02 s and staying under any lock's stale window (`REGISTRY_LOCK_STALE_SEC = 15.0`). No shared helper exists: the loop is hand-copied into `gap-ledger.py`, `skf-forge-tier-rw.py`, `campaign-state.py`, `skf-parse-gaps.py` and `skf-render-stack-metadata.py`, and `skf-run-lock.py`'s `_windows_retry` waits only about 0.2 s. `skf-atomic-write.py` `cmd_write` and 15 other `src/` scripts still call a bare `os.replace`. So a Windows-only WinError 5 from a rename is this race, not a flake: copy the loop into that writer and add a test that simulates Windows refusing the rename.
