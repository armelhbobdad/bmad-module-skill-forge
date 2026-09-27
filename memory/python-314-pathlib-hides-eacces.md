---
created: "2026-09-27 22:15"
session: "c33c9199-5464-4490-bac5-d3d511b89070"
---

# Python 3.14 pathlib hides EACCES, and uv run silently switches to it

From Python 3.14, `Path.is_dir()`, `is_file()`, `is_symlink()` and `exists()` return `False` for a path inside a folder the process cannot search (EACCES), where 3.13 and earlier raise `PermissionError`. So a helper that detects "cannot read" by catching that exception silently reads an unreadable version folder as absent on 3.14: `test/test-skf-enumerate-stack-skills.py::TestOwnership::test_unreadable_folder_in_a_group_keeps_its_marked_version` passed on 3.12 and failed only on 3.14 (`assert 0 == 1` on the warning count). The fix is to probe with `os.listdir`, `os.stat` or `os.lstat`, which raise on every version (`_skf_package` and `_metadata_problem` in `src/shared/scripts/skf-enumerate-stack-skills.py`, `_read_error` in `src/shared/scripts/skf-skill-inventory.py`). The trap surfaced because `uv run` with no pinned Python picks the newest managed interpreter: once an agent ran `uv run --python 3.14`, which installed 3.14, the pre-commit `npm test` ran under it, while CI (`quality.yaml`) pins 3.12. When touching a filesystem-walking helper, run the suite under both (`uv run --python 3.12 …` and `--python 3.14 …`), and when local results differ from CI, check `uv run python --version` and `uv python list --only-installed` first.
